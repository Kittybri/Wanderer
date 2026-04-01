import argparse
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
import imageio_ffmpeg
import ormsgpack
from dotenv import load_dotenv
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_BLEND = ROOT_DIR / "wanderer_presentation_templates_with_wanderer.blend"
BOT_CODE_ROOT = ROOT_DIR.parent / "scara_wanderer_bots"
DEFAULT_BLENDER = Path(
    os.getenv("BLENDER_BIN")
    or (r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" if os.name == "nt" else "/usr/bin/blender")
)
DEFAULT_PLATE_SCRIPT = ROOT_DIR / "render_wanderer_plates.py"
DEFAULT_FISH_API_URL = "https://api.fish.audio/v1/tts"
FALLBACK_VOICE_ID = "fb95ab47841a4db189cb35fb619d4ea1"
SCENE_MOODS = {
    "01_Lecture_Explainer": "lecture",
    "02_Side_Screen_Breakdown": "lecture",
    "03_Close_Confession": "confession",
    "04_Mission_Briefing": "mission",
    "05_Duo_Debate": "debate",
}
WANDERER_OPENERS = [
    "Listen carefully.",
    "Let us sort through this properly.",
    "Start with what can actually be observed.",
]
WANDERER_TRANSITIONS = [
    "Next.",
    "There is another angle to this.",
    "Look closer.",
]
WANDERER_CLOSERS = [
    "Hold onto that thought.",
    "That will matter in a moment.",
    "Do not lose the thread now.",
]


@dataclass
class Section:
    title: str
    points: list[str]
    narration: str


def load_environment():
    root_env = Path(__file__).resolve().parent.parent / ".env"
    bot_env = BOT_CODE_ROOT / ".env"
    if root_env.exists():
        load_dotenv(root_env)
    if bot_env.exists():
        load_dotenv(bot_env)


def maybe_import_voice_handler():
    voice_path = BOT_CODE_ROOT / "voice_handler.py"
    if not voice_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("wanderer_voice_handler", voice_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug or "wanderer-lesson"


def read_notes(notes_arg: str) -> str:
    candidate = Path(notes_arg)
    if candidate.exists() and candidate.is_file():
        return candidate.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
    return notes_arg.lstrip("\ufeff")


def sentence_split(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def clean_point(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^(?:[-*]|\u2022|\d+[.)]?|\(?\d+\)|\W)\s*", "", text)
    return re.sub(r"\s+", " ", text).strip(" -")


def derive_title(notes: str) -> str:
    for line in notes.splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if len(stripped) > 8:
            return stripped[:80]
    return "Wanderer Lesson"


def split_sections(notes: str, max_sections: int = 5) -> list[Section]:
    lines = notes.splitlines()
    raw_sections = []
    current_title = None
    current_body = []

    def flush():
        nonlocal current_title, current_body
        body_text = "\n".join(current_body).strip()
        if body_text:
            raw_sections.append((current_title or "", body_text))
        current_title = None
        current_body = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_body:
                current_body.append("")
            continue
        if stripped.startswith("#"):
            flush()
            current_title = stripped.lstrip("#").strip()
        else:
            current_body.append(stripped)
    flush()

    if not raw_sections:
        blocks = [block.strip() for block in re.split(r"\n\s*\n", notes) if block.strip()]
        raw_sections = [("", block) for block in blocks]

    normalized = []
    for heading, body in raw_sections:
        points = []
        for line in body.splitlines():
            cleaned = clean_point(line)
            if cleaned:
                points.append(cleaned)
        if not points:
            points = sentence_split(body)
        if not points:
            continue
        title = heading or points[0][:50].rstrip(".")
        normalized.append((title, points))

    if not normalized:
        fallback_title = derive_title(notes)
        normalized = [(fallback_title, sentence_split(notes)[:5] or [notes.strip()])]

    while len(normalized) > max_sections:
        a_title, a_points = normalized[-2]
        b_title, b_points = normalized[-1]
        normalized[-2] = (a_title, a_points + b_points)
        normalized.pop()

    sections = []
    for idx, (title, points) in enumerate(normalized[:max_sections], start=1):
        title = title.strip() or f"Section {idx}"
        points = [point for point in points if point][:4]
        narration = build_narration(title, points, idx == 1)
        sections.append(Section(title=title, points=points, narration=narration))

    if len(sections) < 3:
        expanded = []
        for section in sections:
            if len(section.points) >= 4 and len(expanded) < 5:
                midpoint = math.ceil(len(section.points) / 2)
                first = section.points[:midpoint]
                second = section.points[midpoint:]
                expanded.append(Section(section.title, first, build_narration(section.title, first, len(expanded) == 0)))
                if second and len(expanded) < 5:
                    continued = f"{section.title} Continued"
                    expanded.append(Section(continued, second, build_narration(continued, second, False)))
            else:
                expanded.append(section)
        sections = expanded[:5]

    return sections


def build_narration(title: str, points: list[str], is_intro: bool) -> str:
    if is_intro:
        intro = f"{WANDERER_OPENERS[0]} {title}."
    else:
        intro = f"{WANDERER_TRANSITIONS[(len(title) + len(points)) % len(WANDERER_TRANSITIONS)]} {title}."
    lines = [intro]
    for point in points[:3]:
        sentence = point.strip()
        if sentence and sentence[-1] not in ".!?":
            sentence += "."
        lines.append(sentence)
    lines.append(WANDERER_CLOSERS[(len(title) + len(lines)) % len(WANDERER_CLOSERS)])
    return " ".join(lines)


def ensure_output_dir(base_name: str) -> Path:
    out_dir = ROOT_DIR / "outputs" / slugify(base_name)
    suffix = 1
    final = out_dir
    while final.exists():
        suffix += 1
        final = ROOT_DIR / "outputs" / f"{slugify(base_name)}-{suffix}"
    final.mkdir(parents=True, exist_ok=True)
    return final


def font_candidates(*names: str) -> ImageFont.FreeTypeFont:
    font_dirs = [
        Path(r"C:\Windows\Fonts"),
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/liberation2"),
        Path("/usr/share/fonts"),
    ]
    for name in names:
        for font_dir in font_dirs:
            candidate = font_dir / name
            if candidate.exists():
                return ImageFont.truetype(str(candidate), size=40)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def draw_vertical_gradient(image: Image.Image, top_rgb: tuple[int, int, int], bottom_rgb: tuple[int, int, int]):
    width, height = image.size
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top_rgb[idx] * (1 - t) + bottom_rgb[idx] * t) for idx in range(3))
        draw.line((0, y, width, y), fill=color)


def draw_wanderer_accent_shapes(draw: ImageDraw.ImageDraw):
    draw.ellipse((1180, -180, 1940, 520), fill=(28, 83, 96))
    draw.ellipse((1340, 80, 2060, 760), fill=(17, 45, 57))
    draw.rectangle((0, 0, 1920, 32), fill=(98, 198, 206))
    draw.rounded_rectangle((126, 108, 1794, 954), radius=42, fill=(10, 18, 27), outline=(89, 175, 184), width=3)
    draw.rounded_rectangle((132, 114, 1788, 948), radius=38, outline=(24, 52, 62), width=2)


def create_slide_images(title: str, sections: list[Section], slides_dir: Path) -> list[Path]:
    slides_dir.mkdir(parents=True, exist_ok=True)
    title_font = font_candidates("segoeuib.ttf", "arialbd.ttf")
    section_font = font_candidates("georgiab.ttf", "arialbd.ttf")
    body_font = font_candidates("segoeui.ttf", "arial.ttf")
    small_font = font_candidates("segoeui.ttf", "arial.ttf")

    slide_paths = []
    for idx, section in enumerate(sections, start=1):
        image = Image.new("RGB", (1920, 1080), (9, 17, 22))
        draw_vertical_gradient(image, (11, 21, 28), (10, 34, 42))
        draw = ImageDraw.Draw(image)
        draw_wanderer_accent_shapes(draw)

        draw.text((178, 162), title, font=title_font.font_variant(size=46), fill=(236, 245, 247))
        draw.rounded_rectangle((172, 236, 820, 308), radius=24, fill=(67, 140, 151))
        draw.text((206, 251), section.title, font=section_font.font_variant(size=34), fill=(242, 248, 250))
        draw.text((1516, 166), f"{idx:02d}", font=title_font.font_variant(size=72), fill=(111, 218, 226))
        draw.text((1498, 252), "Wanderer Notes", font=small_font.font_variant(size=26), fill=(181, 216, 221))

        y = 368
        for point in section.points:
            wrapped = wrap_text(draw, point, body_font.font_variant(size=34), 1260)
            box_height = 56 + (max(1, len(wrapped)) - 1) * 38
            draw.rounded_rectangle((176, y - 10, 1650, y + box_height), radius=26, fill=(17, 29, 40), outline=(45, 94, 106), width=2)
            draw.rounded_rectangle((194, y + 12, 230, y + 48), radius=12, fill=(98, 194, 203))
            text_y = y + 6
            for line in wrapped:
                draw.text((258, text_y), line, font=body_font.font_variant(size=34), fill=(229, 238, 241))
                text_y += 38
            y += box_height + 26

        footer = f"Slide {idx} of {len(sections)}"
        draw.text((1550, 986), footer, font=small_font.font_variant(size=24), fill=(164, 196, 202))
        draw.text((176, 986), "A quieter way to learn it.", font=small_font.font_variant(size=24), fill=(150, 182, 187))
        output = slides_dir / f"slide_{idx:02d}.png"
        image.save(output)
        slide_paths.append(output)
    return slide_paths


def split_for_tts(text: str, max_chars: int = 1200) -> list[str]:
    sentences = sentence_split(text)
    chunks = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
            continue
        if len(current) + 1 + len(sentence) <= max_chars:
            current += " " + sentence
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks or [text[:max_chars]]


def get_voice_id() -> str:
    module = maybe_import_voice_handler()
    if module is not None and hasattr(module, "resolve_voice_id"):
        resolved = (module.resolve_voice_id(bot_name="wanderer") or "").strip()
        if resolved:
            return resolved
    for env_name in ("WANDERER_FISH_VOICE_ID", "WANDERER_VOICE_ID", "FISH_AUDIO_REFERENCE_ID", "FISH_REFERENCE_ID"):
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value
    if module is not None and getattr(module, "VOICE_ID", ""):
        return module.VOICE_ID
    return FALLBACK_VOICE_ID


def fish_tts_chunk(text: str, api_key: str, voice_id: str) -> bytes:
    module = maybe_import_voice_handler()
    if module is not None and hasattr(module, "_fish_tts_blocking"):
        audio_bytes = module._fish_tts_blocking(
            text,
            api_key,
            220,
            voice_id=voice_id,
            bot_name="wanderer",
        )
        if audio_bytes:
            return audio_bytes
    payload = ormsgpack.packb(
        {
            "text": text[:1500],
            "reference_id": voice_id,
            "format": "mp3",
            "mp3_bitrate": 192,
            "latency": "balanced",
            "normalize": True,
            "chunk_length": 230,
        }
    )
    headers = {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/msgpack",
        "model": "s2-pro",
    }
    api_url = (os.getenv("FISH_API_URL") or DEFAULT_FISH_API_URL).strip()
    with httpx.Client(timeout=120) as client:
        response = client.post(api_url, content=payload, headers=headers)
    response.raise_for_status()
    return response.content


def gtts_chunk(text: str, output_path: Path):
    tts = gTTS(text=text, lang="en", slow=False)
    tts.save(str(output_path))


def concat_audio(ffmpeg_exe: str, inputs: list[Path], output_path: Path):
    list_file = output_path.with_suffix(".concat.txt")
    list_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in inputs), encoding="utf-8")
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


