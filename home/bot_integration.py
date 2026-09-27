"""Discord-facing adapter: commands, existing scheduler hooks, optional current-TTS output."""

from __future__ import annotations
import asyncio
import base64
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands
from .client import HomeClient
from .protocol import command, Rejected, ID

SIGNALS = {"irritated", "calm_night", "birthday"}


def quiet(user, now=None):
    local = (now or datetime.now(ZoneInfo(user.get("timezone_name") or "UTC"))).hour
    start = int(user.get("quiet_hours_start", 23))
    end = int(user.get("quiet_hours_end", 8))
    if start == end:
        return False
    return start <= local < end if start < end else local >= start or local < end


def candidate(name, user, rules, now=None):
    now = now or datetime.now(ZoneInfo(user.get("timezone_name") or "UTC"))
    if not user.get("home_actions_enabled", False) or not user.get("proactive", False):
        return None
    for rule in rules[:8]:
        signal = rule.get("signal")
        matched = (
            signal == "irritated"
            and int(user.get("mood", 0)) <= -5
            or signal == "calm_night"
            and int(user.get("mood", 0)) >= 3
            and now.hour >= 21
            or signal == "birthday"
            and name == "scaramouche"
            and now.month == 1
            and now.day == 3
        )
        if signal not in SIGNALS or not matched:
            continue
        return {
            "device": rule.get("device"),
            "action": rule.get("action"),
            "parameters": rule.get("parameters", {}),
        }
    return None


def location_line(name, event):
    # Deliberately exclude zone names, coordinates, inferred routines and long-term profiles.
    if name == "scaramouche":
        return (
            "Your arrival update came through. Now accomplish something."
            if event["kind"] == "location.entered"
            else "Your departure update came through. Try not to embarrass yourself."
        )
    return (
        "Your arrival update came through. Made it there safely?"
        if event["kind"] == "location.entered"
        else "Saw your departure update. Take care."
    )


