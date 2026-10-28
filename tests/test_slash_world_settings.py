"""Slash-first world discovery preserves legacy commands and user-scoped settings."""
import asyncio
from types import SimpleNamespace

import discord
from discord.ext import commands

from command_help import public_catalog
from persistent_world import PersistentWorld


def test_world_preferences_are_user_scoped_and_validate_values(tmp_path):
    async def check():
        values = {}

        async def get(uid):
            return {"grudge_enabled": bool(values.get((uid, "grudge_enabled"), True)),
                    "lullaby_enabled": bool(values.get((uid, "lullaby_enabled"), False)),
                    "lullaby_start_hour": values.get((uid, "lullaby_start_hour"), 23)}

        async def set_pref(uid, key, value):
            values[(uid, key)] = value

        mem = SimpleNamespace(shared_db_path=str(tmp_path / "shared.db"),
                              get_user_preferences=get, set_user_preference=set_pref)
        world = PersistentWorld("wanderer", mem, {})
        assert "Lullaby: True" in await world.preferences(1, "lullaby", "on")
        assert "Lullaby: False" in await world.preferences(2)
        assert "Start hour: 20" in await world.preferences(1, "lullaby_hour", "20")
        assert "Use /world prefs" in await world.preferences(1, "lullaby_hour", "19")
        assert values[(1, "lullaby_start_hour")] == 20

    asyncio.run(check())


def test_legacy_world_commands_remain_callable_but_leave_public_help():
    async def check():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        for name in ("world", "worldadd", "worldprefs"):
            async def handler(ctx):
                pass
            bot.command(name=name)(handler)
        assert all(bot.get_command(name) for name in ("world", "worldadd", "worldprefs"))
        labels = [field.name for page in public_catalog(bot) for field in page.fields]
        assert not any(label in labels for label in ("!world", "!worldadd", "!worldprefs"))
        await bot.close()

    asyncio.run(check())