def synthesize_audio(text: str, output_dir: Path) -> Path:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    audio_dir = output_dir / "audio_chunks"
    audio_dir.mkdir(exist_ok=True)
    chunks = split_for_tts(text)
    api_key = (os.getenv("FISH_AUDIO_API_KEY") or "").strip()
    voice_id = get_voice_id()
    chunk_paths = []

    for idx, chunk in enumerate(chunks, start=1):
        chunk_path = audio_dir / f"chunk_{idx:02d}.mp3"
        if api_key:
            audio_bytes = fish_tts_chunk(chunk, api_key, voice_id)
            chunk_path.write_bytes(audio_bytes)
        else:
            gtts_chunk(chunk, chunk_path)
        chunk_paths.append(chunk_path)

    final_audio = output_dir / "wanderer_narration.mp3"
    if len(chunk_paths) == 1:
        chunk_paths[0].replace(final_audio)
    else:
        concat_audio(ffmpeg_exe, chunk_paths, final_audio)
    return final_audio


def probe_media_duration(media_path: Path) -> float:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run(
        [ffmpeg_exe, "-i", str(media_path)],
        capture_output=True,
        text=True,
    )
    text = proc.stderr or proc.stdout
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        return 12.0
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def build_spec(title: str, sections: list[Section], slide_paths: list[Path]) -> dict:
    total_words = max(1, sum(len(section.narration.split()) for section in sections))
    consumed_words = 0
    segments = []

    for section, slide_path in zip(sections, slide_paths):
        words = len(section.narration.split())
        start_ratio = consumed_words / total_words
        consumed_words += words
        end_ratio = consumed_words / total_words
        segments.append(
            {
                "title": section.title,
                "narration": section.narration,
                "slide_path": str(slide_path),
                "start_ratio": start_ratio,
                "end_ratio": end_ratio,
            }
        )

    transcript = " ".join(section.narration for section in sections)
    return {
        "title": title,
        "transcript": transcript,
        "segments": segments,
    }


