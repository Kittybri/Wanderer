from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IntegrationConfig:
    values: dict[str, Any]

    def __repr__(self) -> str:
        return "IntegrationConfig(<redacted>)"

    def section(self, name: str) -> dict[str, Any]:
        value = self.values.get(name, {})
        return dict(value) if isinstance(value, dict) else {}

    def google_account(self, user_id: int) -> dict[str, Any]:
        accounts = self.section("google").get("accounts", {})
        value = accounts.get(str(int(user_id)), {}) if isinstance(accounts, dict) else {}
        return dict(value) if isinstance(value, dict) else {}

    def user_account(self, provider: str, user_id: int, *, owner_id: int | None = None) -> dict[str, Any]:
        """Return one explicitly mapped account, with owner-only legacy fallback."""
        section = self.section(provider)
        accounts = section.get("accounts", {})
        if isinstance(accounts, dict) and accounts:
            value = accounts.get(str(int(user_id)), {})
            if not isinstance(value, dict) or not value:
                return {}
            shared = {
                key: value for key, value in section.items()
                if key not in {"accounts", "access_token", "refresh_token", "expires_at", "user_id"}
            }
            return {**shared, **dict(value)}
        if owner_id is not None and int(user_id) == int(owner_id):
            return section
        return {}

    def configured_account_count(self, provider: str, *, owner_id: int | None = None) -> int:
        section = self.section(provider)
        accounts = section.get("accounts", {})
        if isinstance(accounts, dict) and accounts:
            return sum(1 for value in accounts.values() if isinstance(value, dict) and value)
        return 1 if owner_id is not None and section else 0


def load_integration_config() -> IntegrationConfig:
    """Load one structured JSON value/file. Never logs configuration contents."""
    raw = (os.getenv("BOT_INTEGRATIONS_JSON") or "").strip()
    path = (os.getenv("BOT_INTEGRATIONS_CONFIG") or "").strip()
    try:
        if path:
            raw = Path(path).expanduser().read_text(encoding="utf-8")
        values = json.loads(raw) if raw else {}
    except (OSError, json.JSONDecodeError):
        values = {}
    return IntegrationConfig(values if isinstance(values, dict) else {})
