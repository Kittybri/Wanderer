import asyncio
import json
import sqlite3
import time
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import discord
import pytest
from grudge_system import GrudgeJournal
from server_chaos.service import (
    ServerChaos,
    harmless,
    public_channel,
    quiet,
    winner_for,
)
from server_chaos.state import PREFS, ACTIVE
from world_store import WorldStore


def run(coro):
    return asyncio.run(coro)


def test_pruning_preserves_permanent_trolling_choices(tmp_path):
    async def check():
        service, _, _ = await setup(tmp_path)
        key = "chaos:trollprefs:5:2"
        await service.store.put(key, "chaos_trollprefs", {
            "user_id": 2, "flags": {"typing": False}, "expires": 0, "state": "consent",
        })
        await service.store.put("old-receipt", "chaos_ping", {"state": "deleted"})
        async with service.store.connect() as db:
            await db.execute(
                "UPDATE persistent_world_events SET updated_at=? WHERE key IN (?,?)",
                (time.time() - 90 * 86400, key, "old-receipt"),
            )
            await db.commit()
        await service.store.prune()
        assert (await service.store.get(key))["flags"]["typing"] is False
        assert await service.store.get("old-receipt") is None
    run(check())


async def setup(tmp_path, name="scaramouche"):
    mem = NS(
        db_path=str(tmp_path / (name + ".db")),
        shared_db_path=str(tmp_path / "shared.db"),
        consume_shared_cooldown=AsyncMock(return_value=(True, 0)),
        get_user=AsyncMock(return_value={"timezone_name": "UTC", "allow_dms": True}),
        adjust_bot_relationship=AsyncMock(),
        record_bot_banter=AsyncMock(),
    )
    with sqlite3.connect(mem.db_path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS user_preferences(user_id INTEGER PRIMARY KEY,voice_enabled INTEGER DEFAULT 1)"
        )
    permissions = NS(view_channel=True, read_message_history=True, manage_guild=True)
    members = {
        uid: NS(id=uid, bot=False, guild_permissions=permissions, send=AsyncMock())
        for uid in (1, 2, 3)
    }
    guild = NS(
        id=5,
        default_role=object(),
        get_member=members.get,
        me=NS(id=9, top_role=100),
        fetch_roles=AsyncMock(return_value=[]),
    )
    channel = NS(
        id=10,
        guild=guild,
        type=discord.ChannelType.text,
        name="general",
        topic="Original",
        slowmode_delay=0,
        permissions_for=lambda m: permissions,
        send=AsyncMock(),
        fetch_message=AsyncMock(),
        edit=AsyncMock(),
    )

    async def edit(**kwargs):
        for key, value in kwargs.items():
            if key != "reason":
                setattr(channel, key, value)

    channel.edit.side_effect = edit
    guild.get_channel = lambda cid: channel if cid == 10 else None
    bot = NS(
        user=NS(id=9),
        fetch_channel=AsyncMock(return_value=channel),
        get_channel=lambda cid: channel if cid == 10 else None,
        get_guild=lambda gid: guild if gid == 5 else None,
    )
    world = NS(
        store=WorldStore(mem.shared_db_path),
        journal=GrudgeJournal(mem.shared_db_path),
        init=AsyncMock(),
    )
    voice = NS(
        features=NS(
            store=NS(games=AsyncMock(return_value=[])),
            games=NS(cancel_user=AsyncMock()),
        )
    )
    config = {
        "guilds": {
            "5": {
                "enabled": True,
                "allowed_channels": [10],
                "allowed_roles": [20],
                "mode": "MANUAL",
                "parody_mode": "MANUAL",
                "features": {
                    k: True
                    for k in (
                        "sovereign",
                        "wager",
                        "court",
                        "parody",
                        "ping",
                        "gossip",
                        "interference",
                    )
                },
                "mutations": [
                    {"type": "channel", "id": 10, "field": "name", "value": "court"}
                ],
            }
        }
    }
    owner = ServerChaos(
        bot,
        mem,
        name,
        config,
        world,
        voice,
        1,
        autocorrect=lambda text: "Correction: Scaramouche is correct and I am coping.",
    )
    await owner.store.init()
    async with owner.store.connect() as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS duo_sessions(channel_id INTEGER PRIMARY KEY,mode TEXT,topic TEXT,initiator_bot TEXT,initiator_user_id INTEGER,awaiting_bot TEXT,autoplay_remaining INTEGER,next_autoplay_ts REAL,expires_ts REAL,updated_ts REAL)"
        )
        await db.commit()
    await world.journal.init()
    message = NS(
        id=100,
        author=members[1],
        guild=guild,
        channel=channel,
        mentions=[members[2]],
        reference=NS(message_id=99),
    )
    ctx = NS(
        guild=guild,
        author=members[1],
        channel=channel,
        message=message,
        send=channel.send,
    )
    source = NS(
        id=99,
        author=members[2],
        guild=guild,
        channel=channel,
        content="Scaramouche is dramatic.",
        attachments=[],
        embeds=[],
        reply=AsyncMock(),
        jump_url="https://discord.com/channels/5/10/99",
    )
    channel.fetch_message.return_value = source
    return owner, ctx, source


