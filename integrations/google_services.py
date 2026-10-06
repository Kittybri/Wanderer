from __future__ import annotations

import time
from datetime import datetime
from .http import AsyncJSONClient, IntegrationAuthError, IntegrationError


class _GoogleBase:
    def __init__(self, account: dict, client: AsyncJSONClient | None = None):
        self.account = dict(account)
        self.client = client or AsyncJSONClient()

    @property
    def ready(self) -> bool:
        return bool(self.account.get("token_resolver") or self.account.get("access_token") or self.account.get("refresh_token"))

    async def _token(self) -> str:
        if self.account.get("token_resolver"):
            return await self.account["token_resolver"]()
        token = str(self.account.get("access_token") or "")
        if token and float(self.account.get("expires_at") or 0) > time.time() + 30:
            return token
        refresh = str(self.account.get("refresh_token") or "")
        if not refresh:
            raise IntegrationAuthError("Google account is not authorized")
        if not self.account.get("client_id") or not self.account.get("client_secret"):
            raise IntegrationAuthError("Google refresh credentials are incomplete")
        try:
            result = await self.client.request("POST", "https://oauth2.googleapis.com/token", data={
                "client_id":self.account.get("client_id", ""), "client_secret":self.account.get("client_secret", ""),
                "refresh_token":refresh, "grant_type":"refresh_token",
            })
        except IntegrationError as exc:
            raise IntegrationAuthError("Google token refresh was rejected") from exc
        self.account["access_token"] = result.get("access_token", "")
        if not self.account["access_token"]:
            raise IntegrationAuthError("Google token refresh returned no access token")
        self.account["expires_at"] = time.time() + int(result.get("expires_in", 3600))
        return str(self.account["access_token"])

    async def _headers(self) -> dict:
        return {"Authorization": f"Bearer {await self._token()}", "Content-Type":"application/json"}


