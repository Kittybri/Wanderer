"""Thin integration with the existing character engine, memory and Fish VoiceState."""

from __future__ import annotations

import asyncio
import contextlib
import json
import io
import os
import shutil

import discord

from awareness_features import classify_safety, protective_prompt
from .receive import ReceiveBackend
from .session import Playback, Session
from .speech import GroqSTT, Limits


class VoiceConversation:
    def __init__(
        self, bot, mem, name, respond, tts, stt_key, owner_id=0, on_spoken=None
    ):
        self.bot, self.mem, self.name = bot, mem, name
        self.respond, self.tts, self.stt_key = respond, tts, stt_key
        self.owner_id = owner_id
        self.on_spoken = on_spoken
        self.sessions = {}
        self.features = None
        self.lock = None
        self.allowed = frozenset(
            int(x)
            for x in os.getenv("VOICE_ALLOWED_CHANNEL_IDS", "").split(",")
            if x.strip().isdigit()
        )

    def install(self):
        self.bot.add_listener(self.voice_state, "on_voice_state_update")
        self.bot.add_listener(self.channel_deleted, "on_guild_channel_delete")
        original = self.bot.close

        async def close():
            await self.close()
            await original()

        self.bot.close = close

    async def close(self):
        if self.features:
            await self.features.close()
        for gid in list(self.sessions):
            await self.leave(gid)

    async def leave(self, gid):
        session = self.sessions.pop(gid, None)
        if session:
            channel = session.backend.vc.channel
            await session.stop()
            with contextlib.suppress(Exception):
                await session.backend.vc.disconnect(force=True)
            with contextlib.suppress(Exception):
                await channel.send(
                    "Live voice ended. Session consent and temporary audio buffers cleared.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )

    async def voice_state(self, member, before, after):
        if self.features:
            # A social-feature DB failure must never prevent receive consent
            # being revoked or the foundation disconnecting a moved bot.
            with contextlib.suppress(Exception):
                await self.features.voice_state(member, before, after)
        session = self.sessions.get(member.guild.id)
        if not session:
            return
        if member.id == self.bot.user.id:
            if (
                getattr(after.channel, "id", None) != session.channel_id
                or after.deaf
                or after.self_deaf
            ):
                await self.leave(member.guild.id)
            return
        if getattr(after.channel, "id", None) != session.channel_id:
            session.consent(member.id, False)

    async def channel_deleted(self, channel):
        session = self.sessions.get(channel.guild.id)
        if session and session.channel_id == channel.id:
            await self.leave(channel.guild.id)

    async def send(self, ctx, text):
        await ctx.reply(
            text, mention_author=False, allowed_mentions=discord.AllowedMentions.none()
        )

    async def status(self, ctx):
        session = self.sessions.get(ctx.guild.id) if ctx.guild else None
        if not session:
            await self.send(
                ctx,
                "Live voice: inactive. Use `!voice start` in an allowed VC. Each participant must opt in with `!voice listen on`. Voice-note preferences are separate.",
            )
            return
        info = session.status()
        await self.send(
            ctx,
            f"Live voice: {info['state']}; listening={info['listening']}; "
            f"receive speech verified={info['receive_proven']} (connection alone is not proof). "
            f"Targeting={info['mode']}; interruption={info['interrupt']}; "
            f"participants={info['participants']}; queued utterances={info['pending_audio']}. "
            "Opt out: `!voice listen off`; end session: `!voice stop`.",
        )

    async def command(self, ctx, message):
        value = (message or "").strip().lower()
        parts = value.split()
        # Both character bots intentionally expose the same !voice command.  An
        # unqualified start/stop keeps the existing shared behavior, while an
        # explicit character suffix lets operators isolate one bot without
        # taking the partner service offline.
        if len(parts) == 2 and parts[0] in {"start", "join", "stop", "leave"}:
            aliases = {
                "scaramouche": {"scaramouche", "scara", "balladeer"},
                "wanderer": {"wanderer", "hatguy", "hat-guy"},
            }
            target = parts[1]
            known_targets = set().union(*aliases.values())
            if target in known_targets:
                if target not in aliases.get(self.name.lower(), {self.name.lower()}):
                    return True
                parts = parts[:1]
                value = parts[0]
        if value == "off" and ctx.guild:
            session = self.sessions.get(ctx.guild.id)
            if session:
                session.consent(ctx.author.id, False)
        if value == "status":
            # Add diagnostics, then allow the legacy voice-note status to run.
            await self.status(ctx)
            return False
        if not parts or parts[0] not in {
            "start",
            "join",
            "stop",
            "leave",
            "listen",
            "mode",
            "interrupt",
            "diagnostics",
            "session",
        }:
            return False
        if value in {"session", "session status"}:
            await self.status(ctx)
            return True
        if not ctx.guild:
            await self.send(ctx, "Live voice controls require a server voice channel.")
            return True
        # Serialize joins/leave/consent commands; no duplicate sessions on concurrent joins.
        if self.lock is None:
            self.lock = asyncio.Lock()
        async with self.lock:
            await self.handle(ctx, parts)
        return True

    async def handle(self, ctx, parts):
        action = parts[0]
        session = self.sessions.get(ctx.guild.id)
        channel = getattr(getattr(ctx.author, "voice", None), "channel", None)
        admin = bool(
            ctx.author.id == self.owner_id or ctx.author.guild_permissions.manage_guild
        )
        if action in {"stop", "leave"}:
            if session and (admin or ctx.author.id == session.initiator):
                await self.leave(ctx.guild.id)
                await self.send(
                    ctx,
                    "Live voice ended; ephemeral audio and session consent cleared.",
                )
            else:
                await self.send(
                    ctx,
                    "Only the session initiator or a server manager can end the session. You can always `!voice listen off`.",
                )
            return
        if action == "diagnostics":
            if ctx.author.id != self.owner_id:
                await self.send(ctx, "Detailed voice diagnostics are owner-only.")
                return
            result = session.status() if session else {"state": "IDLE"}
            if self.features:
                result["advanced_features"] = {
                    "maintenance_error_seen": self.features.reported_error,
                    "pending_duo_turns": len(self.features.duo_pending),
                    "mockingbird_mode": getattr(
                        getattr(session, "feature_router", None), "mock_mode", "OFF"
                    ),
                }
            if session:
                result["events"] = list(session.events)[-16:]
                from .personality import priority_status

                result["priority_speaker"] = priority_status(
                    getattr(
                        getattr(getattr(session, "backend", None), "vc", None),
                        "channel",
                        None,
                    ),
                    ctx.guild.me,
                )
            with contextlib.suppress(discord.HTTPException):
                await ctx.author.send(
                    "Sanitized voice diagnostics; no transcript or raw audio.",
                    file=discord.File(
                        io.BytesIO(json.dumps(result, indent=2).encode()),
                        filename="voice-health.json",
                    ),
                )
            return
        if action == "listen" and parts[1:] == ["off"]:
            if session:
                session.consent(ctx.author.id, False)
            await self.send(
                ctx,
                "Your voice consent is off. Queued audio is discarded; no new speech from you will be transcribed. An already-sent provider request cannot be recalled.",
            )
            return
        temporary = self.features.games.temporary_channels if self.features else set()
        if not channel or (
            channel.id not in self.allowed and channel.id not in temporary
        ):
            await self.send(
                ctx,
                "Join a VC explicitly listed in VOICE_ALLOWED_CHANNEL_IDS first. Listening is disabled elsewhere.",
            )
            return
        if action in {"start", "join"}:
            if session or ctx.guild.voice_client or len(self.sessions) >= 2:
                await self.send(
                    ctx,
                    "A voice connection/session already exists, or the session limit is reached. End it before starting another.",
                )
                return
            prefs = await self.mem.get_user_preferences(ctx.author.id)
            if not prefs.get("voice_enabled", True):
                await self.send(
                    ctx,
                    "Your voice preference is off. Enable `!voice on` before starting live voice.",
                )
                return
            permissions = channel.permissions_for(ctx.guild.me)
            if (
                not permissions.connect
                or not permissions.speak
                or not permissions.view_channel
            ):
                await self.send(
                    ctx, "I need View Channel, Connect and Speak in that VC."
                )
                return
            if not self.stt_key or not shutil.which("ffmpeg"):
                await self.send(
                    ctx,
                    "Live voice needs Groq STT credentials and FFmpeg configured on the host.",
                )
                return
            backend = ReceiveBackend(
                lambda: session.participants if session else frozenset()
            )
            vc = None
            try:
                client_class = backend.client_class()
                # Public notice in the VC's own text chat, not a possibly private invocation channel.
                await channel.send(
                    "Live voice conversation is starting. Audio from consenting participants is sent to Groq for transcription; relevant conversation follows ordinary bot memory rules. No raw recording is saved. "
                    "The person starting it opts in; everyone else must use `!voice listen on`. Opt out with `!voice listen off`. Stop: `!voice stop`.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                vc = await channel.connect(cls=client_class, self_deaf=False)

                async def respond(uid, text, extra):
                    member = ctx.guild.get_member(uid)
                    if not member or uid not in session.participants:
                        return ""
                    await self.mem.upsert_user(uid, str(member), member.display_name)
                    user = await self.mem.get_user(uid) or {}
                    safety = protective_prompt(self.name, classify_safety(text))
                    return await self.respond(
                        uid,
                        channel.id,
                        text,
                        user,
                        member.display_name,
                        member.mention,
                        extra_context=extra + "\n" + safety,
                        is_owner=uid == self.owner_id,
                        channel_obj=channel,
                        is_dm=False,
                        defer_delivery=True,
                    )

                async def synthesize(uid, text):
                    user = await self.mem.get_user(uid) or {}
                    if not user.get("voice_enabled", True):
                        return None
                    return await self.tts(
                        text, user.get("mood", 0), user, voice_key=uid
                    )

                async def remember(uid, text):
                    await self.mem.add_message(
                        uid, channel.id, "assistant", "[voice spoken] " + text
                    )
                    if self.on_spoken:
                        await self.on_spoken(uid, text)

                async def notify(category):
                    await channel.send(
                        "Live voice needs attention; text and ordinary voice notes remain available. Try `!voice status`, then stop/start after checking setup.",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    if self.owner_id:
                        owner = self.bot.get_user(
                            self.owner_id
                        ) or await self.bot.fetch_user(self.owner_id)
                        await owner.send(
                            f"{self.name}: voice diagnostic `{category}` in channel {channel.id}. No transcript/audio attached."
                        )

                session = Session(
                    channel_id=channel.id,
                    initiator=ctx.author.id,
                    name=self.name,
                    backend=backend,
                    stt=GroqSTT(self.stt_key),
                    playback=Playback(vc),
                    respond=respond,
                    synthesize=synthesize,
                    remember=remember,
                    notify=notify,
                    limits=Limits.from_env(),
                )
                session.consent(ctx.author.id, True)
                self.sessions[ctx.guild.id] = session
                if self.features:
                    self.features.attach(session, ctx.guild.id)
                await backend.start(vc)
                await session.start()
                await self.status(ctx)
            except Exception:
                if session:
                    await self.leave(ctx.guild.id)
                elif vc:
                    await vc.disconnect(force=True)
                await self.send(
                    ctx,
                    "Live voice could not start. Check the pinned receive dependencies, Opus/FFmpeg, DAVE and permissions. Text and voice notes are unaffected.",
                )
            return
        if not session or not session.active or channel.id != session.channel_id:
            await self.send(
                ctx, "Start a session in your allowed VC first: `!voice start`."
            )
            return
        if action == "listen" and parts[1:] == ["on"]:
            prefs = await self.mem.get_user_preferences(ctx.author.id)
            if not prefs.get("voice_enabled", True):
                await self.send(
                    ctx, "Enable your voice preference with `!voice on` first."
                )
                return
            try:
                session.consent(ctx.author.id, True)
                if self.features:
                    await self.features.arrival(session, ctx.guild.id, ctx.author.id)
                await self.send(
                    ctx,
                    "You opted in for this session. Speech goes to Groq for transcription; relevant turns use ordinary memory. Raw audio is not saved. `!voice listen off` revokes consent.",
                )
            except ValueError:
                await self.send(ctx, "This session has reached its participant limit.")
            return
        if (
            action == "interrupt"
            and len(parts) == 3
            and parts[1] == "me"
            and parts[2].upper() in {"OFF", "KEYWORD", "NATURAL"}
        ):
            if ctx.author.id in session.participants:
                session.user_interrupt[ctx.author.id] = parts[2].upper()
                await self.send(
                    ctx,
                    "Your interruption preference is "
                    + parts[2].upper()
                    + " for this session.",
                )
            return
        if not (admin or ctx.author.id == session.initiator):
            await self.send(
                ctx, "Session-wide settings require its initiator or a server manager."
            )
            return
        if (
            action == "mode"
            and len(parts) == 2
            and parts[1].upper() in {"DIRECT_ONLY", "CONVERSATION", "ACTIVE_ROOM"}
        ):
            session.mode = parts[1].upper()
        elif (
            action == "interrupt"
            and len(parts) == 2
            and parts[1].upper() in {"OFF", "KEYWORD", "NATURAL"}
        ):
            session.interrupt_mode = parts[1].upper()
        else:
            await self.send(
                ctx,
                "Controls: `start`, `stop`, `listen on/off`, `mode direct_only/conversation/active_room`, `interrupt off/keyword/natural`, `interrupt me off/keyword/natural`, `status`, `diagnostics`. Prefix each with `!voice `.",
            )
            return
        await self.status(ctx)
