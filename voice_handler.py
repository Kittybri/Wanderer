"""
voice_handler.py — Wanderer Bot
Voice ID: 4bae40a07d1e46d1846c044c7b540ae5
"""

import io
import asyncio
import httpx
import ormsgpack

WANDERER_VOICE_ID = "4bae40a07d1e46d1846c044c7b540ae5"
FISH_API_URL      = "https://api.fish.audio/v1/tts"


def _fish_tts_blocking(text: str, api_key: str, chunk_length: int = 220) -> bytes | None:
    try:
        payload = ormsgpack.packb({
            "text":         text[:1500],
            "reference_id": WANDERER_VOICE_ID,
            "format":       "mp3",
            "mp3_bitrate":  192,
            "latency":      "balanced",
            "normalize":    True,
            "chunk_length": chunk_length,
        })
        headers = {
            "authorization": f"Bearer {api_key}",
            "content-type":  "application/msgpack",
            "model":         "s2-pro",
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(FISH_API_URL, content=payload, headers=headers)
        if resp.status_code == 200:
            print(f"[Fish Audio] ✓ {len(resp.content):,} bytes")
            return resp.content
        print(f"[Fish Audio] HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    except Exception as e:
        print(f"[Fish Audio] {type(e).__name__}: {e}")
        return None


async def generate_tts_fish_audio(text: str, api_key: str, chunk_length: int = 220) -> bytes | None:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fish_tts_blocking, text, api_key, chunk_length)


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


async def get_audio(text: str, fish_audio_key: str) -> bytes | None:
    if fish_audio_key:
        audio = await generate_tts_fish_audio(text, fish_audio_key)
        if audio: return audio
    return await generate_tts_gtts(text)


async def get_audio_mooded(text: str, fish_audio_key: str, mood: int = 0) -> bytes | None:
    if not fish_audio_key:
        return await generate_tts_gtts(text)
    # Mood affects pacing
    if mood <= -6:   chunk = 140
    elif mood <= -1: chunk = 190
    elif mood <= 5:  chunk = 220
    else:            chunk = 260

    def _blocking():
        return _fish_tts_blocking(text, fish_audio_key, chunk)

    try:
        audio = await asyncio.get_event_loop().run_in_executor(None, _blocking)
        if audio: return audio
        return await generate_tts_gtts(text)
    except Exception as e:
        print(f"[Fish Mooded] {e}")
        return await generate_tts_gtts(text)
