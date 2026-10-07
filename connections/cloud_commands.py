"""Calendar/Tasks commands ported from the hardened Scaramouche runtime."""
import json
import re
from integration_runtime import IntegrationResult, parse_user_datetime

_INTEGRATION_ERRORS = {
    "NOT_CONFIGURED": "That account integration is not configured for you.",
    "AUTH_FAILED": "The account authorization has expired or was revoked. Reauthorize it before trying again.",
    "FORBIDDEN": "That account refused access to this operation.",
    "NOT_FOUND": "The requested account item could not be found.",
    "RATE_LIMITED": "That provider is rate-limiting requests. Try again later.",
    "TIMEOUT": "The account provider did not answer in time.",
    "PROVIDER_UNAVAILABLE": "The account provider could not be reached. I am not inventing personal data in its place.",
    "INVALID_REQUEST": "That integration request is invalid or its confirmation expired.",
}


def _integration_error(result: IntegrationResult) -> str:
    return _INTEGRATION_ERRORS.get(
        result.error_category or "",
        "The integration request could not be completed.",
    )


def _proposal_text(result: IntegrationResult) -> str:
    if not result.ok:
        return _integration_error(result)
    data = result.data or {}
    request_id = data.get("request_id", "")
    expires = max(1, int(data.get("expires_in", 600)) // 60)
    preview = json.dumps(data.get("preview") or {}, ensure_ascii=False)[:900]
    return (
        f"Dry-run proposal `{request_id}` (expires in {expires} minutes):\n"
        f"```json\n{preview}\n```\n"
        f"Confirm with the matching provider's `confirm {request_id}` command. "
        "The stored payload—not regenerated prose—will execute once."
    )



def install_google_commands(bot, CLOUD_INTEGRATIONS, _setup, safe_reply):
    @bot.group(name="calendar", invoke_without_command=True)
    async def calendar_cmd(ctx):
        await safe_reply(ctx, (
            "Use `!calendar list <today|tomorrow|week|next N days>`, "
            "`!calendar add START | END | SUMMARY [| DESCRIPTION]`, "
            "`!calendar update EVENT_ID | FIELD | VALUE`, or `!calendar confirm REQUEST_ID`."
        ))


    @calendar_cmd.command(name="list")
    async def calendar_list_cmd(ctx, *, window: str = "week"):
        value = window.strip().lower()
        match = re.fullmatch(r"next\s+(\d{1,2})\s+days?", value)
        normalized = f"next:{min(14, int(match.group(1)))}" if match else (
            value if value in {"today", "tomorrow", "week"} else "week"
        )
        user = await _setup(ctx)
        result = await CLOUD_INTEGRATIONS.calendar_upcoming(
            ctx.author.id, normalized, user.get("timezone_name") or "America/Los_Angeles",
        )
        if not result.ok:
            await safe_reply(ctx, _integration_error(result)); return
        events = result.data["events"]
        if not events:
            await safe_reply(ctx, "The calendar returned no events in that window."); return
        lines = [
            f"• {item['summary']} — {item['start']}" + (" (all day)" if item["all_day"] else "")
            for item in events
        ]
        await safe_reply(ctx, "Calendar:\n" + "\n".join(lines))


    @calendar_cmd.command(name="add")
    async def calendar_add_cmd(ctx, *, request: str = ""):
        parts = [part.strip() for part in request.split("|")]
        if len(parts) < 3:
            await safe_reply(ctx, "Use `!calendar add YYYY-MM-DD HH:MM | YYYY-MM-DD HH:MM | summary [| description]`."); return
        user = await _setup(ctx)
        zone = user.get("timezone_name") or "America/Los_Angeles"
        try:
            start, end = parse_user_datetime(parts[0], zone), parse_user_datetime(parts[1], zone)
        except ValueError as exc:
            await safe_reply(ctx, str(exc)); return
        result = await CLOUD_INTEGRATIONS.preview_calendar_create(
            ctx.author.id, parts[2], start, end, parts[3] if len(parts) > 3 else "",
        )
        await safe_reply(ctx, _proposal_text(result))


    @calendar_cmd.command(name="update")
    async def calendar_update_cmd(ctx, *, request: str = ""):
        parts = [part.strip() for part in request.split("|")]
        if len(parts) < 3 or parts[1].lower() not in {"summary", "description", "start", "end"}:
            await safe_reply(ctx, "Use `!calendar update EVENT_ID | summary|description|start|end | VALUE`."); return
        field, value = parts[1].lower(), parts[2]
        if field in {"start", "end"}:
            user = await _setup(ctx)
            try:
                value = {"dateTime": parse_user_datetime(value, user.get("timezone_name") or "America/Los_Angeles").isoformat()}
            except ValueError as exc:
                await safe_reply(ctx, str(exc)); return
        result = await CLOUD_INTEGRATIONS.preview_calendar_update(ctx.author.id, parts[0], {field: value})
        await safe_reply(ctx, _proposal_text(result))


    @calendar_cmd.command(name="confirm")
    async def calendar_confirm_cmd(ctx, request_id: str = ""):
        result = await CLOUD_INTEGRATIONS.confirm(ctx.author.id, request_id, provider="google_calendar")
        await safe_reply(ctx, "Calendar write completed." if result.ok else _integration_error(result))


    @bot.group(name="tasks", invoke_without_command=True)
    async def tasks_cmd(ctx):
        await safe_reply(ctx, (
            "Use `!tasks list [incomplete|due]`, `!tasks add TITLE [| DUE | NOTES]`, "
            "`!tasks update TASK_ID | title|notes|due|status | VALUE`, or `!tasks confirm REQUEST_ID`."
        ))


    @tasks_cmd.command(name="list")
    async def tasks_list_cmd(ctx, mode: str = "incomplete"):
        user = await _setup(ctx)
        result = await CLOUD_INTEGRATIONS.tasks_list(
            ctx.author.id, "due_week" if mode.lower() in {"due", "week", "soon"} else "incomplete",
            user.get("timezone_name") or "America/Los_Angeles",
        )
        if not result.ok:
            await safe_reply(ctx, _integration_error(result)); return
        items = result.data["tasks"]
        if not items:
            await safe_reply(ctx, "Google Tasks returned no matching incomplete tasks."); return
        await safe_reply(ctx, "Tasks:\n" + "\n".join(
            f"• {item['title']}" + (f" — due {item['due']}" if item["due"] else "")
            for item in items
        ))


    @tasks_cmd.command(name="add")
    async def tasks_add_cmd(ctx, *, request: str = ""):
        parts = [part.strip() for part in request.split("|")]
        if not parts or not parts[0]:
            await safe_reply(ctx, "Use `!tasks add TITLE [| YYYY-MM-DD HH:MM | NOTES]`."); return
        user = await _setup(ctx)
        due = None
        if len(parts) > 1 and parts[1]:
            try:
                due = parse_user_datetime(parts[1], user.get("timezone_name") or "America/Los_Angeles")
            except ValueError as exc:
                await safe_reply(ctx, str(exc)); return
        result = await CLOUD_INTEGRATIONS.preview_task_create(
            ctx.author.id, parts[0], due=due, notes=parts[2] if len(parts) > 2 else "",
        )
        await safe_reply(ctx, _proposal_text(result))


    @tasks_cmd.command(name="update")
    async def tasks_update_cmd(ctx, *, request: str = ""):
        parts = [part.strip() for part in request.split("|")]
        if len(parts) < 3:
            await safe_reply(ctx, "Use `!tasks update TASK_ID | title|notes|due|status | VALUE`."); return
        field, value = parts[1].lower(), parts[2]
        if field == "due":
            user = await _setup(ctx)
            try:
                value = parse_user_datetime(value, user.get("timezone_name") or "America/Los_Angeles")
            except ValueError as exc:
                await safe_reply(ctx, str(exc)); return
        result = await CLOUD_INTEGRATIONS.preview_task_update(ctx.author.id, parts[0], field, value)
        await safe_reply(ctx, _proposal_text(result))


    @tasks_cmd.command(name="confirm")
    async def tasks_confirm_cmd(ctx, request_id: str = ""):
        result = await CLOUD_INTEGRATIONS.confirm(ctx.author.id, request_id, provider="google_tasks")
        await safe_reply(ctx, "Task write completed." if result.ok else _integration_error(result))
