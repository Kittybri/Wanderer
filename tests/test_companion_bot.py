import asyncio
import base64
import json
import sqlite3
import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import discord
from discord.ext import commands
from home.bot_integration import HomeBot
from home.companion_bot import CompanionBot, due_soon


def run(coro):
    return asyncio.run(coro)


def setup(tmp_path):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    mem = NS(
        shared_db_path=str(tmp_path / "shared.db"),
        get_user=AsyncMock(return_value={}),
        consume_shared_cooldown=AsyncMock(return_value=(True, 0)),
        respects_dm_timing=AsyncMock(return_value=True),
        can_dm_user=AsyncMock(return_value=True),
        set_dm_sent=AsyncMock(),
    )
    home = HomeBot("scaramouche", bot, mem, {"enabled": True}, AsyncMock(), 1)
    home.client.call = AsyncMock(return_value={"ok": True})
    pc = CompanionBot(
        home,
        vision=AsyncMock(
            return_value='{"category":"coding","confidence":0.95,"sensitive":false,"summary":"SECRET"}'
        ),
    )
    pc.install()
    return pc


def test_owner_private_commands_and_shared_optout(tmp_path):
    async def check():
        pc = setup(tmp_path)
        ctx = NS(author=NS(id=2), guild=None, reply=AsyncMock())
        cmd = pc.home.bot.get_command("pc").callback
        await cmd(ctx, "on")
        pc.home.client.call.assert_not_awaited()
        ctx.author.id, ctx.guild = 1, NS(id=5)
        await cmd(ctx, "on")
        pc.home.client.call.assert_not_awaited()
        ctx.guild = None
        await cmd(ctx, "on")
        assert (await pc.preference(1))["enabled"]
        assert not (await pc.preference(2))["enabled"]
        await cmd(ctx, "off")
        assert not (await pc.preference(1))["enabled"]
        pc.home.client.call.assert_awaited_with("pc_forget", 1)
        await pc.home.bot.close()

    run(check())


def test_pending_deletion_survives_restart_and_retries(tmp_path):
    async def check():
        pc = setup(tmp_path)
        await pc.preference(1, enabled=True)
        pc.home.client.call.return_value = {"ok": False}
        assert not await pc.forget(1)
        assert (await pc.preference(1))["pending_delete"]
        other = CompanionBot(pc.home)
        assert (await other.preference(1))["pending_delete"]
        pc.home.client.call.return_value = {"ok": True}
        await other.tick()
        assert not (await other.preference(1))["pending_delete"]
        assert not (await other.preference(1))["enabled"]
        await pc.home.bot.close()

    run(check())


def test_vision_ephemeral_failure_sensitive_and_optout(tmp_path):
    async def check():
        pc = setup(tmp_path)
        await pc.preference(1, enabled=True)
        pc.home.client.call.return_value = {"ok": True, "consent": {"screen": True}}

        def image():
            return {
                "ok": True,
                "screen": {
                    "image": base64.b64encode(b"\xff\xd8FAKEIMAGE").decode(),
                    "app": "Editor",
                },
            }

        result = image()
        assert await pc.analyze(1, result) == "Possibly viewing coding content."
        assert "screen" not in result and "SECRET" not in json.dumps(pc.screens)
        pc.vision.return_value = (
            '{"category":"coding","confidence":0.95,"sensitive":true}'
        )
        assert await pc.analyze(1, image()) == "unknown"
        pc.vision.side_effect = RuntimeError("provider_secret")
        assert "unavailable" in await pc.analyze(1, image())
        await pc.preference(1, enabled=False)
        pc.vision.reset_mock()
        assert "unavailable" in await pc.analyze(1, image())
        pc.vision.assert_not_awaited()
        with sqlite3.connect(pc.home.mem.shared_db_path) as db:
            assert "FAKEIMAGE" not in str(list(db.iterdump()))
        await pc.home.bot.close()

    run(check())


def test_proactive_quiet_serious_and_cooldown_gates(tmp_path):
    async def check():
        pc = setup(tmp_path)
        await pc.preference(1, enabled=True)
        pc.home.bot.fetch_user = AsyncMock(return_value=NS(send=AsyncMock()))
        local = {
            "app": "Editor",
            "category": "coding",
            "duration_seconds": 7200,
            "idle_state": "ACTIVE",
            "updated_at": time.time(),
            "event": "",
        }
        pc.home.client.call.return_value = {"ok": True, "presence": local}
        user = {
            "proactive": True,
            "allow_dms": True,
            "quiet_hours_start": 0,
            "quiet_hours_end": 0,
        }
        pc.home.mem.get_user.return_value = user
        pc.observe_message(NS(author=NS(id=1), content="medical emergency"))
        await pc.tick()
        pc.home.bot.fetch_user.assert_not_awaited()
        pc.suppressed.clear()
        pc.last_tick = 0
        await pc.tick()
        pc.home.bot.fetch_user.assert_awaited_once_with(1)
        pc.home.mem.consume_shared_cooldown.assert_awaited_with("pc_reaction:1", 21600)
        pc.last_tick = 0
        pc.home.mem.consume_shared_cooldown.return_value = (False, 60)
        await pc.tick()
        assert pc.home.bot.fetch_user.await_count == 1
        await pc.home.bot.close()

    run(check())


def test_google_context_reads_only_boolean():
    async def check():
        from datetime import datetime, timezone

        tasks = NS(
            ready=True,
            list_tasks=AsyncMock(
                return_value={
                    "items": [
                        {
                            "title": "PRIVATE",
                            "due": datetime.now(timezone.utc).isoformat(),
                        }
                    ]
                }
            ),
        )
        assert await due_soon(tasks) is True
        tasks.list_tasks.return_value = {
            "items": [
                {"status": "completed", "due": datetime.now(timezone.utc).isoformat()}
            ]
        }
        assert await due_soon(tasks) is False

    run(check())
