"""Opt-in party games with durable intent/cleanup records, never permission traps."""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from types import SimpleNamespace
import discord

PUZZLES = (
    {
        "question": "What number comes next: 2, 4, 8, 16, ?",
        "answers": ["32", "thirty two", "thirty-two"],
        "hint": "Double the previous number.",
    },
    {
        "question": "Three switches are OFF. Toggle A, then B, then A. Which switch is ON?",
        "answers": ["b", "switch b"],
        "hint": "Toggling the same switch twice returns it to OFF.",
    },
)
QUESTIONS = {
    "scaramouche": (
        "The court is in session. Explain your most questionable game strategy.",
        "Which of us would you choose to lead a boss fight, and why?",
        "Your final defense: name one strategy you would improve. Keep it about the game.",
    ),
    "wanderer": (
        "This is voluntary. What game strategy would you like help improving?",
        "What usually goes wrong during that boss fight? Keep personal details out of it.",
        "Pick one practical change for next time. I will call that a successful defense.",
    ),
}
TERMINAL = {"solved", "failed", "expired", "cancelled", "completed"}


class Games:
    def __init__(self, owner):
        self.owner, self.store = owner, owner.store
        self.temporary_channels = set()
        self.lock = None

    async def command(self, ctx, action, argument):
        if self.lock is None:
            self.lock = asyncio.Lock()
        async with self.lock:
            await self._command(ctx, action, argument)

    async def _command(self, ctx, action, argument):
        owner, uid = self.owner, ctx.author.id
        if action == "help":
            await owner.service.send(
                ctx,
                "Managers: !vcgame interrogate [@user] or escape [@users]. Invited users: !vcgame accept <id>. In the puzzle thread: !vcgame answer <id> <answer> or hint <id>. Anyone participating can use !vcgame cancel or leave; status shows your games. Interrogation includes temporary movement and opt-in Groq transcription/Fish playback; no raw recording. You remain free to leave.",
            )
            return
        if not ctx.guild:
            raise ValueError("server required")
        gid = ctx.guild.id
        games = [g for g in await self.store.games() if g["guild_id"] == gid]
        if action in {"cancel", "leave"}:
            for game in games:
                if (
                    uid in game["participants"]
                    or ctx.author.guild_permissions.manage_channels
                ):
                    game["state"] = "cancelled"
                    await self.store.save_game(game)
                    await self.cleanup(game)
            await owner.service.send(
                ctx,
                "Your game is cancelled. Any unfinished restoration is retained for recovery; you are always free to leave manually.",
            )
            return
        if not owner.enabled(gid):
            raise ValueError("disabled")
        if action == "status":
            visible = [
                f"{g['id']}: {g['kind']} / {g['state']}"
                for g in games
                if uid in g["participants"]
                or ctx.author.guild_permissions.manage_channels
            ]
            await owner.service.send(
                ctx, "\n".join(visible) or "No active game for you."
            )
            return
        if action in {"interrogate", "escape"}:
            if not ctx.author.guild_permissions.manage_channels:
                raise ValueError("Manage Channels required")
            if not owner.allowed(gid, ctx.channel.id, game=True) or not owner.enabled(
                gid, action
            ):
                raise ValueError("channel/feature disabled")
            members = list(ctx.message.mentions) or [ctx.author]
            if action == "escape" and ctx.author not in members:
                members.insert(0, ctx.author)
            if not 1 <= len(members) <= (1 if action == "interrogate" else 4) or any(
                m.bot for m in members
            ):
                raise ValueError("human participant limit")
            if len({m.id for m in members}) != len(members):
                raise ValueError("duplicate members")
            if action == "interrogate":
                target = members[0]
                channel = getattr(target.voice, "channel", None)
                if not channel or not owner.allowed(gid, channel.id):
                    raise ValueError("target must be in allowed VC")
                if ctx.guild.voice_client or gid in owner.service.sessions:
                    raise ValueError("stop the existing voice session first")
                if (
                    not ctx.guild.me.guild_permissions.manage_channels
                    or not ctx.guild.me.guild_permissions.move_members
                ):
                    raise ValueError("missing room/move permissions")
            consent = []
            for member in members:
                prefs = await self.store.preferences(member.id)
                flag = (
                    "interrogation_game_enabled"
                    if action == "interrogate"
                    else "escape_room_enabled"
                )
                if member.id == uid or (
                    prefs["vc_party_features_enabled"] and prefs[flag]
                ):
                    consent.append(member.id)
            if not await owner.budget(gid, uid, action, seconds=3600):
                raise ValueError("cooldown")
            game = await self.store.create_game(
                gid,
                {
                    "kind": action,
                    "participants": [m.id for m in members],
                    "accepted": consent,
                    "requester": uid,
                    "parent": ctx.channel.id,
                    "channel": 0,
                    "original": getattr(
                        getattr(members[0].voice, "channel", None), "id", 0
                    ),
                    "question_index": 0,
                    "attempts": 0,
                    "puzzle": random.choice(PUZZLES),
                    "notified": False,
                },
                120,
            )
            await owner.service.send(
                ctx,
                f"Voluntary {action} invitation `{game['id']}`. Each invited person can accept with `!vcgame accept {game['id']}` within two minutes, or decline with `!vcgame cancel`. Interrogation moves you temporarily and uses the existing Groq/Fish voice pipeline; escape uses a private puzzle thread. No normal-channel access changes.",
            )
            if set(consent) == set(game["participants"]):
                await self.activate(ctx, game)
            return
        game_id, _, value = argument.partition(" ")
        game = next((g for g in games if g["id"] == game_id), None)
        if not game or uid not in game["participants"]:
            raise ValueError("not your invitation/game")
        if game["expires"] <= time.time():
            game["state"] = "expired"
            await self.store.save_game(game)
            await self.cleanup(game)
            return
        if action == "accept" and game["state"] == "created":
            if uid not in game["accepted"]:
                game["accepted"].append(uid)
            await self.store.save_game(game)
            if set(game["accepted"]) == set(game["participants"]):
                await self.activate(ctx, game)
            else:
                await owner.service.send(
                    ctx,
                    "Consent recorded; waiting for the remaining invited participants.",
                )
            return
        if (
            game["kind"] != "escape"
            or game["state"] not in {"active", "hint_requested"}
            or ctx.channel.id != game["channel"]
        ):
            raise ValueError("use the active game thread")
        if action == "hint":
            game["state"] = "hint_requested"
            await self.store.save_game(game)
            line = (
                "Fine. One hint: "
                if owner.name == "scaramouche"
                else "Here is a useful hint: "
            ) + game["puzzle"]["hint"]
            await owner.service.send(ctx, line)
            return
        if action != "answer":
            raise ValueError("unknown game command")
        correct = value.strip().casefold().rstrip(".! ") in game["puzzle"]["answers"]
        game["attempts"] += 1
        game["state"] = (
            "solved" if correct else "failed" if game["attempts"] >= 5 else "active"
        )
        await self.store.save_game(game)
        if correct:
            for participant in game["participants"]:
                if (await self.store.preferences(participant))[
                    "vc_party_features_enabled"
                ]:
                    await self.store.remember(participant, gid, "solved_escape")
            await owner.service.send(
                ctx,
                (
                    "Solved. Even I must concede that."
                    if owner.name == "scaramouche"
                    else "Correct. Well worked out; the room is open."
                ),
            )
        else:
            await owner.service.send(
                ctx,
                (
                    "Not quite. Check the rule again."
                    if owner.name == "wanderer"
                    else "Incorrect. The puzzle has not changed just because you dislike it."
                )
                + f" Attempts: {game['attempts']}/5.",
            )
            session = owner.service.sessions.get(gid)
            if session:
                await owner.sound(
                    session,
                    gid,
                    uid,
                    "buzzer" if owner.name == "scaramouche" else "sigh",
                )
        if game["state"] in TERMINAL:
            await self.cleanup(game)

    async def activate(self, ctx, game):
        owner, guild = self.owner, ctx.guild
        if set(game["accepted"]) != set(game["participants"]):
            raise ValueError("consent incomplete")
        if not owner.enabled(guild.id, game["kind"]):
            raise ValueError("feature disabled")
        game["state"] = "creating"
        game["creation_started"] = True
        await self.store.save_game(game)  # durable intent before any Discord mutation
        name = "vc-game-" + game["id"]
        try:
            members = [guild.get_member(uid) for uid in game["participants"]]
            if any(m is None or m.bot for m in members):
                raise ValueError("member unavailable")
            parent = guild.get_channel(game["parent"])
            if not parent:
                raise ValueError("parent unavailable")
            if game["kind"] == "escape":
                thread = await parent.create_thread(
                    name=name,
                    type=discord.ChannelType.private_thread,
                    invitable=False,
                    auto_archive_duration=60,
                    reason="Consensual bounded puzzle game",
                )
                game["channel"] = thread.id
                await self.store.save_game(game)
                for member in members:
                    await thread.add_user(member)
                game["state"], game["expires"] = "active", time.time() + 600
                await self.store.save_game(game)
                await thread.send(
                    f"Voluntary escape room. You remain free to leave and use other channels. Ten minutes, five attempts.\n{game['puzzle']['question']}\nUse `!vcgame answer {game['id']} <answer>`, `!vcgame hint {game['id']}`, or `!vcgame cancel`.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                target = members[0]
                if guild.voice_client or guild.id in owner.service.sessions:
                    raise ValueError("voice busy")
                if (
                    getattr(getattr(target.voice, "channel", None), "id", None)
                    != game["original"]
                ):
                    raise ValueError("target moved before consent completed")
                if not owner.allowed(guild.id, game["original"]):
                    raise ValueError("original no longer allowed")
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    target: discord.PermissionOverwrite(
                        view_channel=True, connect=True, speak=True, send_messages=True
                    ),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        connect=True,
                        speak=True,
                        send_messages=True,
                        manage_channels=True,
                    ),
                }
                room = await guild.create_voice_channel(
                    name,
                    overwrites=overwrites,
                    reason="Consensual temporary interrogation game",
                    user_limit=3,
                )
                game["channel"] = room.id
                await self.store.save_game(game)  # record room BEFORE moving a person
                await target.move_to(
                    room,
                    reason="Accepted voluntary game; original channel retained for restore",
                )
                for _ in range(30):
                    if (
                        getattr(getattr(target.voice, "channel", None), "id", None)
                        == room.id
                    ):
                        break
                    await asyncio.sleep(0.1)
                else:
                    raise ValueError("move not observed")
                self.temporary_channels.add(room.id)
                proxy = SimpleNamespace(author=target, guild=guild, reply=ctx.reply)
                # The exact existing pipeline performs joining, consent notice, VAD,
                # STT, Fish and cancellation. No game-specific audio receiver.
                await owner.service.command(proxy, "start")
                session = owner.service.sessions.get(guild.id)
                if not session or session.channel_id != room.id or not session.active:
                    raise ValueError("voice unavailable")
                owner.attach(session, guild.id)
                game["state"], game["expires"] = "active", time.time() + 120
                await self.store.save_game(game)
                await session.submit(
                    target.id,
                    "",
                    reply=QUESTIONS[owner.name][0],
                    feature_kind="interrogate",
                )
        except BaseException:
            game["state"] = "cancelled"
            await self.store.save_game(game)
            await self.cleanup(game)
            raise

    async def utterance(self, session, uid):
        if self.lock is None:
            self.lock = asyncio.Lock()
        async with self.lock:
            return await self._utterance(session, uid)

    async def serious(self, session, uid):
        """End playful questions; let the existing safety response speak first."""
        if self.lock is None:
            self.lock = asyncio.Lock()
        async with self.lock:
            for game in await self.store.games():
                if (
                    game["kind"] == "interrogate"
                    and game["state"] == "active"
                    and game["channel"] == session.channel_id
                    and uid in game["participants"]
                ):
                    game["state"] = "finishing"
                    game["finish_after"] = time.time() + 30
                    await self.store.save_game(game)
                    return True
        return False

    async def _utterance(self, session, uid):
        for game in await self.store.games():
            if (
                game["kind"] == "interrogate"
                and game["state"] == "active"
                and game["channel"] == session.channel_id
                and uid in game["participants"]
            ):
                game["question_index"] += 1
                if game["question_index"] >= 3:
                    game["state"] = "finishing"
                    game["finish_after"] = time.time() + 15
                    line = (
                        "The court is adjourned. You are free to go."
                        if self.owner.name == "scaramouche"
                        else "That is enough questions. Let us get you back."
                    )
                else:
                    line = QUESTIONS[self.owner.name][game["question_index"]]
                await self.store.save_game(game)
                return line
        return ""

    async def cancel_user(self, gid, uid):
        if self.lock is None:
            self.lock = asyncio.Lock()
        async with self.lock:
            await self._cancel_user(gid, uid)

    async def _cancel_user(self, gid, uid):
        for game in await self.store.games():
            if game["guild_id"] == gid and uid in game["participants"]:
                game["state"] = "cancelled"
                await self.store.save_game(game)
                await self.cleanup(game)

    async def tick(self, recovery=False):
        if self.lock is None:
            self.lock = asyncio.Lock()
        async with self.lock:
            for game in await self.store.games():
                session = self.owner.service.sessions.get(game["guild_id"])
                if not self.owner.enabled(game["guild_id"], game["kind"]):
                    game["state"] = "cancelled"
                if (
                    recovery
                    and game["kind"] == "interrogate"
                    and game["state"] != "created"
                ):
                    game["state"] = "cancelled"
                if game["state"] == "creating":
                    game["state"] = "cancelled"
                if game["expires"] < time.time():
                    game["state"] = "expired"
                if (
                    game["kind"] == "interrogate"
                    and game["state"] == "finishing"
                    and time.time() >= game.get("finish_after", 0)
                    and (not session or not session.busy())
                ):
                    game["state"] = "completed"
                    uid = game["participants"][0]
                    if (await self.store.preferences(uid))["vc_party_features_enabled"]:
                        await self.store.remember(
                            uid, game["guild_id"], "interrogation_completed"
                        )
                if game["kind"] == "interrogate" and game["state"] == "active":
                    guild = self.owner.service.bot.get_guild(game["guild_id"])
                    member = (
                        guild.get_member(game["participants"][0]) if guild else None
                    )
                    if (
                        not session
                        or not session.active
                        or game["participants"][0] not in session.participants
                        or not member
                        or getattr(getattr(member.voice, "channel", None), "id", None)
                        != game["channel"]
                    ):
                        game["state"] = "cancelled"
                if game["state"] in TERMINAL:
                    await self.store.save_game(game)
                    await self.cleanup(game)

    async def cleanup(self, game):
        """Only restore members still in our exact room; never chase manual leavers."""
        bot = self.owner.service.bot
        guild = bot.get_guild(game["guild_id"])
        if not guild:
            return  # retain journal for next ready/recovery
        try:
            channel = None
            if game["channel"]:
                try:
                    channel = await bot.fetch_channel(game["channel"])
                except discord.NotFound:
                    pass
            elif game["state"] in TERMINAL and game.get("creation_started"):
                # Recover crash between create API completion and recording its ID.
                candidates = (
                    list(guild.voice_channels)
                    if game["kind"] == "interrogate"
                    else await guild.active_threads()
                )
                matches = [
                    c
                    for c in candidates
                    if c.name == "vc-game-" + game["id"]
                    and c.created_at.timestamp() >= game["created"] - 5
                ]
                if len(matches) > 1:
                    raise ValueError("ambiguous recovery target")
                if matches:
                    channel = matches[0]
                    game["channel"] = channel.id
                    await self.store.save_game(game)
            if channel and (
                channel.guild.id != game["guild_id"]
                or channel.name != "vc-game-" + game["id"]
            ):
                raise ValueError("cleanup target changed")
            if game["kind"] == "interrogate":
                session = self.owner.service.sessions.get(guild.id)
                if session and session.channel_id == game["channel"]:
                    await self.owner.service.leave(guild.id)
                target = guild.get_member(game["participants"][0])
                if (
                    channel
                    and target
                    and getattr(getattr(target.voice, "channel", None), "id", None)
                    == channel.id
                ):
                    original = guild.get_channel(game["original"])
                    if not original:
                        raise ValueError("original channel missing")
                    await target.move_to(
                        original, reason="Restore after voluntary game"
                    )
                    # Discord cache updates can lag the HTTP result. Never delete until observed.
                    return
                if channel:
                    if any(not m.bot for m in channel.members):
                        raise ValueError("room still occupied")
                    # Do not disconnect another bot's unrelated session by deleting its room.
                    if channel.members:
                        raise ValueError("waiting for bot disconnect")
                    await channel.delete(reason="Cleanup completed voluntary game")
                self.temporary_channels.discard(game["channel"])
            elif channel:
                await channel.edit(archived=True, reason="Voluntary puzzle game ended")
            await self.store.delete_game(game["id"])
        except (discord.HTTPException, ValueError):
            if not game.get("notified"):
                game["notified"] = True
                await self.store.save_game(game)
                parent = guild.get_channel(game["parent"])
                if parent:
                    with contextlib.suppress(discord.HTTPException):
                        await parent.send(
                            f"Game {game['id']} has ended, but restoration/cleanup needs a server manager. You are free to leave manually. The recovery record is retained.",
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
