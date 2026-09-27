"""Small, non-identifying companion wire vocabulary and expiring presence model."""

from __future__ import annotations
from dataclasses import dataclass
import json
import math
import time
from .protocol import Rejected

CATEGORIES = {
    "coding",
    "browser",
    "game",
    "media",
    "school",
    "writing",
    "communication",
    "creative",
    "unknown",
}
STATES = {"ACTIVE", "IDLE", "AWAY", "LOCKED", "UNKNOWN"}
CAPABILITIES = {
    "computer_presence",
    "screen_context",
    "desktop_notifications",
    "local_audio",
    "screen_lock",
    "app_launch",
    "url_launch",
    "development_events",
}
EVENTS = {"test_passed", "test_failed", "build_completed", "build_failed"}
NOTIFICATIONS = {
    "test": "Companion notification test.",
    "break": "Take a short break.",
    "build_completed": "Your build finished.",
    "build_failed": "Your build needs attention.",
    "test_passed": "Your tests passed.",
    "test_failed": "Your tests need attention.",
}
ACTION_CAPABILITY = {
    "notify": "desktop_notifications",
    "play": "local_audio",
    "stop": "local_audio",
    "volume": "local_audio",
    "lock": "screen_lock",
    "launch_app": "app_launch",
    "open_url": "url_launch",
    "screen": "screen_context",
    "test": "computer_presence",
}


def presence(value, now=None):
    now = time.time() if now is None else now
    if not isinstance(value, dict) or set(value) != {
        "app",
        "category",
        "duration_seconds",
        "idle_state",
        "updated_at",
        "event",
    }:
        raise Rejected("invalid_presence")
    if (
        value["category"] not in CATEGORIES
        or value["idle_state"] not in STATES
        or value["event"] not in EVENTS | {""}
    ):
        raise Rejected("invalid_presence")
    app = value["app"]
    if not isinstance(app, str) or len(app) > 64 or any(ord(c) < 32 for c in app):
        raise Rejected("invalid_app_label")
    duration, stamp = value["duration_seconds"], value["updated_at"]
    if type(duration) is not int or not 0 <= duration <= 86400 or duration % 300:
        raise Rejected("invalid_duration_bucket")
    if (
        type(stamp) not in (int, float)
        or not math.isfinite(stamp)
        or not now - 120 <= stamp <= now + 5
    ):
        raise Rejected("stale_presence")
    if value["idle_state"] != "ACTIVE":
        return dict(value, app="", category="unknown", duration_seconds=0)
    return dict(value)


def screen_summary(raw):
    """Never retain model-authored free text, titles, identities or screen instructions."""
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        confidence = value.get("confidence")
        category = value.get("category")
        if (
            value.get("sensitive") is not False
            or type(confidence) not in (int, float)
            or not math.isfinite(confidence)
            or not 0.8 <= confidence <= 1
            or category not in CATEGORIES
            or category == "unknown"
        ):
            return "unknown"
        return "Possibly viewing " + category + " content."
    except (ValueError, TypeError, AttributeError):
        return "unknown"


@dataclass
class UserPresenceContext:
    discord_status: str = "unknown"
    active_app: str = ""
    activity_category: str = "unknown"
    active_duration: int = 0
    idle_state: str = "UNKNOWN"
    screen_summary: str = ""
    updated_at: float = 0


def aggregate(local=None, discord=None, screen=None, now=None):
    now = time.time() if now is None else now
    result = UserPresenceContext()
    if discord and 0 <= now - discord.get("updated_at", 0) < 120:
        if discord.get("status") in {"online", "offline", "idle", "dnd"}:
            result.discord_status = discord["status"]
    try:
        data = presence(local, now)
    except (Rejected, TypeError):
        return result
    result.active_app = data["app"]
    result.activity_category = data["category"]
    result.active_duration = data["duration_seconds"]
    result.idle_state = data["idle_state"]
    result.updated_at = data["updated_at"]
    if (
        screen
        and result.idle_state == "ACTIVE"
        and 0 <= now - screen.get("updated_at", 0) < 120
        and screen.get("app") == result.active_app
    ):
        result.screen_summary = screen_summary(screen.get("classification"))
    return result
