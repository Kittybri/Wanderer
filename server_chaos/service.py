"""Bounded Discord-native games with explicit authority and public provenance."""

from __future__ import annotations
from .errors import ChaosError

import asyncio
import contextlib
import hashlib
import secrets
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from awareness_features import is_sensitive_memory, classify_safety
from voice_conversation.personality import safe_parody
from voice_conversation.games import PUZZLES
from .state import ChaosState, PREFS, ACTIVE
from .restoration import Restoration

PAIR = "scaramouche::wanderer"
GAME_TYPES = {"coin_flip", "dice", "high_card", "one_in_six"}


def harmless(text):
    if (
        not text
        or text.lstrip().startswith(("!", "/"))
        or is_sensitive_memory(text)
        or classify_safety(text).protective
    ):
        return False
    # Extend the already conservative game-only VC parody filter, not a second
    # model classifier. No free-form invented admissions or private disclosures.
    for word in (
        "Scaramouche",
        "scaramouche",
        "Wanderer",
        "wanderer",
        "dramatic",
        "annoying",
        "coping",
        "right",
        "wrong",
        "being",
        "mocked",
        "called",
        "voice",
        "robotic",
        "my",
    ):
        text = text.replace(word, "game")
    return safe_parody(text)


def public_channel(channel, *members):
    if not channel or channel.type != discord.ChannelType.text:
        return False  # No DM, thread (even public), voice chat or restricted channel.
    guild = channel.guild
    for member in (guild.default_role, *members):
        p = channel.permissions_for(member)
        if not p.view_channel or not p.read_message_history:
            return False
    return True


