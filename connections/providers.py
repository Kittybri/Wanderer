"""Provider protocol and the Phase 1 Google adapter. No arbitrary endpoint execution."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from typing import Protocol
from urllib.parse import urlencode
import aiohttp

from .security import ConnectionError

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
TASKS_SCOPE = "https://www.googleapis.com/auth/tasks"
SCOPES = ("openid", "email", CALENDAR_SCOPE, TASKS_SCOPE)
MODULE_SCOPES = {"calendar": CALENDAR_SCOPE, "tasks": TASKS_SCOPE}


class Provider(Protocol):
    name: str
    module_scopes: dict
    def authorization_url(self, state: str, verifier: str) -> str: ...
    async def exchange(self, code: str, verifier: str) -> dict: ...
    async def identity(self, token: str) -> dict: ...
    async def refresh(self, token: str) -> dict: ...
    async def revoke(self, token: str) -> bool: ...


def masked_email(identity):
    email = str(identity.get("email", ""))
    if (identity.get("email_verified") is not True or not isinstance(identity.get("sub"), str)
            or not 1 <= len(identity["sub"]) <= 255):
        raise ConnectionError("IDENTITY_UNVERIFIED")
    if len(email) > 254 or not re.fullmatch(r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9.-]+", email):
        raise ConnectionError("IDENTITY_UNVERIFIED")
    # Neither names, subject IDs, nor the email domain are displayed as trusted prose.
    return email[0].lower() + "***@***"


class GoogleProvider:
    name = "google"
    module_scopes = MODULE_SCOPES

    def __init__(self, settings):
        self.settings = settings

    def authorization_url(self, state, verifier):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": self.settings.client_id, "redirect_uri": self.settings.redirect_uri,
            "response_type": "code", "access_type": "offline", "include_granted_scopes": "true",
            "prompt": "consent select_account", "scope": " ".join(SCOPES), "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256",
        })

    async def _request(self, method, url, *, data=None, headers=None, revoke=False):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                async with session.request(method, url, data=data, headers=headers, allow_redirects=False) as response:
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        raw.extend(chunk)
                        if len(raw) > 65536:
                            raise ConnectionError("PROVIDER_UNAVAILABLE")
                    if revoke:
                        return response.status == 200
                    result = json.loads(raw)
                    if not isinstance(result, dict):
                        raise ValueError()
                    if response.status != 200:
                        if result.get("error") == "invalid_grant":
                            raise ConnectionError("REAUTH_REQUIRED")
                        raise ConnectionError("PROVIDER_UNAVAILABLE")
                    return result
        except ConnectionError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, UnicodeError):
            raise ConnectionError("PROVIDER_UNAVAILABLE") from None

    async def exchange(self, code, verifier):
        return await self._request("POST", "https://oauth2.googleapis.com/token", data={
            "client_id": self.settings.client_id, "client_secret": self.settings.client_secret,
            "redirect_uri": self.settings.redirect_uri, "grant_type": "authorization_code",
            "code": code, "code_verifier": verifier,
        })

    async def identity(self, token):
        return await self._request("GET", "https://openidconnect.googleapis.com/v1/userinfo",
                                   headers={"Authorization": "Bearer " + token})

    async def refresh(self, token):
        return await self._request("POST", "https://oauth2.googleapis.com/token", data={
            "client_id": self.settings.client_id, "client_secret": self.settings.client_secret,
            "grant_type": "refresh_token", "refresh_token": token,
        })

    async def revoke(self, token):
        return await self._request("POST", "https://oauth2.googleapis.com/revoke",
                                   data={"token": token}, revoke=True)
