"""Temporary Groq model compatibility shim.

Maps Groq model IDs retired from the free/developer tier to the current
free replacements without changing the rest of the bot logic.
Python imports sitecustomize automatically at startup when this file is on
sys.path, so existing `python bot.py` deployments continue to work.
"""

try:
    from groq.resources.chat.completions import Completions

    _original_create = Completions.create
    _MODEL_MAP = {
        "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
        "llama-3.1-8b-instant": "openai/gpt-oss-20b",
    }

    def _create_with_current_models(self, *args, **kwargs):
        model = kwargs.get("model")
        replacement = _MODEL_MAP.get(model)
        if replacement:
            kwargs["model"] = replacement
        return _original_create(self, *args, **kwargs)

    Completions.create = _create_with_current_models
except Exception as exc:
    print(f"[GROQ_COMPAT] Could not install model mapping: {exc}")
