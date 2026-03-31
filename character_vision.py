import base64
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv


root_env = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=root_env) if os.path.exists(root_env) else load_dotenv()

XAI_API_KEY = (os.getenv("XAI_API_KEY") or "").strip()
XAI_BASE_URL = (os.getenv("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")
VISION_MODEL = (os.getenv("XAI_VISION_MODEL") or "grok-2-vision-1212").strip()
XAI_EXHAUSTED_SILENCE_S = int(os.getenv("XAI_EXHAUSTED_SILENCE_S", "600") or "600")
_VISION_EXHAUSTED_UNTIL = 0.0

BOT_SYSTEM_PROMPTS = {
    "scaramouche": (
        "You are Scaramouche: sharp, direct, and concise. "
        "When given an image, identify important visual details first, "
        "then explain implications in plain language."
    ),
    "wanderer": (
        "You are Wanderer: reflective, clear, and analytical. "
        "When given an image, describe what is observable, call out uncertainty, "
        "and provide practical takeaways."
    ),
}


def _mark_vision_exhausted(retry_after_s: int) -> None:
    global _VISION_EXHAUSTED_UNTIL
    _VISION_EXHAUSTED_UNTIL = max(_VISION_EXHAUSTED_UNTIL, time.time() + max(XAI_EXHAUSTED_SILENCE_S, retry_after_s))


def vision_is_exhausted() -> bool:
    return time.time() < _VISION_EXHAUSTED_UNTIL


def vision_exhausted_remaining() -> int:
    return max(0, int(_VISION_EXHAUSTED_UNTIL - time.time()))


def _parse_retry_after_s(response: requests.Response) -> int:
    header = (response.headers or {}).get("Retry-After", "").strip()
    if header.isdigit():
        return max(XAI_EXHAUSTED_SILENCE_S, int(header))

    text = ""
    try:
        text = response.text or ""
    except Exception:
        text = ""
    match = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", text, re.IGNORECASE)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = float(match.group(3) or 0.0)
        return max(XAI_EXHAUSTED_SILENCE_S, int(hours * 3600 + minutes * 60 + seconds))
    match = re.search(r"retry[- ]after[:= ]+(\d+)", text, re.IGNORECASE)
    if match:
        return max(XAI_EXHAUSTED_SILENCE_S, int(match.group(1)))
    return XAI_EXHAUSTED_SILENCE_S


def _image_part(
    image_url: Optional[str],
    image_path: Optional[str],
    image_bytes: Optional[bytes],
    mime_type: Optional[str],
) -> dict:
    if image_url:
        return {"type": "image_url", "image_url": {"url": image_url}}

    if image_bytes is not None:
        mime = mime_type or "image/png"
        data = base64.b64encode(image_bytes).decode("utf-8")
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}

    if not image_path:
        raise ValueError("Provide image_url, image_path, or image_bytes for vision input.")

    p = Path(image_path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    mime = mime_type or mimetypes.guess_type(str(p))[0] or "image/png"
    data = base64.b64encode(p.read_bytes()).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def ask_character_bot(
    bot_name: str,
    prompt: str,
    *,
    image_url: Optional[str] = None,
    image_path: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    timeout_s: int = 90,
) -> str:
    """Run Scaramouche or Wanderer with optional vision input through xAI."""
    if not XAI_API_KEY:
        raise RuntimeError("Missing XAI_API_KEY")
    if vision_is_exhausted():
        return ""

    key = bot_name.strip().lower()
    if key not in BOT_SYSTEM_PROMPTS:
        raise ValueError(f"Unsupported bot_name: {bot_name}. Use one of: {', '.join(BOT_SYSTEM_PROMPTS)}")

    content = [{"type": "text", "text": prompt.strip()}]
    if image_url or image_path or image_bytes is not None:
        content.append(
            _image_part(
                image_url=image_url,
                image_path=image_path,
                image_bytes=image_bytes,
                mime_type=mime_type,
            )
        )

    payload = {
        "model": model or VISION_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt or BOT_SYSTEM_PROMPTS[key]},
            {"role": "user", "content": content},
        ],
        "temperature": temperature,
    }

    res = requests.post(
        f"{XAI_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout_s,
    )
    if res.status_code == 429:
        _mark_vision_exhausted(_parse_retry_after_s(res))
        return ""
    res.raise_for_status()
    body = res.json()

    return body["choices"][0]["message"]["content"].strip()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Scaramouche/Wanderer with vision input.")
    parser.add_argument("bot", choices=sorted(BOT_SYSTEM_PROMPTS.keys()))
    parser.add_argument("prompt", help="Instruction for the bot.")
    parser.add_argument("--image-url", dest="image_url", default=None)
    parser.add_argument("--image", dest="image_path", default=None)
    parser.add_argument("--model", dest="model", default=None)
    args = parser.parse_args()

    answer = ask_character_bot(
        args.bot,
        args.prompt,
        image_url=args.image_url,
        image_path=args.image_path,
        model=args.model,
    )
    print(answer)
