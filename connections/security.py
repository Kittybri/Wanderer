"""Small fail-closed configuration and authenticated credential envelope."""
from __future__ import annotations

import base64
import ipaddress
import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from nacl.secret import SecretBox


class ConnectionError(RuntimeError):
    """Only fixed, public-safe error codes may cross the service boundary."""
    def __init__(self, code="UNAVAILABLE"):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Settings:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    redirect_uri: str
    master_key: str = field(repr=False)

    @classmethod
    def from_env(cls):
        return cls(*(os.getenv(key, "").strip() for key in (
            "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
            "GOOGLE_OAUTH_REDIRECT_URI", "CONNECTIONS_MASTER_KEY")))

    def validate(self):
        try:
            parsed = urlsplit(self.redirect_uri)
            host = parsed.hostname or ""
            if (parsed.scheme != "https" or not host or "." not in host or
                    parsed.username or parsed.password or parsed.query or parsed.fragment or
                    parsed.path != "/oauth/google/callback" or parsed.port not in (None, 443)):
                raise ValueError()
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ValueError()
            if host.endswith((".localhost", ".local")) or not self.client_id or not self.client_secret:
                raise ValueError()
            Cipher(self.master_key)
        except (ValueError, ConnectionError):
            raise ConnectionError("NOT_CONFIGURED") from None

    @property
    def origin(self):
        parsed = urlsplit(self.redirect_uri)
        return f"{parsed.scheme}://{parsed.netloc}"


class Cipher:
    """libsodium SecretBox; authenticated envelope binds ciphertext to its owner/purpose."""
    def __init__(self, key):
        try:
            raw = base64.b64decode(key, altchars=b"-_", validate=True)
            if len(raw) != SecretBox.KEY_SIZE:
                raise ValueError()
            self.box = SecretBox(raw)
        except Exception:
            raise ConnectionError("ENCRYPTION_UNAVAILABLE") from None

    def seal(self, value, context):
        raw = json.dumps({"v": 1, "context": context, "value": value}, separators=(",", ":")).encode()
        return bytes(self.box.encrypt(raw))

    def open(self, value, context):
        try:
            envelope = json.loads(self.box.decrypt(value))
            if envelope["v"] != 1 or envelope["context"] != context:
                raise ValueError()
            return envelope["value"]
        except Exception:
            raise ConnectionError("ENCRYPTION_UNAVAILABLE") from None