class GoogleTasksService(_GoogleBase):
    async def list_tasks(self, tasklist: str = "@default", *, show_completed: bool = False,
                         max_results: int = 20) -> dict:
        from urllib.parse import quote, urlencode
        query = urlencode({
            "showCompleted": str(bool(show_completed)).lower(),
            "showHidden": "false",
            "maxResults": max(1, min(50, int(max_results))),
        })
        return await self.client.request(
            "GET",
            f"https://tasks.googleapis.com/tasks/v1/lists/{quote(tasklist, safe='')}/tasks?{query}",
            headers=await self._headers(),
        )

    async def create_task(self, title: str, *, notes: str = "", due: datetime | None = None, tasklist: str = "@default") -> dict:
        if not str(title).strip():
            raise ValueError("task title is required")
        payload = {"title":title[:250], "notes":notes[:2000]}
        if due:
            if due.tzinfo is None:
                raise ValueError("due datetime must include a timezone")
            payload["due"] = due.isoformat()
        from urllib.parse import quote
        return await self.client.request("POST", f"https://tasks.googleapis.com/tasks/v1/lists/{quote(tasklist, safe='')}/tasks", headers=await self._headers(), json=payload)

    async def update_task(self, task_id: str, changes: dict, tasklist: str = "@default") -> dict:
        allowed = {key:value for key, value in changes.items() if key in {"title", "notes", "due", "status"}}
        if not str(task_id).strip() or not allowed:
            raise ValueError("task_id and at least one supported change are required")
        if "title" in allowed and not str(allowed["title"]).strip():
            raise ValueError("task title cannot be empty")
        if "status" in allowed and allowed["status"] not in {"completed", "needsAction"}:
            raise ValueError("unsupported task status")
        if "due" in allowed:
            due = allowed["due"]
            if isinstance(due, datetime):
                if due.tzinfo is None:
                    raise ValueError("due datetime must include a timezone")
                allowed["due"] = due.isoformat()
            elif isinstance(due, str):
                parsed = datetime.fromisoformat(due.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("due datetime must include a timezone")
            else:
                raise ValueError("due must be a timezone-aware datetime or ISO string")
        from urllib.parse import quote
        return await self.client.request("PATCH", f"https://tasks.googleapis.com/tasks/v1/lists/{quote(tasklist, safe='')}/tasks/{quote(str(task_id), safe='')}", headers=await self._headers(), json=allowed)


class GoogleCalendarService(_GoogleBase):
    async def upcoming(self, *, calendar_id: str = "primary", time_min: datetime,
                       time_max: datetime | None = None, max_results: int = 20) -> dict:
        if time_min.tzinfo is None or (time_max is not None and time_max.tzinfo is None):
            raise ValueError("calendar bounds must include a timezone")
        if time_max is not None and time_max <= time_min:
            raise ValueError("time_max must be after time_min")
        from urllib.parse import quote, urlencode
        query_values = {
            "timeMin": time_min.isoformat(), "singleEvents": "true",
            "orderBy": "startTime", "maxResults": max(1, min(50, int(max_results))),
        }
        if time_max is not None:
            query_values["timeMax"] = time_max.isoformat()
        query = urlencode(query_values)
        return await self.client.request("GET", f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events?{query}", headers=await self._headers())

    async def get_event(self, event_id: str, *, calendar_id: str = "primary") -> dict:
        from urllib.parse import quote
        if not str(event_id).strip():
            raise ValueError("event_id is required")
        return await self.client.request(
            "GET",
            f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events/{quote(str(event_id), safe='')}",
            headers=await self._headers(),
        )

    async def create_event(self, summary: str, start: datetime, end: datetime, *, calendar_id: str = "primary", description: str = "", confirmed: bool = False) -> dict:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("calendar datetimes must include a timezone")
        if not str(summary).strip():
            raise ValueError("calendar summary is required")
        if end <= start:
            raise ValueError("calendar end must be after start")
        from urllib.parse import quote
        payload = {"summary":summary[:250], "description":description[:2000], "start":{"dateTime":start.isoformat()}, "end":{"dateTime":end.isoformat()},
                   "extendedProperties":{"private":{"created_by":"scara-wanderer-bots"}}}
        if not confirmed:
            return {"dry_run": True, "operation": "create_event", "payload": payload}
        return await self.client.request("POST", f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events", headers=await self._headers(), json=payload)

    async def update_bot_event(self, event_id: str, existing_event: dict, changes: dict, *, calendar_id: str = "primary", confirmed: bool = False) -> dict:
        marker = existing_event.get("extendedProperties", {}).get("private", {}).get("created_by")
        if marker != "scara-wanderer-bots":
            raise PermissionError("only bot-created events may be updated")
        from urllib.parse import quote
        allowed = {key:value for key, value in changes.items() if key in {"summary", "description", "start", "end"}}
        if not str(event_id).strip() or not allowed:
            raise ValueError("event_id and at least one supported change are required")
        if "summary" in allowed and not str(allowed["summary"]).strip():
            raise ValueError("calendar summary cannot be empty")
        for key in ("start", "end"):
            value = allowed.get(key)
            if value and isinstance(value, dict) and value.get("dateTime"):
                parsed = datetime.fromisoformat(str(value["dateTime"]).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("calendar datetimes must include a timezone")
        if not confirmed:
            return {"dry_run": True, "operation": "update_event", "event_id": event_id, "changes": allowed}
        return await self.client.request("PATCH", f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events/{quote(str(event_id), safe='')}", headers=await self._headers(), json=allowed)


class GoogleSheetsService(_GoogleBase):
    async def append_score_rows(self, spreadsheet_id: str, rows: list[list[object]], *, range_name: str = "Scores!A:D") -> dict:
        if not spreadsheet_id or not rows:
            raise ValueError("spreadsheet and rows are required")
        allowed_ids = {str(item) for item in self.account.get("allowed_spreadsheets", []) if item}
        if spreadsheet_id not in allowed_ids:
            raise PermissionError("spreadsheet is not allowlisted for scoreboard writes")
        from urllib.parse import quote, urlencode
        query = urlencode({"valueInputOption":"USER_ENTERED", "insertDataOption":"INSERT_ROWS"})
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{quote(range_name, safe='')}:append?{query}"
        return await self.client.request("POST", url, headers=await self._headers(), json={"values":rows[:100]})