def render_plates(
    blender_exe: Path,
    blend_path: Path,
    scene_name: str,
    spec_path: Path,
    plates_dir: Path,
    width: int,
    height: int,
    engine: str,
):
    mood = SCENE_MOODS.get(scene_name, "lecture")
    cmd = [
        str(blender_exe),
        "-b",
        "--python",
        str(DEFAULT_PLATE_SCRIPT),
        "--",
        "--blend",
        str(blend_path),
        "--scene",
        scene_name,
        "--spec",
        str(spec_path),
        "--output-dir",
        str(plates_dir),
        "--mood",
        mood,
        "--width",
        str(width),
        "--height",
        str(height),
        "--engine",
        engine,
    ]
    subprocess.run(cmd, check=True)


def word_viseme(word: str) -> str:
    token = "".join(ch for ch in word.lower() if ch.isalpha())
    if not token:
        return "rest"
    if token.endswith(("m", "n")):
        return "n"
    for char in token:
        if char in "aeiou":
            return {
                "a": "a",
                "e": "e",
                "i": "i",
                "o": "o",
                "u": "u",
            }[char]
    return "rest"


def build_segment_frame_labels(text: str, frames: int) -> list[str]:
    words = [word for word in text.split() if word.strip()]
    if not words:
        return ["rest"] * max(1, frames)
    labels = ["rest"] * max(1, frames)
    per_word = max(1.0, frames / max(1, len(words)))
    for idx, word in enumerate(words):
        start = int(round(idx * per_word))
        end = min(len(labels), max(start + 1, int(round((idx + 1) * per_word))))
        mid = start + max(1, (end - start) // 2)
        viseme = word_viseme(word)
        for pos in range(start, end):
            labels[pos] = "rest"
        if start < len(labels):
            labels[start] = "rest"
        if mid < len(labels):
            labels[mid] = viseme
        if end - 1 < len(labels):
            labels[end - 1] = "rest"
    return labels


def build_frame_plan(spec: dict, duration_seconds: float, fps: int) -> list[tuple[int, str]]:
    total_frames = max(1, int(math.ceil(duration_seconds * fps)))
    segments = spec.get("segments", [])
    plan = []
    for index, segment in enumerate(segments, start=1):
        start = int(round(segment.get("start_ratio", 0.0) * total_frames))
        end = int(round(segment.get("end_ratio", 1.0) * total_frames))
        if index == len(segments):
            end = total_frames
        frames = max(1, end - start)
        labels = build_segment_frame_labels(segment.get("narration", ""), frames)
        plan.extend((index, label) for label in labels)
    while len(plan) < total_frames:
        plan.append((len(segments) or 1, "rest"))

    blink_every = max(fps * 3, 24)
    for blink_frame in range(fps * 2, len(plan), blink_every):
        for offset in range(2):
            frame = blink_frame + offset
            if frame < len(plan):
                segment_index, _ = plan[frame]
                plan[frame] = (segment_index, "blink")
    return plan[:total_frames]


def assemble_frame_images(plates_manifest: dict, frame_plan: list[tuple[int, str]], frames_dir: Path):
    frames_dir.mkdir(parents=True, exist_ok=True)
    for idx, (segment_index, viseme) in enumerate(frame_plan, start=1):
        segment = plates_manifest["plates"].get(str(segment_index), {})
        source = segment.get(viseme) or segment.get("rest")
        if not source:
            continue
        target = frames_dir / f"frame_{idx:05d}.png"
        shutil.copyfile(source, target)


def encode_video(frames_dir: Path, fps: int, audio_path: Path, final_video: Path):
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame_%05d.png"),
        "-i",
        str(audio_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(final_video),
    ]
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description="Create a Wanderer presentation video from notes.")
    parser.add_argument("notes", help="Notes text or a path to a notes file.")
    parser.add_argument("--title", default="", help="Optional lesson title.")
    parser.add_argument("--output-dir", default="", help="Optional output directory override.")
    parser.add_argument("--scene", default="01_Lecture_Explainer", help="Template scene to render.")
    parser.add_argument("--blend", default=str(DEFAULT_BLEND), help="Path to the populated Wanderer blend.")
    parser.add_argument("--blender", default=str(DEFAULT_BLENDER), help="Path to Blender binary.")
    parser.add_argument("--width", type=int, default=1280, help="Output video width.")
    parser.add_argument("--height", type=int, default=720, help="Output video height.")
    parser.add_argument("--engine", default="BLENDER_WORKBENCH", help="Render engine for the one-click pipeline.")
    parser.add_argument("--fps", type=int, default=12, help="Output video fps for the fast talking-head mode.")
    args = parser.parse_args()

    load_environment()

    notes_text = read_notes(args.notes)
    title = args.title.strip() or derive_title(notes_text)
    sections = split_sections(notes_text)
    output_dir = Path(args.output_dir) if args.output_dir else ensure_output_dir(title)
    output_dir.mkdir(parents=True, exist_ok=True)
    slides_dir = output_dir / "slides"
    slide_paths = create_slide_images(title, sections, slides_dir)
    spec = build_spec(title, sections, slide_paths)

    transcript_path = output_dir / "transcript.txt"
    transcript_path.write_text(spec["transcript"], encoding="utf-8")

    spec_path = output_dir / "presentation_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    audio_path = synthesize_audio(spec["transcript"], output_dir)
    duration_seconds = probe_media_duration(audio_path)
    plates_dir = output_dir / "plates"
    frames_dir = output_dir / "frames"
    final_video = output_dir / "wanderer_presentation.mp4"

    render_plates(
        Path(args.blender),
        Path(args.blend),
        args.scene,
        spec_path,
        plates_dir,
        args.width,
        args.height,
        args.engine,
    )
    plates_manifest = json.loads((plates_dir / "plates_manifest.json").read_text(encoding="utf-8"))
    frame_plan = build_frame_plan(spec, duration_seconds, args.fps)
    assemble_frame_images(plates_manifest, frame_plan, frames_dir)
    encode_video(frames_dir, args.fps, audio_path, final_video)

    summary = {
        "title": title,
        "scene": args.scene,
        "slides": [str(path) for path in slide_paths],
        "transcript": str(transcript_path),
        "audio": str(audio_path),
        "spec": str(spec_path),
        "plates_dir": str(plates_dir),
        "frames_dir": str(frames_dir),
        "final_video": str(final_video),
    }
    (output_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
