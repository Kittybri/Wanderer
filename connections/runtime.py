"""Dynamic Google authorization layered over the existing protected operation runtime."""
from __future__ import annotations

from contextvars import ContextVar
import inspect

from integration_runtime import CloudIntegrationRuntime, IntegrationResult
from integrations.google_services import GoogleCalendarService, GoogleTasksService, GoogleSheetsService
from integrations.http import IntegrationAuthError, IntegrationError, IntegrationErrorCategory
from .security import ConnectionError


class ConnectedGoogleRuntime(CloudIntegrationRuntime):
    def __init__(self, config, *, owner_id, connections, bot_name, **kwargs):
        super().__init__(config, owner_id=owner_id, **kwargs)
        self.connections = connections
        self.bot_name = bot_name
        self._expected_revision = ContextVar("google_write_revision", default=None)

    def google_services(self, user_id):
        def account(module):
            async def resolve():
                try:
                    expected = self._expected_revision.get()
                    revision = await self.connections.authorize(user_id, self.bot_name, module)
                    if expected is not None and revision != expected:
                        raise ConnectionError("ACCOUNT_CHANGED")
                    token = await self.connections.get_google(user_id, self.bot_name, module)
                    if await self.connections.authorize(user_id, self.bot_name, module) != revision:
                        raise ConnectionError("ACCOUNT_CHANGED")
                    return token
                except ConnectionError as exc:
                    category = (IntegrationErrorCategory.RATE_LIMITED if exc.code in {"REFRESH_BUSY", "REFRESH_BACKOFF", "RATE_LIMITED"}
                                else IntegrationErrorCategory.PROVIDER_UNAVAILABLE if exc.code == "PROVIDER_UNAVAILABLE"
                                else IntegrationErrorCategory.FORBIDDEN if exc.code in {"BOT_DISABLED", "SCOPES_MISSING", "ACCOUNT_CHANGED"}
                                else IntegrationErrorCategory.NOT_CONFIGURED if exc.code in {"NOT_CONNECTED", "NOT_CONFIGURED"}
                                else IntegrationErrorCategory.AUTH_FAILED)
                    raise IntegrationError("Google authorization unavailable; use !google.", category) from None
            return {"token_resolver": resolve}
        # No automatic legacy fallback: disconnect/denied grants must never resurrect authorization.
        # Keep the old application-owned Sheets allowlist outside OAuth, owner-only.
        sheets = self.config.google_account(user_id) if int(user_id) == self.owner_id else {}
        return (
            self._make("calendar", GoogleCalendarService, account("calendar")),
            self._make("tasks", GoogleTasksService, account("tasks")),
            self._make("sheets", GoogleSheetsService, sheets),
        )

    async def _bound_preview(self, method, module, user_id, *args, **kwargs):
        try:
            revision = await self.connections.authorize(user_id, self.bot_name, module)
            result = method(user_id, *args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            if result.ok:
                item = self.pending.get(result.data["request_id"], user_id)
                item.payload["_connection_revision"] = revision
            return result
        except ConnectionError:
            return IntegrationResult("google_" + module, "preview", False, error_category="AUTH_FAILED")

    async def preview_calendar_create(self, user_id, *args, **kwargs):
        return await self._bound_preview(super().preview_calendar_create, "calendar", user_id, *args, **kwargs)

    async def preview_calendar_update(self, user_id, *args, **kwargs):
        return await self._bound_preview(super().preview_calendar_update, "calendar", user_id, *args, **kwargs)

    async def preview_task_create(self, user_id, *args, **kwargs):
        return await self._bound_preview(super().preview_task_create, "tasks", user_id, *args, **kwargs)

    async def preview_task_update(self, user_id, *args, **kwargs):
        return await self._bound_preview(super().preview_task_update, "tasks", user_id, *args, **kwargs)

    async def confirm(self, user_id, request_id, *, provider=None):
        try:
            item = self.pending.get(request_id, user_id, provider=provider)
            if item.provider not in {"google_calendar", "google_tasks"}:
                return await super().confirm(user_id, request_id, provider=provider)
            revision = await self.connections.authorize(user_id, self.bot_name, item.provider.removeprefix("google_"))
            if revision != item.payload.get("_connection_revision"):
                raise ConnectionError("ACCOUNT_CHANGED")
        except (ConnectionError, PermissionError, ValueError):
            return IntegrationResult(provider or "google", "confirm", False, error_category="FORBIDDEN")
        marker = self._expected_revision.set(revision)
        try:
            return await super().confirm(user_id, request_id, provider=provider)
        finally:
            self._expected_revision.reset(marker)

    async def forget(self, user_id):
        self.pending.forget_user(user_id)
        for key in list(self._last_write):
            if key[0] == int(user_id):
                self._last_write.pop(key, None)
