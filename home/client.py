"""Bot-side transport; one signed call, no unsafe automatic retry of actions."""

from __future__ import annotations
import asyncio
import aiohttp
from .protocol import sign, secure_url, Rejected


class HomeClient:
    def __init__(self, name, config):
        self.name = name
        self.config = config

    @property
    def enabled(self):
        return bool(self.config.get("enabled", False))

    async def call(self, operation, user_id, **values):
        if not self.enabled:
            return {"ok": False, "error": "home_not_configured"}
        try:
            base = secure_url(
                self.config.get("url", ""), mock=self.config.get("mock", False)
            )
            envelope = sign(
                self.config.get("secret", ""),
                "rpc:" + self.name,
                dict(values, op=operation, user_id=int(user_id)),
            )
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=8 if operation.startswith("pc_") else 40)
            ) as session:
                async with session.post(
                    base + "/rpc/" + self.name, json=envelope, allow_redirects=False
                ) as response:
                    if response.status != 200:
                        return {"ok": False, "error": "home_unavailable"}
                    result = await response.json()
                    return (
                        result
                        if isinstance(result, dict)
                        else {"ok": False, "error": "invalid_response"}
                    )
        except (Rejected, aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return {"ok": False, "error": "home_unavailable"}
