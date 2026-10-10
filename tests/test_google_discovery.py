"""Discovery and private slash response regressions; no network or real tokens."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from discord.ext import commands
import pytest

from connections.discord_ui import ConnectionsController, GOOGLE_HELP
from connections.security import ConnectionError


@pytest.mark.parametrize("connected", [False, True])
def test_slash_is_publicly_discoverable_but_panel_is_private_and_user_bound(connected):
    async def run():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        service = SimpleNamespace(
            configured=True,
            status=AsyncMock(return_value={
                "status": "CONNECTED" if connected else "NOT_CONNECTED",
                "modules": ["calendar", "tasks"] if connected else [],
                "grants": {"scaramouche": True} if connected else {},
                "revision": "fake-revision", "masked_identity": "t***@***" if connected else "",
            }),
            pending=AsyncMock(return_value=None),
            create_session=AsyncMock(return_value="https://example.test/oauth/google/start/fake"),
        )
        controller = ConnectionsController(bot, service, SimpleNamespace(), "wanderer", AsyncMock(return_value=False)).install()
        interaction = SimpleNamespace(user=SimpleNamespace(id=987),
                                      response=SimpleNamespace(defer=AsyncMock()),
                                      edit_original_response=AsyncMock())
        await bot.tree.get_command("google").callback(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        service.status.assert_awaited_once_with(987)
        payload = interaction.edit_original_response.call_args.kwargs
        assert payload["embed"].title == "Connected Accounts"
        assert payload["view"].user_id == 987
        assert not payload["allowed_mentions"].everyone
        labels = [child.label for child in payload["view"].children]
        assert ("Connect Google" in labels) is not connected
        if not connected:
            service.create_session.assert_awaited_once_with(987, "wanderer")
        else:
            service.create_session.assert_not_awaited()
        stranger = SimpleNamespace(user=SimpleNamespace(id=988),
                                   response=SimpleNamespace(send_message=AsyncMock()))
        assert not await payload["view"].interaction_check(stranger)
        assert stranger.response.send_message.call_args.kwargs["ephemeral"] is True
        await bot.close()
    asyncio.run(run())


@pytest.mark.parametrize("failure", [ConnectionError("RESET_PENDING"), RuntimeError("fake-sensitive-token")])
def test_slash_errors_stay_private_and_do_not_expose_exception(failure):
    async def run():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        controller = ConnectionsController(bot, None, None, "scaramouche", None)
        controller.panel = AsyncMock(side_effect=failure)
        interaction = SimpleNamespace(user=SimpleNamespace(id=987),
                                      response=SimpleNamespace(defer=AsyncMock()),
                                      edit_original_response=AsyncMock())
        await controller.slash_panel(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        payload = interaction.edit_original_response.call_args.kwargs
        assert "fake-sensitive-token" not in payload["content"]
        assert payload["embed"] is None and payload["view"] is None
        await bot.close()
    asyncio.run(run())


def test_actual_character_help_prominently_lists_google_without_embed_overflow():
    # Execute only the actual help function, without starting the monolithic bot.
    source = ast.parse(Path("bot.py").read_text())
    function = next(node for node in source.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "help_cmd")
    function.decorator_list = []
    # Focused Google presentation test; actual registry coverage is in test_preservation.
    registry = SimpleNamespace(walk_commands=lambda: [],
                               tree=SimpleNamespace(walk_commands=lambda: []))
    namespace = {"discord": discord, "bot": registry,
                 "log_error": lambda *args: pytest.fail("Help failed")}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "bot.py", "exec"), namespace)
    ctx = SimpleNamespace(send=AsyncMock())
    asyncio.run(namespace["help_cmd"](ctx))
    pages = []
    for call in ctx.send.call_args_list:
        pages.extend(call.kwargs.get("embeds", []))
        if call.kwargs.get("embed"):
            pages.append(call.kwargs["embed"])
    assert pages and GOOGLE_HELP in pages[0].description
    assert all(len(p.fields) <= 25 and len(p) <= 6000 for p in pages)
    assert "!google" in GOOGLE_HELP and "/google" in GOOGLE_HELP


def test_single_command_sync_preserves_legacy_remote_commands_and_runs_once():
    async def run():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none(), application_id=123)
        controller = ConnectionsController(bot, None, None, "scaramouche", None, sync_google=True).install()
        bot.http.upsert_global_command = AsyncMock()
        bot.tree.sync = AsyncMock(side_effect=AssertionError("Must not bulk replace legacy commands"))
        await controller.sync_google_command()
        await controller.sync_google_command()
        bot.http.upsert_global_command.assert_awaited_once()
        args = bot.http.upsert_global_command.call_args.args
        assert args[0] == 123 and args[1]["name"] == "google"
        bot.tree.sync.assert_not_awaited()
        await bot.close()
    asyncio.run(run())
