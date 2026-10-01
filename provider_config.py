"""Explicit Groq model selection without process-wide monkey patches."""

from __future__ import annotations

import os


MODEL_ALIASES = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
    "llama-3.2-11b-vision-preview": "qwen/qwen3.8-27b",
    "llama-3.2-90b-vision-preview": "qwen/qwen3.8-27b",
}


def resolve_groq_model(value: str | None = None, *, default: str = "openai/gpt-oss-120b") -> str:
    configured = (value or os.getenv("GROQ_MODEL") or default).strip()
    return MODEL_ALIASES.get(configured, configured)


GROQ_TEXT_MODEL = resolve_groq_model(os.getenv("GROQ_MODEL_PRIMARY"))
GROQ_LIGHT_MODEL = resolve_groq_model(
    os.getenv("GROQ_MODEL_LIGHT"), default="openai/gpt-oss-20b"
)
GROQ_VISION_MODEL = resolve_groq_model(
    os.getenv("GROQ_VISION_MODEL"), default="qwen/qwen3.8-27b"
)
