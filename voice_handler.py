"""
voice_handler.py - shared Fish Audio / gTTS voice helper.
"""

from __future__ import annotations

import asyncio
import io
import os
import time

import httpx
import ormsgpack

VOICE_ID = "fb95ab47841a4db189cb35fb619d4ea1"
FISH_API_URL = "https://api.fish.audio/v1/tts"
FISH_CIRCUIT_FAILURES = int(os.getenv("FISH_CIRCUIT_FAILURES", "3") or "3")
FISH_CIRCUIT_COOLDOWN_S = int(os.getenv("FISH_CIRCUIT_COOLDOWN_S", "300") or "300")

_fish_failure_count = 0
_fish_open_until = 0.0


def fish_circuit_remaining() -> int:
    return max(0, int(_fish_open_until - time.time()))


def _fish_circuit_open() -> bool:
    return fish_circuit_remaining() > 0


def _fish_mark_success() -> None:
    global _fish_failure_count, _fish_open_until
    _fish_failure_count = 0
    _fish_open_until = 0.0


def _fish_mark_failure(reason: str) -> None:
    global _fish_failure_count, _fish_open_until
    _fish_failure_count += 1
    if _fish_failure_count >= FISH_CIRCUIT_FAILURES:
        _fish_open_until = max(_fish_open_until, time.time() + FISH_CIRCUIT_COOLDOWN_S)
        print(f"[Fish Audio] circuit open for {FISH_CIRCUIT_COOLDOWN_S}s after failures: {reason[:120]}")


def resolve_voice_id(bot_name: str | None = None, voice_id: str | None = None) -> str:
    explicit = (voice_id or "").strip()
    if explicit:
        return explicit

    key = (bot_name or "").strip().lower()
    if key == "scaramouche":
        env_names = (
            "SCARAMOUCHE_FISH_VOICE_ID",
            "SCARAMOUCHE_VOICE_ID",
            "FISH_AUDIO_REFERENCE_ID",
            "FISH_REFERENCE_ID",
        )
    elif key == "wanderer":
        env_names = (
            "WANDERER_FISH_VOICE_ID",
            "WANDERER_VOICE_ID",
            "FISH_AUDIO_REFERENCE_ID",
            "FISH_REFERENCE_ID",
        )
    else:
        env_names = ("FISH_AUDIO_REFERENCE_ID", "FISH_REFERENCE_ID")

    for env_name in env_names:
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value
    return VOICE_ID


def _fish_tts_blocking(
    text: str,
    api_key: str,
    chunk_length: int = 220,
    *,
    voice_id: str | None = None,
    bot_name: str | None = None,
) -> bytes | None:
    try:
        if _fish_circuit_open():
            print(f"[Fish Audio] circuit open; skipping Fish for {fish_circuit_remaining()}s")
            return None
        reference_id = resolve_voice_id(bot_name=bot_name, voice_id=voice_id)
        payload = ormsgpack.packb(
            {
                "text": text[:1500],
                "reference_id": reference_id,
                "format": "mp3",
                "mp3_bitrate": 192,
                "latency": "balanced",
                "normalize": True,
                "chunk_length": chunk_length,
            }
        )
        headers = {
            "authorization": f"Bearer {api_key}",
            "content-type": "application/msgpack",
            "model": "s2-pro",
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(FISH_API_URL, content=payload, headers=headers)
        if resp.status_code == 200:
            print(f"[Fish Audio] OK {len(resp.content):,} bytes")
            _fish_mark_success()
            return resp.content
        print(f"[Fish Audio] HTTP {resp.status_code}: {resp.text[:200]}")
        if resp.status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
            _fish_mark_failure(f"HTTP {resp.status_code}")
        return None
    except Exception as e:
        print(f"[Fish Audio] {type(e).__name__}: {e}")
        _fish_mark_failure(str(e))
        return None


async def generate_tts_fish_audio(
    text: str,
    api_key: str,
    chunk_length: int = 220,
    *,
    voice_id: str | None = None,
    bot_name: str | None = None,
) -> bytes | None:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: _fish_tts_blocking(text, api_key, chunk_length, voice_id=voice_id, bot_name=bot_name),
    )


async def generate_tts_gtts(text: str) -> bytes | None:
    try:
        from gtts import gTTS

        buf = io.BytesIO()
        gTTS(text=text[:800], lang="en", slow=False).write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"[gTTS] {e}")
        return None


async def get_audio(
    text: str,
    fish_audio_key: str,
    *,
    voice_id: str | None = None,
    bot_name: str | None = None,
) -> bytes | None:
    if fish_audio_key:
        audio = await generate_tts_fish_audio(text, fish_audio_key, voice_id=voice_id, bot_name=bot_name)
        if audio:
            return audio
    return await generate_tts_gtts(text)


def _style_tts_text(text: str, style: str = "guarded") -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if style == "soft":
        return cleaned.replace("...", ".  ").replace(" - ", ". ")
    if style == "late_night":
        return cleaned.replace("...", ", ").replace(" - ", ", ").replace(";", ", ")
    if style == "repair":
        return cleaned.replace("...", ". ").replace(" but ", ", but ")
    if style == "tense":
        return cleaned.replace(",", ". ").replace(";", ". ")
    if style == "combat":
        return cleaned.replace(",", ". ").replace(" and ", ". ").replace(" but ", ". ")
    if style == "duo_teasing":
        return cleaned.replace("...", ". ").replace(";", ". ").replace(" and ", ", ")
    if style == "jealous":
        return cleaned.replace(",", ". ").replace("...", ". ").replace(" and ", ". ")
    if style in {"cutting", "distant"}:
        return cleaned.replace(" and ", ". ").replace(" but ", ". ")
    if style in {"measured", "curious"}:
        return cleaned.replace("...", ", ")
    return cleaned


async def get_audio_mooded(
    text: str,
    fish_audio_key: str,
    mood: int = 0,
    style: str = "guarded",
    *,
    voice_id: str | None = None,
    bot_name: str | None = None,
) -> bytes | None:
    if not fish_audio_key:
        return await generate_tts_gtts(text)

    if mood <= -6:
        chunk = 140
    elif mood <= -1:
        chunk = 190
    elif mood <= 5:
        chunk = 220
    else:
        chunk = 260

    if style == "soft":
        chunk += 35
    elif style == "late_night":
        chunk += 45
    elif style == "repair":
        chunk += 20
    elif style == "tense":
        chunk = max(120, chunk - 30)
    elif style == "combat":
        chunk = max(110, chunk - 45)
    elif style == "duo_teasing":
        chunk = max(125, chunk - 15)
    elif style == "jealous":
        chunk = max(120, chunk - 25)
    elif style in {"cutting", "distant"}:
        chunk = max(130, chunk - 20)
    elif style in {"measured", "curious"}:
        chunk += 10

    styled_text = _style_tts_text(text, style)

    def _blocking():
        return _fish_tts_blocking(styled_text, fish_audio_key, chunk, voice_id=voice_id, bot_name=bot_name)

    try:
        audio = await asyncio.get_event_loop().run_in_executor(None, _blocking)
        if audio:
            return audio
        return await generate_tts_gtts(text)
    except Exception as e:
        print(f"[Fish Mooded] {e}")
        return await generate_tts_gtts(text)
