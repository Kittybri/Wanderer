from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import hashlib
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from google_docs_bridge import fetch_google_doc, overwrite_google_doc


ROOT_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = ROOT_DIR.parent
SCARA_TEMPLATE_DIR = DOWNLOADS_DIR / "scaramouche_blender_templates"
WANDERER_TEMPLATE_DIR = DOWNLOADS_DIR / "wanderer_blender_templates"
SCARA_VIDEO_SCRIPT = SCARA_TEMPLATE_DIR / "notes_to_scaramouche_video.py"
WANDERER_VIDEO_SCRIPT = WANDERER_TEMPLATE_DIR / "notes_to_wanderer_video.py"
DUO_VIDEO_SCRIPT = SCARA_TEMPLATE_DIR / "notes_to_duo_debate_video.py"
VIDEO_RENDER_TIMEOUT_S = int(os.getenv("VIDEO_RENDER_TIMEOUT_S", "1200") or "1200")
VIDEO_RENDER_WIDTH = int(os.getenv("VIDEO_RENDER_WIDTH", "960") or "960")
VIDEO_RENDER_HEIGHT = int(os.getenv("VIDEO_RENDER_HEIGHT", "540") or "540")
VIDEO_RENDER_FPS = int(os.getenv("VIDEO_RENDER_FPS", "8") or "8")
VIDEO_RENDER_ENGINE = os.getenv("VIDEO_RENDER_ENGINE", "BLENDER_WORKBENCH").strip() or "BLENDER_WORKBENCH"
VIDEO_RENDER_SECRET = (
    os.getenv("VIDEO_RENDER_SECRET")
    or os.getenv("VIDEO_RENDER_SHARED_SECRET")
    or ""
).strip()
VIDEO_RENDER_HOST = (os.getenv("VIDEO_RENDER_HOST") or "0.0.0.0").strip() or "0.0.0.0"
VIDEO_RENDER_PORT = int(os.getenv("VIDEO_RENDER_PORT", "8765") or "8765")
VIDEO_RENDER_MAX_QUEUE = int(os.getenv("VIDEO_RENDER_MAX_QUEUE", "6") or "6")
WORKER_GROQ_MODEL = (os.getenv("GROQ_MODEL_PRIMARY") or "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"

JOB_QUEUE: "queue.Queue[str]" = queue.Queue()
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
ACTIVE_JOB_ID: str | None = None
ACTIVE_FINGERPRINTS: dict[str, str] = {}
SUCCESS_DURATIONS: "deque[float]" = deque(maxlen=12)


def _job_fingerprint(job_type: str, bot_name: str, title: str, notes_text: str) -> str:
    payload = "\0".join((job_type, bot_name, title.strip(), notes_text.strip())).encode("utf-8", "ignore")
    return hashlib.sha256(payload).hexdigest()


def _queue_position_locked(job: dict) -> int | None:
    if job.get("status") == "running":
        return 0
    if job.get("status") != "queued":
        return None
    queued = sorted(
        (item for item in JOBS.values() if item.get("status") == "queued"),
        key=lambda item: (item.get("created_at", 0), item.get("job_id", "")),
    )
    return next((index for index, item in enumerate(queued, 1) if item["job_id"] == job["job_id"]), None)


def _wait_estimate_locked(job: dict) -> dict | None:
    position = _queue_position_locked(job)
    if position is None or len(SUCCESS_DURATIONS) < 3:
        return None
    jobs_ahead = position if ACTIVE_JOB_ID and position > 0 else max(0, position - 1)
    average = sum(SUCCESS_DURATIONS) / len(SUCCESS_DURATIONS)
    center = jobs_ahead * average
    # Intentionally coarse: rolling history is informative, not a promise.
    rounded = max(60, round(center / 60) * 60) if center else 0
    return {"low_seconds": max(0, rounded - 60), "high_seconds": rounded + 60,
            "based_on_completed_jobs": len(SUCCESS_DURATIONS)}


def _load_groq_keys() -> list[str]:
    keys: list[str] = []

    def _remember(value: str):
        cleaned = (value or "").strip()
        if cleaned and cleaned not in keys:
            keys.append(cleaned)

    packed = os.getenv("GROQ_API_KEYS", "")
    if packed:
        for piece in packed.replace(";", ",").replace("\n", ",").split(","):
            _remember(piece)

    for env_name, env_value in os.environ.items():
        if env_name == "GROQ_API_KEY":
            _remember(env_value)
            continue
        if env_name.startswith("GROQ_API_KEY_"):
            _remember(env_value)
    return keys


def _worker_docfix_prompt(bot_name: str, display_name: str, original_text: str, instructions: str = "") -> str:
    persona = "Scaramouche" if (bot_name or "").strip().lower() == "scaramouche" else "the Wanderer"
    flavor = (
        "cleaner and sharper"
        if persona == "Scaramouche"
        else "clearer, calmer, and more natural"
    )
    extra = instructions.strip() or "Fix wording, grammar, clarity, and flow while preserving meaning and overall structure."
    return (
        f"You are {persona} editing a Google Doc for {display_name}.\n"
        f"Revise the wording so it reads {flavor}, but do not invent facts or change the meaning.\n"
        f"Keep headings, paragraph breaks, and list-like structure where possible.\n"
        f"If the text is already good, make only light refinements.\n"
        f"Specific instruction: {extra}\n\n"
        f"Return only the final revised document text. No commentary, no notes, no quotes.\n\n"
        f"DOCUMENT:\n{original_text[:10000]}"
    )


def _worker_rewrite_google_doc_text(bot_name: str, display_name: str, original_text: str, instructions: str = "") -> str:
    from groq import Groq

    keys = _load_groq_keys()
    if not keys:
        raise RuntimeError("No Groq API key is configured on the worker.")
    client = Groq(api_key=keys[0])
    response = client.chat.completions.create(
        model=WORKER_GROQ_MODEL,
        max_tokens=1800,
        messages=[
            {
                "role": "user",
                "content": _worker_docfix_prompt(bot_name, display_name, original_text, instructions),
            }
        ],
    )
    content = ""
    if response and getattr(response, "choices", None):
        content = (response.choices[0].message.content or "").strip()
    return content or original_text


def _load_worker_env():
    candidates = [
        ROOT_DIR / "video_render_worker.env",
        ROOT_DIR / ".env",
    ]
    for path in candidates:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and value and not os.getenv(key):
                os.environ[key] = value


def _video_root() -> Path:
    configured = (os.getenv("VIDEO_RENDER_ROOT") or "").strip()
    if configured:
        path = Path(configured)
    else:
        path = Path(tempfile.gettempdir()) / "scara_wanderer_remote_jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _authorized(headers) -> bool:
    if not VIDEO_RENDER_SECRET:
        return True
    token = (headers.get("X-Render-Secret") or "").strip()
    auth = (headers.get("Authorization") or "").strip()
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    return token == VIDEO_RENDER_SECRET


def _script_for_job(job_type: str, bot_name: str) -> Path:
    if job_type == "duo":
        return DUO_VIDEO_SCRIPT
    key = (bot_name or "").strip().lower()
    if key == "scaramouche":
        return SCARA_VIDEO_SCRIPT
    if key == "wanderer":
        return WANDERER_VIDEO_SCRIPT
    raise ValueError(f"Unsupported bot video renderer: {bot_name}")


def _make_job_dir(job_id: str) -> Path:
    path = _video_root() / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _recover_job_state() -> int:
    """Recover terminal job visibility after a worker restart; never re-run work."""
    recovered = 0
    root = _video_root()
    directories = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
    with JOBS_LOCK:
        for path in directories:
            payload_path = path / "job_payload.json"
            if not payload_path.exists():
                continue
            try:
                metadata = json.loads(payload_path.read_text(encoding="utf-8"))
                summary_path = path / "run_summary.json"
                summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
                script = str(metadata.get("script") or "").casefold()
                job_type = "duo" if "duo" in script else "teaching"
                bot_name = "wanderer" if "wanderer" in script else "scaramouche"
                status = "done" if summary and os.path.exists(str(summary.get("final_video") or "")) else "failed"
                stamp = path.stat().st_mtime
                JOBS[path.name] = {
                    "job_id": path.name, "job_type": job_type, "bot_name": bot_name,
                    "title": metadata.get("title") or f"{bot_name.title()} Video",
                    "notes_text": "", "status": status, "created_at": stamp, "updated_at": stamp,
                    "summary": summary, "error": "" if status == "done" else "Worker restarted before this render completed.",
                    "traceback": "", "env_overrides": {}, "fingerprint": "",
                }
                recovered += 1
            except (OSError, ValueError, TypeError):
                continue
    return recovered


def _run_render_script(
    script_path: Path,
    notes_text: str,
    *,
    title: str,
    output_dir: Path,
    env_overrides: dict[str, str] | None = None,
) -> dict:
    if not script_path.exists():
        raise FileNotFoundError(f"Render script not found: {script_path}")

    notes_path = output_dir / "notes.txt"
    notes_path.write_text(notes_text, encoding="utf-8")
    payload_path = output_dir / "job_payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "script": str(script_path),
                "title": title,
                "env_keys": sorted((env_overrides or {}).keys()),
                "fish_key_present": bool((env_overrides or {}).get("FISH_AUDIO_API_KEY") or os.getenv("FISH_AUDIO_API_KEY")),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        str(script_path),
        str(notes_path),
        "--width",
        str(VIDEO_RENDER_WIDTH),
        "--height",
        str(VIDEO_RENDER_HEIGHT),
        "--fps",
        str(VIDEO_RENDER_FPS),
        "--engine",
        VIDEO_RENDER_ENGINE,
        "--output-dir",
        str(output_dir),
    ]
    if title.strip():
        cmd.extend(["--title", title.strip()])

    run_env = os.environ.copy()
    if env_overrides:
        for key, value in env_overrides.items():
            if isinstance(key, str) and isinstance(value, str):
                run_env[key] = value

    proc = subprocess.run(
        cmd,
        cwd=str(script_path.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=VIDEO_RENDER_TIMEOUT_S,
        text=True,
        encoding="utf-8",
        errors="ignore",
        env=run_env,
    )
    combined = proc.stdout or ""
    summary_path = output_dir / "run_summary.json"
    if proc.returncode != 0:
        tail = "\n".join(combined.splitlines()[-20:]) or "no output"
        raise RuntimeError(f"Video rendering failed.\n{tail}")
    if not summary_path.exists():
        tail = "\n".join(combined.splitlines()[-20:]) or "no output"
        raise RuntimeError(f"Render finished without a summary file.\n{tail}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["_logs"] = combined[-4000:]
    return summary


def _public_job_payload(job: dict) -> dict:
    summary = job.get("summary") or {}
    final_video = (summary.get("final_video") or "").strip()
    payload = {
        "job_id": job["job_id"],
        "status": job["status"],
        "job_type": job["job_type"],
        "bot_name": job["bot_name"],
        "title": job["title"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "error": "Render failed. Check worker logs." if job.get("status") == "failed" else "",
    }
    position = _queue_position_locked(job)
    if position is not None:
        payload["queue_position"] = position
    estimate = _wait_estimate_locked(job)
    if estimate:
        payload["estimated_wait"] = estimate
    if job["status"] == "done" and final_video and os.path.exists(final_video):
        payload["download_url"] = f"/jobs/{job['job_id']}/file"
        payload["final_video_name"] = Path(final_video).name
        payload["summary"] = {
            "title": summary.get("title") or job["title"],
            "final_video_name": Path(final_video).name,
        }
    return payload


def _process_next_job() -> str | None:
    """Process one FIFO item. Split out so queue failure behavior is testable."""
    global ACTIVE_JOB_ID
    job_id = JOB_QUEUE.get()
    try:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return None
            if job.get("status") == "cancelled":
                ACTIVE_FINGERPRINTS.pop(job.get("fingerprint", ""), None)
                return job_id
            ACTIVE_JOB_ID = job_id
            job["status"] = "running"
            job["started_at"] = time.time()
            job["updated_at"] = time.time()

        try:
            output_dir = _make_job_dir(job_id)
            summary = _run_render_script(
                _script_for_job(job["job_type"], job["bot_name"]),
                job["notes_text"],
                title=job["title"],
                output_dir=output_dir,
                env_overrides=job.get("env_overrides") or {},
            )
            with JOBS_LOCK:
                job["summary"] = summary
                job["status"] = "done"
                job["error"] = ""
                SUCCESS_DURATIONS.append(max(0.0, time.time() - job.get("started_at", time.time())))
        except Exception as exc:
            with JOBS_LOCK:
                job["status"] = "failed"
                job["error"] = str(exc)
                job["traceback"] = traceback.format_exc(limit=10)
        finally:
            with JOBS_LOCK:
                job["updated_at"] = time.time()
                ACTIVE_FINGERPRINTS.pop(job.get("fingerprint", ""), None)
                ACTIVE_JOB_ID = None
        return job_id
    finally:
        JOB_QUEUE.task_done()


def _worker_loop():
    while True:
        _process_next_job()


class RenderRequestHandler(BaseHTTPRequestHandler):
    server_version = "ScaraWandererRenderWorker/1.0"

    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path):
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                {
                    "ok": True,
                    "active_job_id": ACTIVE_JOB_ID,
                    "queued_jobs": JOB_QUEUE.qsize(),
                    "known_jobs": len(JOBS),
                }
            )
            return

        if not _authorized(self.headers):
            self._send_json({"ok": False, "error": "Unauthorized"}, status=401)
            return

        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 2 and parts[0] == "jobs":
            with JOBS_LOCK:
                job = JOBS.get(parts[1])
                if not job:
                    self._send_json({"ok": False, "error": "Unknown job id."}, status=404)
                    return
                self._send_json(_public_job_payload(job))
                return

        if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "file":
            with JOBS_LOCK:
                job = JOBS.get(parts[1])
                if not job:
                    self._send_json({"ok": False, "error": "Unknown job id."}, status=404)
                    return
                summary = job.get("summary") or {}
                final_video = (summary.get("final_video") or "").strip()
            if job.get("status") != "done" or not final_video or not os.path.exists(final_video):
                self._send_json({"ok": False, "error": "Video file is not ready."}, status=409)
                return
            self._send_file(Path(final_video))
            return

        self._send_json({"ok": False, "error": "Not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if not _authorized(self.headers):
            self._send_json({"ok": False, "error": "Unauthorized"}, status=401)
            return
        if parsed.path == "/docfix":
            try:
                body = self._read_json()
            except Exception:
                self._send_json({"ok": False, "error": "Expected JSON body."}, status=400)
                return
            doc_url = (body.get("doc_url") or body.get("doc_link") or "").strip()
            bot_name = (body.get("bot_name") or "scaramouche").strip().lower()
            instructions = (body.get("instructions") or "").strip()
            display_name = (body.get("display_name") or "you").strip() or "you"
            if bot_name not in {"scaramouche", "wanderer"}:
                self._send_json({"ok": False, "error": "bot_name must be 'scaramouche' or 'wanderer'."}, status=400)
                return
            if not doc_url:
                self._send_json({"ok": False, "error": "doc_url is required."}, status=400)
                return
            try:
                doc = fetch_google_doc(doc_url)
                if not (doc.get("text") or "").strip():
                    self._send_json({"ok": False, "error": "The Google Doc is empty or unreadable."}, status=400)
                    return
                revised = _worker_rewrite_google_doc_text(bot_name, display_name, doc["text"], instructions)
                result = overwrite_google_doc(doc_url, revised)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=500)
                return
            self._send_json(
                {
                    "ok": True,
                    "doc_id": result["doc_id"],
                    "title": result["title"],
                    "chars_written": result["chars_written"],
                },
                status=200,
            )
            return
        if parsed.path != "/jobs":
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        try:
            body = self._read_json()
        except Exception:
            self._send_json({"ok": False, "error": "Expected JSON body."}, status=400)
            return

        job_type = (body.get("job_type") or "").strip().lower()
        bot_name = (body.get("bot_name") or "").strip().lower()
        notes_text = (body.get("notes_text") or "").strip()
        title = (body.get("title") or "").strip()
        env_overrides = body.get("env_overrides") or {}
        if not isinstance(env_overrides, dict):
            self._send_json({"ok": False, "error": "env_overrides must be an object when provided."}, status=400)
            return
        clean_overrides = {}
        for key, value in env_overrides.items():
            if isinstance(key, str) and isinstance(value, str):
                clean_overrides[key] = value

        if job_type not in {"teaching", "duo"}:
            self._send_json({"ok": False, "error": "job_type must be 'teaching' or 'duo'."}, status=400)
            return
        if job_type == "teaching" and bot_name not in {"scaramouche", "wanderer"}:
            self._send_json({"ok": False, "error": "bot_name must be 'scaramouche' or 'wanderer' for teaching jobs."}, status=400)
            return
        if job_type == "duo":
            bot_name = "scaramouche"
        if not notes_text:
            self._send_json({"ok": False, "error": "notes_text is required."}, status=400)
            return

        fingerprint = _job_fingerprint(job_type, bot_name, title, notes_text)
        job_id = uuid.uuid4().hex[:12]
        now = time.time()
        job = {
            "job_id": job_id,
            "job_type": job_type,
            "bot_name": bot_name,
            "title": title or f"{bot_name.title()} Video",
            "notes_text": notes_text,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "summary": {},
            "error": "",
            "traceback": "",
            "env_overrides": clean_overrides,
            "fingerprint": fingerprint,
        }
        with JOBS_LOCK:
            duplicate_id = ACTIVE_FINGERPRINTS.get(fingerprint)
            if duplicate_id:
                existing = JOBS.get(duplicate_id)
                payload = _public_job_payload(existing) if existing else {"job_id": duplicate_id, "status": "queued"}
                payload.update({"ok": True, "duplicate": True})
                self._send_json(payload, status=200)
                return
            queued_count = sum(1 for item in JOBS.values() if item.get("status") == "queued")
            if queued_count >= VIDEO_RENDER_MAX_QUEUE:
                self._send_json({"ok": False, "error": "Render queue is full. Try again later."}, status=429)
                return
            JOBS[job_id] = job
            ACTIVE_FINGERPRINTS[fingerprint] = job_id
            response = _public_job_payload(job)
        JOB_QUEUE.put(job_id)
        response["ok"] = True
        self._send_json(response, status=202)

    def do_DELETE(self):
        if not _authorized(self.headers):
            self._send_json({"ok": False, "error": "Unauthorized"}, status=401)
            return
        parts = [part for part in urlparse(self.path).path.split("/") if part]
        if len(parts) != 2 or parts[0] != "jobs":
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        with JOBS_LOCK:
            job = JOBS.get(parts[1])
            if not job:
                self._send_json({"ok": False, "error": "Unknown job id."}, status=404)
                return
            if job.get("status") != "queued":
                self._send_json({"ok": False, "error": "Only queued jobs can be cancelled."}, status=409)
                return
            job["status"] = "cancelled"
            job["updated_at"] = time.time()
            ACTIVE_FINGERPRINTS.pop(job.get("fingerprint", ""), None)
            self._send_json({"ok": True, "job_id": job["job_id"], "status": "cancelled"})

    def log_message(self, format, *args):
        print(f"[video-worker] {self.address_string()} - {format % args}")


if __name__ == "__main__":
    _load_worker_env()
    recovered = _recover_job_state()
    print(f"[video-worker] Starting on http://{VIDEO_RENDER_HOST}:{VIDEO_RENDER_PORT}")
    print(f"[video-worker] Queue size limit: {VIDEO_RENDER_MAX_QUEUE}")
    print(f"[video-worker] Secret protection: {'enabled' if VIDEO_RENDER_SECRET else 'disabled'}")
    print(f"[video-worker] Recovered terminal jobs: {recovered}")
    worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    worker_thread.start()
    server = ThreadingHTTPServer((VIDEO_RENDER_HOST, VIDEO_RENDER_PORT), RenderRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