class HomeBot:
    def __init__(self, name, bot, mem, config, tts, owner_id=0, self_store=None):
        self.name = name
        self.bot = bot
        self.mem = mem
        self.config = config
        self.tts = tts
        self.owner_id = int(owner_id or 0)
        self.client = HomeClient(name, config)
        self.self_store = self_store
        self.next_tick = 0
        self.tick_running = False

    async def action(self, uid, gid, device, action, parameters, trigger="manual"):
        try:
            c = command(device, action, parameters, uid, gid, self.name, trigger)
        except (Rejected, ValueError, TypeError):
            return {"ok": False, "error": "invalid_action"}
        result = await self.client.call("action", uid, command=c)
        if result.get("ok") and result.get("result") == "completed" and self.self_store:
            try:
                await self.self_store.record_event(
                    "home_action",
                    "A pre-authorized home action completed.",
                    importance=1,
                    related_user_id=uid,
                    dedupe_key="home:" + c["request_id"],
                )
            except Exception:
                pass  # A memory failure must not turn a completed physical action into a retry.
        return result

    async def speak(self, uid, device, text, user, trigger="manual", guild_id=0):
        if not self.client.enabled or not device or not ID.fullmatch(device):
            return {"ok": False, "error": "home_not_configured"}
        if trigger != "alarm" and quiet(user):
            return {"ok": False, "error": "quiet_hours"}
        if not user.get("voice_enabled", True):
            return {"ok": False, "error": "voice_disabled"}
        # Reuse current emotion-aware TTS. Never forward credentials or internal labels.
        if (
            not text
            or len(text) > 240
            or re.search(
                r"password|token|api.?key|embedding|SYSTEM:|CONTEXT:", text, re.I
            )
        ):
            return {"ok": False, "error": "audio_content_denied"}
        audio = await self.tts(
            text,
            user.get("mood", 0),
            user=user,
            delivery_intent="gentle",
            voice_key=uid,
        )
        if not audio:
            return {"ok": False, "error": "tts_unavailable"}
        mime = (
            "audio/wav"
            if audio.startswith(b"RIFF")
            else "audio/ogg" if audio.startswith(b"OggS") else "audio/mpeg"
        )
        uploaded = await self.client.call(
            "audio", uid, data=base64.b64encode(audio).decode(), mime=mime
        )
        if not uploaded.get("ok"):
            return uploaded
        return await self.action(
            uid,
            guild_id,
            device,
            "play",
            {"asset": uploaded["asset"], "volume": 0.25},
            trigger,
        )

    async def roommate(self, uid, text, user):
        if not self.client.enabled:
            return
        prefs = await self.mem.get_user_preferences(uid)
        device = prefs.get("voice_output_target", "")
        if not device or quiet(user or {}):
            return
        allowed, _ = await self.mem.consume_shared_cooldown(
            f"home_roommate:{self.name}:{uid}", 900
        )
        if allowed:
            await self.speak(uid, device, text[:240], user or {}, "roommate")

    async def tick(self):
        if hasattr(self, "companion"):
            await self.companion.tick()
        if (
            not self.client.enabled
            or self.tick_running
            or time.monotonic() < self.next_tick
        ):
            return
        self.next_tick = time.monotonic() + 60
        self.tick_running = True
        try:
            for raw_uid, settings in list(self.config.get("users", {}).items())[:10]:
                uid = int(raw_uid)
                user = await self.mem.get_user(uid)
                if not user:
                    continue
                if user.get("home_presence_enabled", False):
                    result = await self.client.call("events", uid)
                    if (
                        result.get("ok")
                        and result.get("events")
                        and user.get("proactive")
                        and user.get("allow_dms")
                        and not quiet(user)
                    ):
                        allowed, _ = await self.mem.consume_shared_cooldown(
                            f"home_presence:{uid}", 3600
                        )
                        if (
                            allowed
                            and await self.mem.respects_dm_timing(uid)
                            and await self.mem.can_dm_user(uid, 3600)
                        ):
                            target = await self.bot.fetch_user(uid)
                            await target.send(
                                location_line(self.name, result["events"][0]),
                                allowed_mentions=discord.AllowedMentions.none(),
                            )
                            await self.mem.set_dm_sent(uid)
                if user.get("home_actions_enabled") and not quiet(user):
                    proposal = candidate(self.name, user, settings.get("rules", []))
                    if proposal:
                        allowed, _ = await self.mem.consume_shared_cooldown(
                            f"home_mood:{uid}:{proposal['device']}", 900
                        )
                        if allowed:
                            await self.action(
                                uid,
                                0,
                                proposal["device"],
                                proposal["action"],
                                proposal["parameters"],
                                "autonomous",
                            )
                # Administrator-configured alarm time plus explicit user alarm opt-in.
                local = datetime.now(ZoneInfo(user.get("timezone_name") or "UTC"))
                for alarm in settings.get("alarms", [])[:3]:
                    if not user.get("home_alarms_enabled"):
                        break
                    if alarm.get("time") != local.strftime("%H:%M"):
                        continue
                    device = alarm.get("device", "")
                    allowed, _ = await self.mem.consume_shared_cooldown(
                        f"home_alarm:{self.name}:{uid}:{device}:{local.date()}", 86400
                    )
                    if allowed:
                        await self.speak(uid, device, "Wake up.", user, "alarm")
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # Home failures do not interrupt existing Discord scheduler work.
        finally:
            self.tick_running = False

    def install(self):
        async def say(ctx, value):
            await ctx.reply(
                value[:1800],
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        @self.bot.group(name="home", invoke_without_command=True)
        async def home(ctx):
            await say(
                ctx,
                "Home: location on/off/delete · actions on/off · alarms on/off · output <device|off> · do <device> <action> <JSON> · confirm <id> · speak <device> <text>. Owner: status/devices/agent/permissions/audit/test/disable/enable.",
            )

        @home.command(name="location")
        async def location(ctx, mode: str):
            if ctx.guild:
                await say(
                    ctx, "Location settings are private. Use this command in a DM."
                )
                return
            if mode not in {"on", "off", "delete"}:
                return
            if mode in {"off", "delete"}:
                await self.mem.set_user_preference(
                    ctx.author.id, "home_presence_enabled", 0
                )
            result = await self.client.call("location_" + mode, ctx.author.id)
            if result.get("ok") and mode == "on":
                await self.mem.set_user_preference(
                    ctx.author.id, "home_presence_enabled", 1
                )
            await say(
                ctx,
                (
                    "Location " + mode + "."
                    if result.get("ok")
                    else (
                        "Home service unavailable. Local reactions are off; retry to update/delete the server record."
                        if mode != "on"
                        else "Location was not enabled."
                    )
                ),
            )

        @home.command(name="actions")
        async def actions(ctx, mode: str):
            if mode in {"on", "off"}:
                await self.mem.set_user_preference(
                    ctx.author.id, "home_actions_enabled", int(mode == "on")
                )
                await say(
                    ctx,
                    "Character action suggestions "
                    + mode
                    + ". Device permissions still apply.",
                )

        @home.command(name="alarms")
        async def alarms(ctx, mode: str):
            if mode in {"on", "off"}:
                await self.mem.set_user_preference(
                    ctx.author.id, "home_alarms_enabled", int(mode == "on")
                )
                await say(ctx, "Configured home alarms " + mode + ".")

        @home.command(name="output")
        async def output(ctx, device: str):
            if ctx.guild:
                await say(ctx, "Configure private speaker output in a DM.")
                return
            if device != "off" and not ID.fullmatch(device):
                return
            await self.mem.set_user_preference(
                ctx.author.id, "voice_output_target", "" if device == "off" else device
            )
            await say(
                ctx,
                "Roommate output "
                + (
                    "off."
                    if device == "off"
                    else "requested. Only pre-authorized device policy can permit it."
                ),
            )

        @home.command(name="do")
        @commands.cooldown(1, 10, commands.BucketType.user)
        async def do(ctx, device: str, action: str, *, parameters: str = "{}"):
            try:
                values = json.loads(parameters)
            except ValueError:
                await say(
                    ctx, "Use a JSON object containing only the action parameters."
                )
                return
            result = await self.action(
                ctx.author.id, ctx.guild.id if ctx.guild else 0, device, action, values
            )
            await say(ctx, render(result))

        @home.command(name="confirm")
        async def confirm(ctx, request_id: str):
            await say(
                ctx,
                render(
                    await self.client.call(
                        "confirm", ctx.author.id, request_id=request_id
                    )
                ),
            )

        @home.command(name="speak")
        @commands.cooldown(1, 30, commands.BucketType.user)
        async def speak(ctx, device: str, *, text: str):
            user = await self.mem.get_user(ctx.author.id) or {}
            await say(
                ctx,
                render(
                    await self.speak(
                        ctx.author.id,
                        device,
                        text,
                        user,
                        guild_id=ctx.guild.id if ctx.guild else 0,
                    )
                ),
            )

        for operation in (
            "status",
            "devices",
            "agent",
            "permissions",
            "audit",
            "disable",
            "enable",
            "test",
        ):
            # Hide the captured operation from the Discord argument parser.
            def make_callback(op):
                async def callback(ctx, device: str = None):
                    await diagnostic_impl(ctx, device, op)

                return callback

            async def diagnostic_impl(ctx, device, op):
                if ctx.author.id != self.owner_id or not self.owner_id:
                    await say(ctx, "Owner only.")
                    return
                if ctx.guild:
                    await say(ctx, "Use a DM for home diagnostics and administration.")
                    return
                result = (
                    await self.action(ctx.author.id, 0, device, "test", {})
                    if op == "test"
                    else await self.client.call(
                        op, ctx.author.id, **({"device": device} if device else {})
                    )
                )
                await say(ctx, json.dumps(result, ensure_ascii=True))

            home.command(name=operation)(make_callback(operation))


def render(result):
    if result.get("confirmation_required"):
        return (
            "Confirm this specific action within 30 seconds: !home confirm "
            + result["confirmation_required"]
        )
    if result.get("ok"):
        return (
            "Done."
            if result.get("result") == "completed"
            else "Submitted; physical completion is not confirmed."
        )
    return (
        "That action did not go through ("
        + str(result.get("error", "device unavailable"))
        + ")."
    )