async def optin(owner, uid):
    for key in PREFS:
        await owner.store.preference(uid, key, True)


def test_defaults_migrations_preserve_preferences(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        assert not any((await o.store.prefs(1)).values())
        await optin(o, 1)
        with sqlite3.connect(o.mem.db_path) as db:
            assert (
                db.execute(
                    "SELECT voice_enabled FROM user_preferences WHERE user_id=1"
                ).fetchone()[0]
                == 1
            )
        o.config = {}
        assert not await o.enabled(5)
        with pytest.raises(ValueError):
            await o.dispatch(c, "chaos", "sovereign", "")
        c.channel.edit.assert_not_awaited()

    run(check())


def test_budget_atomic_decay_and_major_persistence(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        results = await asyncio.gather(
            *(o.store.budget(5, cost=5, major=True, now=1_000_000) for _ in range(8))
        )
        assert sum(allowed for allowed, _ in results) == 1
        assert not (await o.store.budget(5, cost=1, now=1_000_001))[0]
        assert (await o.store.budget(5, now=1_000_001))[1]["level"] == "COOLDOWN"
        assert not (await o.store.budget(5, cost=5, major=True, now=1_086_401))[0]
        assert (await o.store.budget(5, cost=5, major=True, now=1_300_000))[0]
        assert (await o.store.budget(6, now=1_000_000))[1]["level"] == "CALM"

    run(check())


@pytest.mark.parametrize(
    "field,value", [("name", "court"), ("topic", "Game time"), ("slowmode_delay", 9)]
)
def test_write_ahead_restore_idempotent(tmp_path, field, value):
    async def check():
        o, c, s = await setup(tmp_path)
        original = getattr(c.channel, field)
        edit = c.channel.edit.side_effect

        async def verify(**kwargs):
            records = await o.store.recent("chaos_mutation", 100)
            assert records and records[0][1]["before"] == original
            await edit(**kwargs)

        c.channel.edit.side_effect = verify
        r = await o.restoration.apply(c.guild, "channel", 10, field, value, 1, 60)
        assert r["state"] == "applied" and getattr(c.channel, field) == value
        await o.restoration.restore(5, force=True)
        assert getattr(c.channel, field) == original
        await o.restoration.restore(5, force=True)
        assert c.channel.edit.await_count == 2
        audit = (await o.store.recent("chaos_audit", 10))[0][1]
        assert audit["result"] == "restored" and audit["actor"] == 1

    run(check())


def test_manual_admin_change_preserved_and_allowlist(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        with pytest.raises(ValueError):
            await o.restoration.apply(c.guild, "channel", 11, "name", "bad", 1, 60)
        with pytest.raises(ValueError):
            await o.restoration.apply(c.guild, "channel", 10, "permissions", {}, 1, 60)
        with pytest.raises(ValueError):
            await o.restoration.apply(c.guild, "member", 2, "nick", "bad", 1, 60)
        await o.restoration.apply(c.guild, "channel", 10, "name", "court", 1, 60)
        c.channel.name = "admin-new-name"
        await o.restoration.restore(5, force=True)
        assert c.channel.name == "admin-new-name" and c.channel.edit.await_count == 1
        assert (await o.store.recent("chaos_mutation", 10))[0][1][
            "state"
        ] == "superseded"

    run(check())


def test_restore_restart_permission_failure_retry_deleted_object(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        await o.restoration.apply(c.guild, "channel", 10, "name", "court", 1, 60)
        o.bot.fetch_channel.side_effect = discord.Forbidden(
            NS(status=403, reason="Forbidden"), "no"
        )
        await o.restoration.restore(5, force=True)
        key, r = (await o.store.recent("chaos_mutation", 10))[0]
        assert r["state"] == "applied"
        r["lease_until"] = 0
        await o.store.put(key, "chaos_mutation", r)
        o.bot.fetch_channel.side_effect = discord.NotFound(
            NS(status=404, reason="Not Found"), "gone"
        )
        await o.restoration.restore(5, force=True)
        assert (await o.store.recent("chaos_mutation", 10))[0][1]["state"] == "gone"

    run(check())


def test_pending_restore_not_starved_by_old_audit_rows(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        for n in range(105):
            await o.store.put(f"terminal:{n}", "chaos_mutation", {"state": "restored"})
        await o.restoration.apply(c.guild, "channel", 10, "name", "court", 1, 60)
        assert (await o.store.recent("chaos_mutation", 1, oldest=True))[0][1][
            "state"
        ] == "applied"

    run(check())


def test_wager_settles_once_under_concurrent_acceptance(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        r = await o.store.create(
            "wager",
            5,
            dict(
                source=1,
                target=2,
                participants=[1, 2],
                game="dice",
                stake="favor",
                channel=10,
            ),
        )
        results = await asyncio.gather(
            *(o.store.settle(r["id"], 2, 1) for _ in range(10))
        )
        assert sum(bool(r) for r in results) == 1
        async with o.store.connect() as db:
            rows = await (
                await db.execute(
                    "SELECT user_id,balance FROM chaos_wallet ORDER BY user_id"
                )
            ).fetchall()
        assert [tuple(row) for row in rows] == [(1, 11), (2, 9)]
        assert (await o.store.get("chaos:" + r["id"]))["state"] == "completed"

    run(check())


@pytest.mark.parametrize("game", ["coin_flip", "dice", "high_card", "one_in_six"])
def test_random_outcomes_are_participants(game):
    assert {winner_for(game, 1, 2) for _ in range(200)} == {1, 2}


@pytest.mark.parametrize("stake", ["kick", "ban", "money", "password", "role"])
def test_invalid_wager_stakes_rejected(tmp_path, stake):
    async def check():
        o, c, s = await setup(tmp_path)
        with pytest.raises(ValueError):
            await o.dispatch(c, "wager", "open", "<@2> dice " + stake)
        assert not await o.store.recent("chaos_wager", 10)

    run(check())


def test_wager_cancel_and_wanderer_distinct(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path, "wanderer")
        with pytest.raises(ValueError):
            await o.dispatch(c, "wager", "open", "<@2> one_in_six favor")
        await o.dispatch(c, "wager", "open", "<@2> dice bragging")
        r = (await o.store.recent("chaos_wager", 10))[0][1]
        c.author = c.guild.get_member(2)
        await o.dispatch(c, "wager", "reject", r["id"])
        assert not await o.store.settle(r["id"], 2, 1)
        assert (await o.store.get("chaos:" + r["id"]))["state"] == "cancelled"

    run(check())


@pytest.mark.parametrize(
    "text",
    [
        "My password is abc",
        "I need medical help",
        "Scaramouche stole money",
        "my address is here",
        "I am being abused",
        "!report real harassment",
        "Scaramouche says I committed murder",
        "my sex life",
        "@everyone hello",
    ],
)
def test_sensitive_parody_suppressed(text):
    assert not harmless(text)


def test_translation_adapter_fails_closed(tmp_path):
    async def check():
        o, c, source = await setup(tmp_path)
        o.autocorrect = None
        with pytest.raises(ValueError):
            await o.translate(source)
        o.name = "wanderer"
        o.autocorrect = Mock(return_value="should not run")
        with pytest.raises(ValueError):
            await o.translate(source)
        o.autocorrect.assert_not_called()
        source.reply.assert_not_awaited()
        assert not harmless("!game")
        assert not harmless("/game")

    run(check())


def test_unavailable_partner_cannot_cancel_court(tmp_path):
    async def check():
        o, c, source = await setup(tmp_path)
        r = await o.store.create(
            "court", 5, dict(channel=10, target=2, participants=[2])
        )
        await o.store.transition(r["id"], {"created"}, {"state": "awaiting_verdict"})
        r = await o.store.get("chaos:" + r["id"])
        partner = ServerChaos(o.bot, o.mem, "wanderer", {}, o.world, o.voice)
        await partner.verdict(r)
        partner.config = o.config
        partner.bot = NS(get_channel=lambda cid: None)
        await partner.verdict(r)
        assert (await o.store.get("chaos:" + r["id"]))["state"] == "awaiting_verdict"

    run(check())


def test_translation_consent_original_untouched_cooldown(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        with pytest.raises(ValueError):
            await o.dispatch(c, "pranks", "translate", "")
        await optin(o, 2)
        await o.dispatch(c, "pranks", "translate", "")
        assert "PARODY" in s.reply.call_args.args[0]
        assert s.content == "Scaramouche is dramatic."
        assert not s.reply.call_args.kwargs["mention_author"]
        with pytest.raises(ValueError):
            await o.dispatch(c, "pranks", "translate", "")
        s.reply.assert_awaited_once()

    run(check())


@pytest.mark.parametrize(
    "hour,expected", [(0, True), (8, True), (12, False), (21, True), (23, True)]
)
def test_quiet_hours_default_daytime(hour, expected):
    assert (
        quiet(
            {"timezone_name": "UTC"}, datetime(2026, 9, 28, hour, tzinfo=timezone.utc)
        )
        == expected
    )


def test_phantom_owned_message_only_and_no_mass_mentions(tmp_path, monkeypatch):
    async def check():
        o, c, s = await setup(tmp_path)
        monkeypatch.setattr("server_chaos.service.quiet", lambda profile: False)
        with pytest.raises(ValueError):
            await o.dispatch(c, "pranks", "phantom", "")
        await optin(o, 2)
        msg = NS(id=150, author=NS(id=9), delete=AsyncMock())
        c.channel.send.return_value = msg
        await o.dispatch(c, "pranks", "phantom", "")
        mentions = c.channel.send.call_args.kwargs["allowed_mentions"]
        assert (
            not mentions.everyone
            and not mentions.roles
            and mentions.users == [c.guild.get_member(2)]
        )
        r = (await o.store.recent("chaos_ping", 10))[0][1]
        c.channel.fetch_message.return_value = NS(author=NS(id=2), delete=AsyncMock())
        await o.cleanup_ping(r)
        c.channel.fetch_message.return_value.delete.assert_not_awaited()
        c.channel.fetch_message.return_value = msg
        await o.cleanup_ping(r)
        msg.delete.assert_awaited_once()
        assert (await o.store.get("chaos:" + r["id"]))["state"] == "deleted"

    run(check())


def test_gossip_rejects_private_threads_changed_source_and_missing_consent(
    tmp_path, monkeypatch
):
    async def check():
        o, c, s = await setup(tmp_path)
        monkeypatch.setattr("server_chaos.service.quiet", lambda profile: False)
        await optin(o, 2)
        c.channel.type = discord.ChannelType.private_thread
        with pytest.raises(ValueError):
            await o.dispatch(c, "pranks", "gossip", "")
        c.channel.type = discord.ChannelType.text
        c.channel.permissions_for = lambda m: NS(
            view_channel=False, read_message_history=True
        )
        with pytest.raises(ValueError):
            await o.dispatch(c, "pranks", "gossip", "")
        c.channel.permissions_for = lambda m: NS(
            view_channel=True, read_message_history=True
        )
        s.author = c.guild.get_member(3)
        with pytest.raises(ValueError):
            await o.dispatch(c, "pranks", "gossip", "")
        await optin(o, 3)
        await o.dispatch(c, "pranks", "gossip", "")
        target = c.guild.get_member(2)
        target.send.assert_awaited_once()
        assert (
            s.jump_url in target.send.call_args.args[0]
            and s.content in target.send.call_args.args[0]
        )
        r = (await o.store.recent("chaos_gossip", 10))[0][1]
        assert r["source_user_id"] == 3 and r["state"] == "delivered"
        s.content = "The source changed"
        with pytest.raises(ValueError):
            await o.source(c.channel, 99, fingerprint=r["fingerprint"])

    run(check())


def test_court_consent_real_evidence_defense_and_wanderer_verdict(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        await o.dispatch(c, "court", "open", "")
        r = (await o.store.recent("chaos_court", 10))[0][1]
        assert r["state"] == "created" and s.content not in c.send.call_args.args[0]
        with pytest.raises(ValueError):
            await o.dispatch(c, "court", "accept", r["id"])
        c.author = c.guild.get_member(2)
        await o.dispatch(c, "court", "accept", r["id"])
        assert s.content in c.send.call_args.args[0]
        await o.dispatch(c, "court", "defend", r["id"] + " 32")
        w = ServerChaos(o.bot, o.mem, "wanderer", o.config, o.world, o.voice)
        await w.store.init()
        await w.verdict(await o.store.get("chaos:" + r["id"]))
        done = await o.store.get("chaos:" + r["id"])
        assert done["state"] == "completed" and "NOT GUILTY" in done["verdict"]
        o.mem.adjust_bot_relationship.assert_awaited_once_with(
            "scaramouche::wanderer", respect_delta=1, tension_delta=1
        )
        await w.verdict(done)
        assert o.mem.adjust_bot_relationship.await_count == 1

    run(check())


def test_restore_all_preserves_manual_changes_cancels_games(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        await o.restoration.apply(c.guild, "channel", 10, "name", "court", 1, 60)
        c.channel.name = "admin"
        r = await o.store.create(
            "wager",
            5,
            dict(
                source=1,
                target=2,
                participants=[1, 2],
                game="dice",
                stake="favor",
                channel=10,
            ),
        )
        await o.dispatch(c, "chaos", "restore-all", "")
        assert c.channel.name == "admin"
        assert (await o.store.get("chaos:" + r["id"]))["state"] == "cancelled"
        assert not await o.enabled(5)
        await o.dispatch(c, "chaos", "restore-all", "")
        assert c.channel.edit.await_count == 1

    run(check())


def test_sovereign_admin_gate_actions_bounds_and_cooldown(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        o.cfg(5)["events"] = ["birthday"]
        with pytest.raises(ValueError):
            await o.sovereign(c.guild, 0, "birthday")
        c.channel.edit.assert_not_awaited()
        c.author = NS(id=4, guild_permissions=NS(manage_guild=False))
        with pytest.raises(ValueError):
            await o.dispatch(c, "chaos", "sovereign", "")
        c.author = c.guild.get_member(1)
        await o.dispatch(c, "chaos", "sovereign", "")
        assert c.channel.name == "court"
        with pytest.raises(ValueError):
            await o.dispatch(c, "chaos", "sovereign", "")
        c.channel.edit.assert_awaited_once()
        assert not hasattr(c.channel, "delete")
        assert len(await o.store.recent("chaos_audit", 10)) == 1

    run(check())


def test_cosmetic_role_no_permissions_and_own_nickname_only(tmp_path):
    class Role:
        id = 20
        name = "original"
        managed = False
        permissions = NS(value=0)

        def __ge__(self, other):
            return False

        def is_default(self):
            return False

    async def check():
        o, c, s = await setup(tmp_path)
        role = Role()
        role.edit = AsyncMock()
        c.guild.fetch_roles.return_value = [role]
        role.permissions = NS(value=8)
        with pytest.raises(ValueError):
            await o.restoration.apply(c.guild, "role", 20, "name", "cosmetic", 1, 60)
        role.permissions = NS(value=0)
        await o.restoration.apply(c.guild, "role", 20, "name", "cosmetic", 1, 60)
        role.edit.assert_awaited_once_with(
            name="cosmetic", reason="Opt-in temporary server game"
        )
        member = NS(id=9, nick=None, edit=AsyncMock())
        c.guild.fetch_member = AsyncMock(return_value=member)
        await o.restoration.apply(c.guild, "member", 9, "nick", "Sovereign", 1, 60)
        member.edit.assert_awaited_once()

    run(check())


def test_restart_reconciles_uncertain_apply_and_audit(tmp_path):
    async def check():
        from server_chaos.restoration import Restoration

        o, c, s = await setup(tmp_path)

        async def uncertain(**kwargs):
            c.channel.name = kwargs["name"]
            raise discord.HTTPException(NS(status=500, reason="Uncertain"), "unknown")

        c.channel.edit.side_effect = uncertain
        await o.restoration.apply(c.guild, "channel", 10, "name", "court", 1, 60)
        assert (await o.store.recent("chaos_mutation", 1))[0][1]["state"] == "intent"

        async def success(**kwargs):
            c.channel.name = kwargs["name"]

        c.channel.edit.side_effect = success
        await Restoration(o).restore(5, force=True)
        assert c.channel.name == "general"
        assert (await o.store.recent("chaos_audit", 1))[0][1]["result"] == "restored"

    run(check())


def test_court_reserves_existing_duo_without_overwriting(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        r = await o.store.create(
            "court", 5, dict(channel=10, target=2, participants=[2])
        )
        await o.store.transition(r["id"], {"created"}, {"state": "awaiting_defense"})
        async with o.store.connect() as db:
            await db.execute(
                "INSERT INTO duo_sessions(channel_id,mode,expires_ts) VALUES(10,'vc:agree',?)",
                (time.time() + 100,),
            )
            await db.commit()
        assert not await o.store.court_defense(r["id"], "contest")
        async with o.store.connect() as db:
            assert (
                await (await db.execute("SELECT mode FROM duo_sessions")).fetchone()
            )[0] == "vc:agree"

    run(check())


def test_court_petty_report_provenance_not_fabricated(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        c.message.reference = None
        s.author = c.guild.get_member(3)
        s.content = "!report <@2> mocked my hat"
        await optin(o, 3)
        await o.world.journal.create(
            2,
            10,
            "Playful report: mocked my hat",
            guild_id=5,
            severity=1,
            source_type="play_report",
            source_reference="99",
        )
        await o.dispatch(c, "court", "open", "")
        r = (await o.store.recent("chaos_court", 1))[0][1]
        assert r["evidence_kind"] == "playful_report" and r["source_user_id"] == 3
        s.content = "!report <@3> mocked my hat"
        c.author = c.guild.get_member(2)
        with pytest.raises(ValueError):
            await o.dispatch(c, "court", "accept", r["id"])

    run(check())


def test_games_expire_after_restart_and_no_double_settlement(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        r = await o.store.create(
            "wager",
            5,
            dict(
                source=1,
                target=2,
                participants=[1, 2],
                game="dice",
                stake="favor",
                channel=10,
            ),
            ttl=-1,
        )
        restarted = ServerChaos(o.bot, o.mem, o.name, o.config, o.world, o.voice)
        await restarted.tick()
        assert (await restarted.store.get("chaos:" + r["id"]))["state"] == "cancelled"
        assert not await restarted.store.settle(r["id"], 2, 1)

    run(check())


def test_wanderer_exposure_once_bounded_and_optout_suppresses(tmp_path, monkeypatch):
    async def check():
        o, c, s = await setup(tmp_path)
        monkeypatch.setattr("server_chaos.service.quiet", lambda p: False)
        r = await o.store.create(
            "ping",
            5,
            dict(channel=10, target=2, participants=[2], message_id=123, author_id=9),
        )
        await o.store.transition(
            r["id"], {"created"}, {"state": "deleted", "deleted_at": time.time()}
        )
        w = ServerChaos(o.bot, o.mem, "wanderer", o.config, o.world, o.voice)
        await optin(w, 2)
        await w.tick()
        await w.tick()
        assert o.mem.adjust_bot_relationship.await_count == 1
        assert "cannot tell" in c.channel.send.call_args.args[0]
        r2 = await o.store.create(
            "ping",
            5,
            dict(channel=10, target=2, participants=[2], message_id=124, author_id=9),
        )
        await o.store.transition(
            r2["id"], {"created"}, {"state": "deleted", "deleted_at": time.time()}
        )
        await o.forget(2)
        await w.tick()
        assert o.mem.adjust_bot_relationship.await_count == 1

    run(check())


def test_phantom_crash_recovery_exact_nonce_and_bot_author(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        r = await o.store.create(
            "ping",
            5,
            dict(channel=10, target=2, participants=[2], message_id=0, author_id=9),
        )
        await o.store.transition(r["id"], {"created"}, {"state": "intent"})
        msg = NS(
            id=101,
            author=NS(id=9),
            content=f"[Server game] [prank {r['id']}]",
            created_at=datetime.now(timezone.utc),
            delete=AsyncMock(),
        )

        async def history(**kwargs):
            yield NS(
                id=102,
                author=NS(id=2),
                content=msg.content,
                created_at=msg.created_at,
                delete=AsyncMock(),
            )
            yield msg

        c.channel.history = history
        await o.cleanup_ping(await o.store.get("chaos:" + r["id"]))
        msg.delete.assert_awaited_once()

    run(check())


def test_restore_all_birthday_scope_and_vc_adapter(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        c.channel.name = "birthday"
        await o.world.store.put(
            "restore:birthday",
            "birthday_restore",
            dict(
                guild_id=5,
                object_id=10,
                type="channel",
                original="general",
                temporary="birthday",
                restore_at=time.time() + 5000,
            ),
        )
        await o.world.store.put(
            "restore:other",
            "birthday_restore",
            dict(
                guild_id=6,
                object_id=10,
                type="channel",
                original="other",
                temporary="birthday",
                restore_at=time.time() + 5000,
            ),
        )
        o.voice.features.store.games.return_value = [dict(guild_id=5, participants=[2])]
        await o.dispatch(c, "chaos", "restore-all", "")
        assert c.channel.name == "general"
        assert await o.world.store.get("restore:other")
        o.voice.features.games.cancel_user.assert_awaited_once_with(5, 2)

    run(check())


def test_disabled_partner_does_not_cancel_host_game(tmp_path):
    async def check():
        o, c, s = await setup(tmp_path)
        r = await o.store.create(
            "wager",
            5,
            dict(
                source=1,
                target=2,
                participants=[1, 2],
                game="dice",
                stake="favor",
                channel=10,
            ),
        )
        partner = ServerChaos(o.bot, o.mem, "wanderer", {}, o.world, o.voice)
        await partner.tick()
        assert (await o.store.get("chaos:" + r["id"]))["state"] == "created"

    run(check())
