"""
voice_handler.py - shared Fish Audio / gTTS voice helper.
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import threading
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


_local = threading.local()
# A connection the server dropped while it sat idle: the request never reached Fish, so it is safe to send again.
_RECONNECT_ERRORS = (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError, httpx.WriteError)


def _fish_post(payload: bytes, headers: dict) -> httpx.Response:
    """POST to Fish over a connection kept open per worker thread.

    A new connection (and TLS handshake) for every piece of a reply added to every pause in his speech. A kept
    connection the server has since closed is retried once on a fresh one; timeouts are not retried.
    """
    for attempt in (1, 2):
        client = getattr(_local, "client", None)
        if client is None:
            client = _local.client = httpx.Client(timeout=60, limits=httpx.Limits(keepalive_expiry=30))
        try:
            return client.post(FISH_API_URL, content=payload, headers=headers)
        except _RECONNECT_ERRORS:
            _local.client = None
            client.close()
            if attempt == 2:
                raise


def _fish_tts_blocking(
    text: str,
    api_key: str,
    chunk_length: int = 220,
    *,
    voice_id: str | None = None,
    bot_name: str | None = None,
    speed: float = 1.0,
) -> bytes | None:
    try:
        if _fish_circuit_open():
            print(f"[Fish Audio] circuit open; skipping Fish for {fish_circuit_remaining()}s")
            return None
        reference_id = resolve_voice_id(bot_name=bot_name, voice_id=voice_id)
        request = {
            "text": text[:1500],
            "reference_id": reference_id,
            "format": "mp3",
            "mp3_bitrate": 192,
            "latency": "balanced",
            "normalize": True,
            "chunk_length": chunk_length,
        }
        if speed != 1.0:
            request["prosody"] = {"speed": speed, "volume": 0}
        payload = ormsgpack.packb(request)
        headers = {
            "authorization": f"Bearer {api_key}",
            "content-type": "application/msgpack",
            "model": "s2-pro",
        }
        resp = _fish_post(payload, headers)
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


GTTS_REQUEST_TIMEOUT_S = 15


def _gtts_blocking(text: str) -> bytes:
    from gtts import gTTS

    buf = io.BytesIO()
    gTTS(text=text[:800], lang="en", slow=False, timeout=GTTS_REQUEST_TIMEOUT_S).write_to_fp(buf)
    return buf.getvalue()


async def generate_tts_gtts(text: str) -> bytes | None:
    # gTTS makes its web requests synchronously and with no timeout by default: called directly here it froze the
    # whole bot (every message and the Discord heartbeat) for as long as Google took, so it runs in a worker thread
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _gtts_blocking, text)
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


# How he says it, per voice style: a Fish S2 cue (plain words in square brackets before a sentence, lasting to the
# end of that sentence) and a small speed change. His mood used to be shown by rewriting punctuation, which dropped
# words: in a cold mood "you and I" came out as "you. I". The words are now left alone.
_DELIVERY = {
    "heated": ("angry", 1.04),
    "tense": ("tense", 1.03),
    "combat": ("intense, focused", 1.05),
    "cutting": ("cold, cutting", 0.97),
    "cold": ("cool, distant", 0.98),
    "distant": ("distant", 0.98),
    "jealous": ("irritated, a little jealous", 1.02),
    "mocking": ("dry, teasing", 1.0),
    "duo_teasing": ("teasing", 1.02),
    "curious": ("curious", 1.0),
    "measured": ("measured", 0.98),
    "concerned": ("concerned, gentle", 0.96),
    "soft": ("soft", 0.97),
    "late_night": ("quiet, late at night", 0.95),
    "repair": ("sincere, softer", 0.97),
    "reconciliation": ("softer", 0.97),
    "restrained_vulnerability": ("quiet, a little vulnerable", 0.96),
}


def _expressive() -> bool:
    """VOICE_EMOTION_TAGS=off turns the cues and speed changes off (plain delivery), without a code change."""
    return (os.getenv("VOICE_EMOTION_TAGS") or "on").strip().lower() not in {"off", "0", "false", "no"}


def _delivery(style: str) -> tuple:
    cue, speed = _DELIVERY.get(style, ("", 1.0))
    return (cue, speed) if _expressive() else ("", 1.0)


def _style_tts_text(text: str, style: str = "guarded") -> str:
    # Cues come only from here: square brackets in the reply itself (from the model or a user) are removed, since
    # Fish S2 would take them as instructions.
    cleaned = re.sub(r"\s{2,}", " ", re.sub(r"\[[^\[\]]{0,80}\]", " ", text or "")).strip()
    cue = _delivery(style)[0]
    if not cleaned or not cue:
        return cleaned
    styled = " ".join(f"[{cue}] {sentence}" for sentence in re.split(r"(?<=[.!?…])\s+", cleaned) if sentence)
    # Fish is sent at most 1500 characters: cues never push words out, so a very long text is voiced plainly.
    return styled if len(styled) <= 1500 else cleaned


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

    # chunk_length controls generation/buffering, not real speech speed.
    chunk = 220

    styled_text = _style_tts_text(text, style)
    speed = _delivery(style)[1]

    def _blocking():
        return _fish_tts_blocking(
            styled_text, fish_audio_key, chunk, voice_id=voice_id, bot_name=bot_name, speed=speed
        )

    try:
        audio = await asyncio.get_event_loop().run_in_executor(None, _blocking)
        if audio:
            return audio
        return await generate_tts_gtts(text)
    except Exception as e:
        print(f"[Fish Mooded] {e}")
        return await generate_tts_gtts(text)