def quiet(profile, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        hour = now.astimezone(
            ZoneInfo(profile.get("timezone_name") or "America/Los_Angeles")
        ).hour
        start, end = int(profile.get("quiet_hours_start", 23)), int(
            profile.get("quiet_hours_end", 8)
        )
    except (ValueError, TypeError, KeyError):
        return True
    return (
        hour < 9
        or hour >= 21
        or (
            start != end
            and (start <= hour < end if start < end else hour >= start or hour < end)
        )
    )


def winner_for(game, source, target):
    if game not in GAME_TYPES:
        raise ChaosError("Unsupported wager game")
    if game == "coin_flip":
        return (source, target)[secrets.randbelow(2)]
    if game == "one_in_six":
        return source if secrets.randbelow(6) == 0 else target
    sides = 6 if game == "dice" else 13
    # Bounded tie handling; final tie uses an unbiased coin.
    for _ in range(3):
        a, b = secrets.randbelow(sides), secrets.randbelow(sides)
        if a != b:
            return source if a > b else target
    return (source, target)[secrets.randbelow(2)]


class ServerChaos:
    def __init__(
        self, bot, mem, name, config, world, voice, owner_id=0, *, autocorrect=None
    ):
        self.bot, self.mem, self.name, self.config = bot, mem, name, config or {}
        self.world, self.voice, self.owner_id = world, voice, owner_id
        self.autocorrect = autocorrect
        self.store = ChaosState(mem, name)
        self.restoration = Restoration(self)
        self.lock, self.task = None, None
        self.error_reported = False
        self.last_auto = 0

    def cfg(self, gid):
        return self.config.get("guilds", {}).get(str(gid), {})

    async def enabled(self, gid, feature=None):
        cfg = self.cfg(gid)
        control = await self.store.get(f"chaos:control:{gid}") or {}
        return bool(
            cfg.get("enabled", False)
            and control.get("enabled", True)
            and (not feature or cfg.get("features", {}).get(feature, False))
        )

    def admin(self, ctx):
        return bool(
            ctx.guild
            and (
                ctx.author.id == self.owner_id
                or ctx.author.guild_permissions.manage_guild
            )
        )

    async def send(self, channel, text):
        if self.name == "wanderer":
            for source, target in (
                ("!chaos", "!wanchaos"),
                ("!wager", "!challenge"),
                ("!court", "!defense"),
                ("!pranks", "!wanpranks"),
            ):
                text = text.replace(source, target)
        return await channel.send(
            "[Server game] " + text[:1900],
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def reserve(self, gid, uid, feature, cost=1, days=1):
        if not (await self.store.budget(gid, cost=cost))[0]:
            raise ChaosError("The guild chaos budget is cooling down.")
        ok, _ = await self.mem.consume_shared_cooldown(
            f"chaos:{gid}:{uid}:{feature}", max(300, days * 86400)
        )
        if not ok:
            raise ChaosError("This game/prank is cooling down.")

    async def source(
        self, channel, mid, member=None, fingerprint=None, allow_report=False
    ):
        if not public_channel(channel, *([member] if member else [])):
            raise ChaosError(
                "Only a currently public, readable text channel can supply evidence."
            )
        message = await channel.fetch_message(int(mid))
        text = message.content
        if allow_report and text.startswith("!report "):
            pieces = text.split(maxsplit=2)
            text = (
                pieces[2]
                if len(pieces) == 3
                and member is not None
                and pieces[1] in {f"<@{member.id}>", f"<@!{member.id}>"}
                and pieces[2] in {"mocked my hat", "called my voice robotic"}
                else ""
            )
        if (
            message.author.bot
            or not harmless(text)
            or message.attachments
            or message.embeds
        ):
            raise ChaosError("That is not eligible harmless public game text.")
        digest = hashlib.sha256(message.content.encode()).hexdigest()
        if fingerprint and digest != fingerprint:
            raise ChaosError("The source changed; the game cannot reuse it.")
        return message, digest

    async def control(self, ctx, action, argument):
        gid = ctx.guild.id
        if action in {"status", "budget"}:
            _, budget = await self.store.budget(gid)
            pending = [
                r
                for _, r in await self.store.recent("chaos_mutation", 100)
                if r["guild_id"] == gid and r["state"] in {"intent", "applied"}
            ]
            legacy = (
                await self.mem.get_due_temporary_channel_settings()
                if hasattr(self.mem, "get_due_temporary_channel_settings")
                else []
            )
            legacy = [r for r in legacy if ctx.guild.get_channel(r["channel_id"])]
            await self.send(
                ctx,
                f"Chaos enabled: {await self.enabled(gid)}. Budget: {budget['level']} ({budget['score']:.1f}/6). Pending cosmetic restorations: {len(pending)}. Legacy slowmode receipts needing manual reconciliation: {len(legacy)}. Maintenance issue seen: {self.error_reported}.",
            )
            return
        if not self.admin(ctx):
            raise ChaosError("Manage Server or configured owner authority required.")
        if action in {"enable", "disable", "restore", "restore-all"}:
            if action == "enable" and not self.cfg(gid).get("enabled"):
                raise ChaosError("Enable the guild in deployment configuration first.")
            birthday_keys = [
                k
                for k, r in await self.store.recent("birthday_restore", 100)
                if r["guild_id"] == gid
            ]
            await self.store.put(
                f"chaos:control:{gid}",
                "chaos_control",
                {
                    "enabled": action == "enable",
                    "restore_requested": time.time() if action != "enable" else 0,
                    "birthday_keys": birthday_keys,
                },
            )
            if action != "enable":
                await self.restore_all(gid)
            await self.send(
                ctx,
                "Chaos "
                + (
                    "enabled within the configured allowlists."
                    if action == "enable"
                    else "disabled; tracked restoration requested. Check status for pending permission/network recovery. Newer manual edits are preserved."
                ),
            )
            return
        if action == "sovereign":
            await self.sovereign(ctx.guild, ctx.author.id, "manual")
            await self.send(
                ctx,
                "A temporary cosmetic reign is recorded. No permissions, roles or channels are removed.",
            )
            return
        if action == "event" and argument in {"challenge", "tournament"}:
            # A manager explicitly attests this event, never inferred from mood.
            await self.sovereign(ctx.guild, ctx.author.id, argument)
            await self.send(
                ctx,
                "Configured event acknowledged; temporary cosmetic state is tracked.",
            )
            return
        await self.send(
            ctx,
            "!chaos status|budget|enable|disable|restore-all|sovereign; !chaos event challenge|tournament. No destructive powers.",
        )

    async def sovereign(self, guild, actor, trigger):
        if self.name != "scaramouche":
            raise ChaosError(
                "Wanderer does not seize the server. He can request restoration."
            )
        cfg = self.cfg(guild.id)
        if not await self.enabled(guild.id, "sovereign"):
            raise ChaosError("Sovereign is disabled.")
        mode = cfg.get("mode", "MANUAL")
        if mode not in {"MANUAL", "EVENT", "AUTONOMOUS_SAFE"}:
            raise ChaosError("Sovereign mode is OFF or invalid.")
        if trigger != "manual" and mode == "MANUAL":
            raise ChaosError("Event/autonomous triggers are disabled in MANUAL mode.")
        if trigger == "autonomous" and mode != "AUTONOMOUS_SAFE":
            raise ChaosError("Autonomy not authorized")
        if trigger not in {"manual", "autonomous"} and trigger not in cfg.get(
            "events", []
        ):
            raise ChaosError("Event not configured")
        plans = list(cfg.get("mutations", []))[
            : max(1, min(5, int(cfg.get("max_actions", 3))))
        ]
        if not plans:
            raise ChaosError("No configured cosmetic actions")
        if not (
            await self.store.budget(
                guild.id,
                cost=5,
                major=True,
                cooldown=max(86400, int(cfg.get("cooldown_days", 3)) * 86400),
            )
        )[0]:
            raise ChaosError(
                "Major server events are cooling down for days, not minutes."
            )
        for plan in plans:
            await self.restoration.apply(
                guild,
                plan["type"],
                int(plan["id"]),
                plan["field"],
                plan["value"],
                actor,
                min(900, int(cfg.get("max_duration", 300))),
            )
        channel = guild.get_channel(int(cfg.get("announcement_channel", 0)))
        if channel and channel.id in cfg.get("allowed_channels", []):
            await self.send(
                channel,
                "My cosmetic reign has been requested. Every attempted change has a restoration record—even magnificence has paperwork.",
            )

    async def wager(self, ctx, action, argument):
        gid, uid = ctx.guild.id, ctx.author.id
        if action == "balance":
            async with self.store.connect() as db:
                row = await (
                    await db.execute(
                        "SELECT balance FROM chaos_wallet WHERE guild_id=? AND user_id=?",
                        (gid, uid),
                    )
                ).fetchone()
            await self.send(
                ctx,
                f"Your fictional favor tokens: {row[0] if row else 10}. No monetary value; no permissions or real-world favors owed.",
            )
            return
        if action == "open":
            target = ctx.message.mentions[0] if ctx.message.mentions else None
            args = [v for v in argument.split() if not v.startswith("<@")]
            game = args[0] if args else "dice"
            stake = args[1] if len(args) > 1 else "bragging"
            if (
                len(args) > 2
                or game not in GAME_TYPES
                or not target
                or target.bot
                or target.id == uid
                or stake not in {"bragging", "favor"}
            ):
                raise ChaosError(
                    "Use !wager open @human coin_flip|dice|high_card|one_in_six bragging|favor. Only one fictional favor token; never money or roles."
                )
            if self.name == "wanderer" and (stake != "bragging" or game != "dice"):
                raise ChaosError(
                    "I offer fair dice challenges for bragging rights, not stakes or loaded odds."
                )
            await self.reserve(gid, uid, "wager", cost=2, days=0)
            r = await self.store.create(
                "wager",
                gid,
                dict(
                    channel=ctx.channel.id,
                    source=uid,
                    target=target.id,
                    participants=[uid, target.id],
                    game=game,
                    stake=stake,
                ),
            )
            odds = (
                "Challenger wins only 1 in 6; target wins 5 in 6."
                if game == "one_in_six"
                else "Equal odds; ties use a fair redraw/coin."
            )
            await self.send(
                ctx,
                f"Voluntary {'wager' if self.name=='scaramouche' else 'fair challenge'} {r['id']}: {game}; stake={stake} (one fictional token, no value). {odds} Only target ID {target.id} can !wager accept {r['id']}; either player can reject/cancel. Expires in five minutes.",
            )
            return
        r = await self.store.get("chaos:" + argument.strip())
        if (
            not r
            or r.get("bot") != self.name
            or r.get("guild_id") != gid
            or r.get("channel") != ctx.channel.id
            or "game" not in r
            or uid not in r["participants"]
        ):
            raise ChaosError("No matching wager for you in this channel.")
        if action in {"cancel", "reject"}:
            changed = await self.store.transition(
                r["id"], {"created"}, {"state": "cancelled"}
            )
            await self.send(
                ctx,
                (
                    "Wager cancelled."
                    if changed
                    else "Already settled or closed; no second change."
                ),
            )
            return
        if action != "accept":
            raise ChaosError("Use open, accept, reject or cancel.")
        if not ctx.guild.get_member(r["source"]) or not ctx.guild.get_member(
            r["target"]
        ):
            await self.store.transition(r["id"], {"created"}, {"state": "cancelled"})
            raise ChaosError("A participant left; no stake applied.")
        result = await self.store.settle(
            r["id"], uid, winner_for(r["game"], r["source"], r["target"])
        )
        if not result:
            raise ChaosError(
                "Not your invitation, already settled, expired, or insufficient fictional tokens."
            )
        await self.send(
            ctx,
            f"Result {r['id']}: winner ID {result['winner']}. Stake applied once. {'A glorious, entirely inconsequential victory.' if self.name=='scaramouche' else 'Fair result. No tokens were risked.'}",
        )

    async def court(self, ctx, action, argument):
        gid, uid = ctx.guild.id, ctx.author.id
        if action == "open":
            if self.name != "scaramouche":
                raise ChaosError(
                    "Wanderer handles defense, not prosecutions. Respond to Scaramouche's voluntary case."
                )
            target = ctx.message.mentions[0] if ctx.message.mentions else None
            if not target or target.bot:
                raise ChaosError("Mention one human participant.")
            ref = getattr(ctx.message, "reference", None)
            mid = getattr(ref, "message_id", 0)
            evidence_kind = "public_quote"
            if not mid:
                await self.world.init()
                rows = await self.world.journal.active(target.id, ctx.channel.id)
                petty = next(
                    (
                        r
                        for r in rows
                        if r["severity"] == 1
                        and r["guild_id"] == gid
                        and r["source_type"] == "play_report"
                    ),
                    None,
                )
                if not petty:
                    raise ChaosError(
                        "Reply to an actual harmless public quote, or use an existing PETTY playful report from this channel."
                    )
                mid, evidence_kind = petty["source_reference"], "playful_report"
            source, digest = await self.source(
                ctx.channel, mid, target, allow_report=evidence_kind == "playful_report"
            )
            if evidence_kind == "public_quote" and source.author.id != target.id:
                raise ChaosError(
                    "Quoted evidence must be the participant's own message."
                )
            if (
                evidence_kind == "playful_report"
                and not (await self.store.prefs(source.author.id))["chaos_court"]
            ):
                raise ChaosError("The report author must opt into court sharing.")
            await self.reserve(gid, uid, "court", cost=2, days=0)
            r = await self.store.create(
                "court",
                gid,
                dict(
                    channel=ctx.channel.id,
                    target=target.id,
                    participants=[target.id],
                    requester=uid,
                    source_message_id=int(mid),
                    source_user_id=source.author.id,
                    fingerprint=digest,
                    evidence_kind=evidence_kind,
                    puzzle=PUZZLES[0],
                ),
            )
            await self.send(
                ctx,
                f"Voluntary Court invitation {r['id']} for user ID {target.id}. No moderation consequences. Accept permits public evidence and optional Wanderer defense: !court accept {r['id']}. Decline/cancel any time. Five minutes.",
            )
            return
        rid, _, defense = argument.partition(" ")
        r = await self.store.get("chaos:" + rid)
        if (
            not r
            or "evidence_kind" not in r
            or r["guild_id"] != gid
            or r["channel"] != ctx.channel.id
            or uid != r["target"]
        ):
            raise ChaosError("Only the invited participant can act on this case here.")
        if action in {"cancel", "reject"}:
            await self.store.transition(rid, ACTIVE, {"state": "cancelled"})
            await self.send(ctx, "Case dismissed. No consequence.")
            return
        if r["expires"] <= time.time():
            raise ChaosError("Case expired.")
        if action == "accept":
            source, _ = await self.source(
                ctx.channel,
                r["source_message_id"],
                ctx.author,
                r["fingerprint"],
                allow_report=r["evidence_kind"] == "playful_report",
            )
            changed = await self.store.transition(
                rid, {"created"}, {"state": "awaiting_defense", "accepted": True}
            )
            if not changed:
                raise ChaosError("Already accepted or closed.")
            await self.send(
                ctx,
                f"SCARAMOUCHE COURT — PARTY GAME\nEvidence ({r['evidence_kind']}, message {source.id}): {discord.utils.escape_markdown(source.content)}\n{r['puzzle']['question']}\n!court defend {rid} <answer|admit|contest>. This is not evidence of real misconduct.",
            )
            return
        answer = defense.strip().casefold()
        if action != "defend" or answer not in {
            "admit",
            "contest",
            *r["puzzle"]["answers"],
        }:
            raise ChaosError(
                "Use the puzzle answer, admit, contest or cancel; no private defense disclosures."
            )
        category = "solved" if answer in r["puzzle"]["answers"] else answer
        changed = await self.store.court_defense(rid, category)
        if not changed:
            raise ChaosError(
                "Defense already received, case closed, or another duo already owns this channel. Do not overwrite it."
            )
        await self.send(
            ctx,
            "Defense recorded. Wanderer may review it; without a defense bot, this closes harmlessly. No forced punishment.",
        )

    async def pranks(self, ctx, action, argument):
        uid, gid = ctx.author.id, ctx.guild.id
        if action in {"parody", "ping", "gossip", "court"} and argument in {
            "on",
            "off",
        }:
            await self.store.preference(uid, "chaos_" + action, argument == "on")
            if argument == "off":
                await self.forget(uid, disable=False)
            await self.send(
                ctx,
                f"Your {action} consent is {argument}. This never grants consent for somebody else.",
            )
            return
        if action in {"off", "forget"}:
            await self.forget(uid)
            await self.send(
                ctx,
                "Your chaos consent is off. Pending personal games/deliveries are cancelled; technical restoration/audit receipts remain.",
            )
            return
        if action == "status":
            await self.send(ctx, str(await self.store.prefs(uid)))
            return
        if self.name != "scaramouche":
            raise ChaosError(
                "I do not impersonate his schemes. I can expose recorded pranks and review his court cases."
            )
        if action not in {"translate", "phantom", "gossip"}:
            raise ChaosError(
                "!pranks parody|ping|gossip|court on/off; status; off; translate [reply]; phantom @consenting-user; gossip @recipient [reply to public source]."
            )
        feature = {"translate": "parody", "phantom": "ping", "gossip": "gossip"}[action]
        if not await self.enabled(gid, feature):
            raise ChaosError("This prank is disabled here.")
        target = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
        if target.bot or (
            action != "translate"
            and not (await self.store.prefs(target.id))["chaos_" + feature]
        ):
            raise ChaosError("The participant has not opted in.")
        if action == "phantom":
            await self.phantom(ctx.channel, target)
            return
        mid = getattr(getattr(ctx.message, "reference", None), "message_id", 0)
        source, digest = await self.source(ctx.channel, mid, target)
        if not (await self.store.prefs(source.author.id))["chaos_" + feature]:
            raise ChaosError("The source author has not opted in.")
        if action == "translate":
            await self.translate(source)
            return
        profile = await self.mem.get_user(target.id) or {}
        if quiet(profile) or not profile.get("allow_dms", False):
            raise ChaosError("Recipient DMs or daytime availability are off.")
        await self.reserve(gid, target.id, "gossip", days=3)
        r = await self.store.create(
            "gossip",
            gid,
            dict(
                channel=source.channel.id,
                source_message_id=source.id,
                source_user_id=source.author.id,
                recipient_user_id=target.id,
                participants=[source.author.id, target.id],
                fingerprint=digest,
                summary="A consenting participant made a public game remark.",
            ),
            ttl=60,
        )
        # Re-fetch provenance immediately before delivery; claim before send gives
        # at-most-once delivery after an ambiguous HTTP failure/restart.
        source, _ = await self.source(ctx.channel, source.id, target, digest)
        for p in r["participants"]:
            if not (await self.store.prefs(p))["chaos_gossip"]:
                raise ChaosError("Consent changed.")
        if not await self.store.transition(r["id"], {"created"}, {"state": "claimed"}):
            raise ChaosError("Delivery was cancelled.")
        try:
            await self.send(
                target,
                f"Opt-in gossip GAME. Apparently user ID {source.author.id} has opinions: “{discord.utils.escape_markdown(source.content)}”\nPublic source: {source.jump_url}\nThat is the actual statement, not a private disclosure. !pranks gossip off in the server stops this.",
            )
        except discord.HTTPException:
            await self.store.transition(r["id"], {"claimed"}, {"state": "failed"})
            raise
        await self.store.transition(
            r["id"], {"claimed"}, {"state": "delivered", "delivered_at": time.time()}
        )
        await self.send(
            ctx,
            "A consenting recipient received the attributed public game remark. No private messages were used.",
        )

    async def translate(self, source):
        if self.name != "scaramouche" or self.autocorrect is None:
            raise ChaosError("This bot does not run translation pranks.")
        if self.cfg(source.guild.id).get("parody_mode", "OFF") not in {
            "MANUAL",
            "PARTY",
        }:
            raise ChaosError("Parody mode is OFF.")
        if not (await self.store.prefs(source.author.id))[
            "chaos_parody"
        ] or not harmless(source.content):
            raise ChaosError("Not eligible")
        line = self.autocorrect(source.content)
        if not line:
            raise ChaosError("No harmless transformation available")
        await self.reserve(source.guild.id, source.author.id, "parody", days=3)
        if not await self.store.claim(
            f"chaos:parody:{source.id}",
            "chaos_parody",
            {"state": "attempted", "guild_id": source.guild.id},
        ):
            raise ChaosError("Already used this source")
        await source.reply(
            "[Server game] **PARODY — Scaramouche's words, not yours:**\n" + line,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def phantom(self, channel, target):
        if not public_channel(channel, target) or quiet(
            await self.mem.get_user(target.id) or {}
        ):
            raise ChaosError(
                "No prank during quiet hours or outside public allowed channels."
            )
        await self.reserve(channel.guild.id, target.id, "phantom", days=7)
        r = await self.store.create(
            "ping",
            channel.guild.id,
            dict(
                channel=channel.id,
                target=target.id,
                participants=[target.id],
                message_id=0,
                author_id=self.bot.user.id,
            ),
            ttl=5,
        )
        if not (await self.store.prefs(target.id))[
            "chaos_ping"
        ] or not await self.store.transition(r["id"], {"created"}, {"state": "intent"}):
            raise ChaosError("Consent changed.")
        msg = await channel.send(
            f"[Server game] <@{target.id}> A brief opted-in prank. [prank {r['id']}]",
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=[target], replied_user=False
            ),
        )
        await self.store.transition(
            r["id"], {"intent"}, {"state": "applied", "message_id": msg.id}
        )

    async def cleanup_ping(self, r):
        channel = self.bot.get_channel(r["channel"])
        if not channel or channel.guild.id != r["guild_id"]:
            return
        try:
            if r["message_id"]:
                msg = await channel.fetch_message(r["message_id"])
            else:
                found = [
                    m
                    async for m in channel.history(limit=50)
                    if m.author.id == r["author_id"]
                    and m.content.endswith(f"[prank {r['id']}]")
                    and abs(m.created_at.timestamp() - r["created_at"]) < 60
                ]
                if len(found) != 1:
                    return  # ambiguous send: keep receipt, never delete other messages
                msg = found[0]
            if msg.author.id != self.bot.user.id or msg.author.id != r["author_id"]:
                return
            await msg.delete()
        except discord.NotFound:
            pass
        except discord.HTTPException:
            return
        await self.store.transition(
            r["id"],
            {"intent", "applied"},
            {"state": "deleted", "deleted_at": time.time()},
        )

    async def forget(self, uid, disable=True):
        await self.store.init()
        if disable:
            for key in PREFS:
                await self.store.preference(uid, key, False)
        for kind in ("wager", "court", "gossip", "ping"):
            for _, r in await self.store.recent("chaos_" + kind, 100):
                if uid not in r.get("participants", []):
                    continue
                if kind == "ping":
                    await self.store.transition(
                        r["id"], {r["state"]}, {"exposure_allowed": False}
                    )
                if kind == "ping" and r["state"] in {"intent", "applied"}:
                    await self.cleanup_ping(r)
                elif r["state"] in ACTIVE:
                    await self.store.transition(r["id"], ACTIVE, {"state": "cancelled"})

    async def restore_all(self, gid):
        await self.restoration.restore(gid, force=True)
        for kind in ("wager", "court", "gossip", "ping"):
            for _, r in await self.store.recent("chaos_" + kind, 100):
                if r["guild_id"] != gid:
                    continue
                if kind == "ping" and r["state"] in {"intent", "applied"}:
                    await self.cleanup_ping(r)
                elif r["state"] in ACTIVE:
                    await self.store.transition(r["id"], ACTIVE, {"state": "cancelled"})
        # Reuse the existing VC game's restoration, never delete/move independently.
        for g in await self.voice.features.store.games():
            if g["guild_id"] == gid:
                await self.voice.features.games.cancel_user(gid, g["participants"][0])
        # Existing birthday manager already compares current to its applied name.
        from birthday_event import restore_decorations

        control = await self.store.get(f"chaos:control:{gid}") or {}
        await restore_decorations(
            self.bot,
            self.world.store,
            datetime.max.replace(tzinfo=timezone.utc),
            guild_id=gid,
            keys=control.get("birthday_keys", []),
        )

    async def rivalry(self, note):
        await self.mem.adjust_bot_relationship(PAIR, respect_delta=1, tension_delta=1)
        await self.mem.record_bot_banter(
            PAIR, self.name, note, "server_game_interference"
        )

    async def tick(self):
        await self.store.init()
        await self.restoration.restore()
        for key, control in await self.store.recent("chaos_control", 100):
            if control.get("restore_requested"):
                gid = int(key.rsplit(":", 1)[1])
                await self.restore_all(gid)
        for _, r in await self.store.recent("chaos_ping", 100, oldest=True):
            if (
                r["bot"] == self.name
                and r["state"] in {"intent", "applied"}
                and r["expires"] <= time.time()
            ):
                await self.cleanup_ping(r)
            elif (
                self.name == "wanderer"
                and r["state"] == "deleted"
                and r.get("exposure_allowed", True)
                and time.time() - r.get("deleted_at", 0) < 300
                and r["channel"] in self.cfg(r["guild_id"]).get("allowed_channels", [])
                and await self.enabled(r["guild_id"], "interference")
            ):
                channel = self.bot.get_channel(r["channel"])
                target = channel.guild.get_member(r["target"]) if channel else None
                if (
                    channel
                    and target
                    and public_channel(channel, target)
                    and (await self.store.prefs(target.id))["chaos_ping"]
                    and not quiet(await self.mem.get_user(target.id) or {})
                ):
                    if await self.store.claim(
                        "chaos:exposed:" + r["id"],
                        "chaos_interference",
                        {"state": "attempted"},
                    ):
                        await self.send(
                            channel,
                            "For the record: Scaramouche sent and deleted an opted-in prank ping. I cannot tell whether anyone saw a notification.",
                        )
                        await self.rivalry(
                            "Wanderer exposed Scaramouche's recorded prank; no claim about anyone's perception."
                        )
        for kind in ("wager", "court", "gossip"):
            for _, r in await self.store.recent("chaos_" + kind, 100, oldest=True):
                if r["state"] not in ACTIVE:
                    continue
                if r["expires"] <= time.time() or (
                    r["bot"] == self.name and not await self.enabled(r["guild_id"])
                ):
                    await self.store.transition(r["id"], ACTIVE, {"state": "cancelled"})
                    continue
                if kind == "court" and r["state"] == "awaiting_verdict":
                    await self.verdict(r)
        if self.name == "scaramouche" and time.time() - self.last_auto > 3600:
            self.last_auto = time.time()
            for gid, cfg in list(self.config.get("guilds", {}).items())[:20]:
                guild = self.bot.get_guild(int(gid))
                if not guild:
                    continue
                local = datetime.now(ZoneInfo(cfg.get("timezone", "UTC")))
                trigger = (
                    "birthday"
                    if (local.month, local.day) == (1, 3)
                    and "birthday" in cfg.get("events", [])
                    else "autonomous"
                )
                if trigger == "autonomous" and (
                    cfg.get("mode") != "AUTONOMOUS_SAFE" or secrets.randbelow(1000) != 0
                ):
                    continue
                with contextlib.suppress(ValueError, discord.HTTPException):
                    await self.sovereign(guild, 0, trigger)
        await self.store.prune()

    async def verdict(self, r):
        if self.name != r["bot"] and (
            not await self.enabled(r["guild_id"], "interference")
            or r["channel"] not in self.cfg(r["guild_id"]).get("allowed_channels", [])
        ):
            return  # An unavailable/disabled partner cannot dismiss the host's case.
        channel = self.bot.get_channel(r["channel"])
        target = channel.guild.get_member(r["target"]) if channel else None
        if not channel or not target or not public_channel(channel, target):
            if self.name == r["bot"]:
                await self.store.transition(r["id"], ACTIVE, {"state": "cancelled"})
            return
        if (
            self.name == "wanderer"
            and await self.enabled(r["guild_id"], "interference")
            and r["channel"] in self.cfg(r["guild_id"]).get("allowed_channels", [])
        ):
            try:
                await self.source(
                    channel,
                    r["source_message_id"],
                    member=target,
                    fingerprint=r["fingerprint"],
                    allow_report=r["evidence_kind"] == "playful_report",
                )
            except (ValueError, discord.HTTPException):
                verdict = "CASE DISMISSED — evidence is no longer verifiable."
            else:
                verdict = {
                    "admit": "GUILTY OF THEATRICAL GAMEPLAY — you admitted the playful charge. No penalty.",
                    "contest": "SCARAMOUCHE IS OVERREACTING — that evidence establishes no meaningful wrongdoing.",
                    "solved": "NOT GUILTY — puzzle solved. I am overruling the theatrics.",
                }[r["defense"]]
            claimed = await self.store.court_finish(r["id"], verdict)
            if claimed:
                await self.send(
                    channel,
                    f"Wanderer's defense, case {r['id']}: {verdict} Bragging rights only; no moderation action.",
                )
                await self.rivalry(
                    "Wanderer independently reviewed Scaramouche's voluntary court; the outcome stayed harmless."
                )
        elif self.name == r["bot"] and time.time() - r["defense_at"] > 45:
            if await self.store.court_finish(r["id"], "CASE DISMISSED"):
                await self.send(
                    channel,
                    f"Case {r['id']} dismissed. No defense bot answered; I will not invent a verdict on its behalf. No penalty.",
                )

    async def on_message(self, message):
        if (
            self.name != "scaramouche"
            or message.author.bot
            or not message.guild
            or not harmless(message.content)
        ):
            return
        if (
            self.cfg(message.guild.id).get("parody_mode") != "PARTY"
            or message.channel.id
            not in self.cfg(message.guild.id).get("allowed_channels", [])
            or not public_channel(message.channel)
        ):
            return
        if secrets.randbelow(1000) != 0:
            return
        if await self.enabled(message.guild.id, "parody"):
            with contextlib.suppress(ValueError, discord.HTTPException):
                await self.translate(message)

    async def dispatch(self, ctx, command, action, argument):
        await self.store.init()
        if action == "help":
            await self.send(
                ctx,
                "!chaos status|budget; managers: enable|disable|sovereign|restore-all; !chaos event challenge|tournament. !wager open @user dice|coin_flip|high_card|one_in_six bragging|favor; accept|reject|cancel <id>; balance. !court open @user (reply to public evidence), accept <id>, defend <id> <answer|admit|contest>, cancel <id>. !pranks parody|ping|gossip|court on/off; translate (reply); phantom @user; gossip @recipient (reply); status|off. Wanderer offers only fair dice for bragging and defends rather than opening cases.",
            )
            return
        if command == "pranks" and action in {"off", "forget"}:
            await self.forget(ctx.author.id)
            await self.send(
                ctx,
                "Your chaos consent is off; pending personal games and deliveries cancelled.",
            )
            return
        if not ctx.guild:
            raise ChaosError("A configured guild is required.")
        revoking = command == "pranks" and argument == "off"
        cancelling = command in {"wager", "court"} and action in {"cancel", "reject"}
        if (
            command != "chaos"
            and not revoking
            and not cancelling
            and not await self.enabled(ctx.guild.id)
        ):
            raise ChaosError("Server chaos is disabled here.")
        if (
            command in {"wager", "court"}
            and not cancelling
            and (
                ctx.channel.id not in self.cfg(ctx.guild.id).get("allowed_channels", [])
                or not await self.enabled(ctx.guild.id, command)
            )
        ):
            raise ChaosError("Game/channel not allowlisted.")
        if (
            command == "pranks"
            and action in {"translate", "phantom", "gossip"}
            and ctx.channel.id not in self.cfg(ctx.guild.id).get("allowed_channels", [])
        ):
            raise ChaosError("Channel not allowlisted.")
        await {
            "chaos": self.control,
            "wager": self.wager,
            "court": self.court,
            "pranks": self.pranks,
        }[command](ctx, action, argument)

    async def on_ready(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.loop())

    async def loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                if self.lock is None:
                    self.lock = asyncio.Lock()
                async with self.lock:
                    await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                if not self.error_reported:
                    self.error_reported = True
                    if self.owner_id:
                        with contextlib.suppress(Exception):
                            owner = self.bot.get_user(
                                self.owner_id
                            ) or await self.bot.fetch_user(self.owner_id)
                            await self.send(
                                owner,
                                "Server chaos maintenance needs attention. Recovery receipts retained; no source text or secrets attached. Use !chaos status / restore-all.",
                            )
            await asyncio.sleep(5)

    def install(self):
        self.bot.add_listener(self.on_ready, "on_ready")
        self.bot.add_listener(self.on_message, "on_message")
        close = self.bot.close

        async def closing():
            if self.task:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
            await close()

        self.bot.close = closing

        def register(name, route):
            async def command(ctx, action="status", *, argument=""):
                if self.lock is None:
                    self.lock = asyncio.Lock()
                async with self.lock:
                    try:
                        await self.dispatch(
                            ctx, route, action.lower(), argument.strip()
                        )
                    except ChaosError as exc:
                        await self.send(
                            ctx, str(exc)
                        )  # only deterministic local messages
                    except (ValueError, TypeError, KeyError):
                        await self.send(
                            ctx,
                            "Invalid game/configuration value. Check the feature guide; raw values are not included here.",
                        )
                    except discord.HTTPException:
                        await self.send(
                            ctx,
                            "Discord could not complete that step. Durable recovery/result receipts remain; check status rather than repeating the action.",
                        )

            self.bot.command(name=name)(command)

        routes = ("chaos", "wager", "court", "pranks")
        names = (
            routes
            if self.name == "scaramouche"
            else ("wanchaos", "challenge", "defense", "wanpranks")
        )
        for name, route in zip(names, routes):
            register(name, route)
