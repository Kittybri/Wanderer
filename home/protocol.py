"""Strict wire protocol and domain-separated HMAC envelopes."""

from __future__ import annotations
import hashlib
import hmac
import json
import math
import re
import secrets
import time
from urllib.parse import urlsplit


class Rejected(ValueError):
    pass


ACTIONS = {
    "power",
    "brightness",
    "color",
    "color_temperature",
    "scene",
    "play",
    "pause",
    "stop",
    "volume",
    "print_note",
    "test",
}
PARAMS = {
    "power": {"on"},
    "brightness": {"value"},
    "color": {"name"},
    "color_temperature": {"mirek"},
    "scene": {"name"},
    "play": {"asset", "volume"},
    "pause": set(),
    "stop": set(),
    "volume": {"value"},
    "print_note": {"template"},
    "test": set(),
}
TRIGGERS = {"manual", "autonomous", "proposal", "alarm", "roommate"}
ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
# No chat content, coordinates, paths, endpoints or arbitrary documents in commands.
NOTES = {
    "posture": "Sit up straight.",
    "birthday": "Happy birthday. Make the day worth remembering.",
    "break": "Take a short break.",
    "reminder": "One thing at a time.",
}


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def secret_ok(value):
    return (
        isinstance(value, str) and len(value) >= 32 and not value.startswith("REPLACE_")
    )


def sign(secret, domain, payload, now=None):
    if not secret_ok(secret):
        raise Rejected("weak_credential")
    body = {
        "nonce": secrets.token_hex(16),
        "timestamp": time.time() if now is None else now,
        "payload": payload,
    }
    body["signature"] = hmac.new(
        secret.encode(), domain.encode() + b"\n" + canonical(body), hashlib.sha256
    ).hexdigest()
    return body


def verify(secret, domain, envelope, now=None):
    now = time.time() if now is None else now
    if (
        not secret_ok(secret)
        or not isinstance(envelope, dict)
        or set(envelope) != {"nonce", "timestamp", "payload", "signature"}
    ):
        raise Rejected("authentication_failed")
    stamp = envelope["timestamp"]
    if (
        type(stamp) not in (int, float)
        or not math.isfinite(stamp)
        or abs(now - stamp) > 30
    ):
        raise Rejected("expired_envelope")
    if not isinstance(envelope["nonce"], str) or not re.fullmatch(
        r"[0-9a-f]{32}", envelope["nonce"]
    ):
        raise Rejected("invalid_nonce")
    body = {k: envelope[k] for k in ("nonce", "timestamp", "payload")}
    expected = hmac.new(
        secret.encode(), domain.encode() + b"\n" + canonical(body), hashlib.sha256
    ).hexdigest()
    if not isinstance(envelope["signature"], str) or not hmac.compare_digest(
        expected, envelope["signature"]
    ):
        raise Rejected("authentication_failed")
    return envelope["payload"]


def secure_url(url, *, websocket=False, mock=False):
    parsed = urlsplit(url)
    schemes = {"wss"} if websocket else {"https"}
    if mock and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        schemes |= {"ws"} if websocket else {"http"}
    if (
        parsed.scheme not in schemes
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise Rejected("tls_url_required")
    return url.rstrip("/")


def command(
    device, action, parameters, user_id, guild_id, bot, trigger="manual", now=None
):
    now = time.time() if now is None else now
    return validate(
        {
            "request_id": secrets.token_hex(16),
            "device_id": device,
            "action": action,
            "parameters": parameters,
            "user_id": int(user_id),
            "guild_id": int(guild_id),
            "bot": bot,
            "trigger": trigger,
            "issued_at": now,
            "expires_at": now + 30,
            "confirmed": False,
        },
        now,
    )


def validate(value, now=None):
    now = time.time() if now is None else now
    fields = {
        "request_id",
        "device_id",
        "action",
        "parameters",
        "user_id",
        "guild_id",
        "bot",
        "trigger",
        "issued_at",
        "expires_at",
        "confirmed",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise Rejected("malformed_command")
    if not isinstance(value["request_id"], str) or not re.fullmatch(
        r"[0-9a-f]{32}", value["request_id"]
    ):
        raise Rejected("invalid_request_id")
    if not isinstance(value["device_id"], str) or not ID.fullmatch(value["device_id"]):
        raise Rejected("invalid_device")
    if (
        value["bot"] not in {"scaramouche", "wanderer"}
        or value["trigger"] not in TRIGGERS
        or type(value["confirmed"]) is not bool
    ):
        raise Rejected("invalid_identity")
    if (
        type(value["user_id"]) is not int
        or value["user_id"] <= 0
        or type(value["guild_id"]) is not int
        or value["guild_id"] < 0
    ):
        raise Rejected("invalid_actor")
    issued, expires = value["issued_at"], value["expires_at"]
    if any(
        type(t) not in (float, int) or not math.isfinite(t) for t in (issued, expires)
    ):
        raise Rejected("invalid_time")
    if (
        issued > now + 5
        or expires <= now
        or not 0 < expires - issued <= 30
        or now - issued > 30
    ):
        raise Rejected("expired_command")
    action = value["action"]
    if (
        action not in ACTIONS
        or not isinstance(value["parameters"], dict)
        or set(value["parameters"]) != PARAMS[action]
    ):
        raise Rejected("unsupported_action_or_parameters")
    p = value["parameters"]
    if action == "power" and type(p["on"]) is not bool:
        raise Rejected("invalid_power")
    for key in ("value", "mirek", "volume"):
        if key in p and (type(p[key]) not in (int, float) or not math.isfinite(p[key])):
            raise Rejected("invalid_numeric_parameter")
    for key in ("name", "asset", "template"):
        if key in p and (not isinstance(p[key], str) or not ID.fullmatch(p[key])):
            raise Rejected("invalid_reference")
    if action == "print_note" and p["template"] not in NOTES:
        raise Rejected("unsupported_document")
    return dict(value, parameters=dict(p))
