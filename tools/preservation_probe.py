"""Offline runtime evidence; never writes expected manifests."""
import asyncio
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

async def collect():
    import bot
    from preservation_contract import inventory
    result = inventory(bot.bot)
    result["sources"] = {}
    for command in bot.bot.walk_commands():
        try:
            result["sources"][command.qualified_name] = inspect.getsource(command.callback)
        except (OSError, TypeError):
            result["sources"][command.qualified_name] = ""
    ctx = SimpleNamespace(send=AsyncMock(), reply=AsyncMock(), author=SimpleNamespace(id=42))
    await bot.help_cmd(ctx)
    result["help"] = "\n".join(
        str(call.args) + " " + " ".join(str(e.to_dict()) for e in call.kwargs.get("embeds", []))
        for call in ctx.send.call_args_list)
    result["globals"] = {}
    for name, obj in vars(bot).items():
        if name in {"WORLD", "HOME", "PC", "VOICE_CONVERSATION", "CHAOS", "TAROT", "CONNECTIONS_UI",
                    "CONNECTIONS", "CLOUD_INTEGRATIONS", "PROVIDER_STATUS", "mem", "self_store", "FACE_PROFILES"}:
            result["globals"][name] = [type(obj).__module__, type(obj).__name__]
    result["privacy"] = sorted(bot.PRIVACY_DELETION.stages)
    await bot.bot.close()
    return result

def main():
    with tempfile.TemporaryDirectory(prefix="preservation-probe-") as temp:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        os.environ.update(GROQ_API_KEY="fake-test-key", GROQ_API_KEY_2="", GROQ_API_KEY_3="",
                          DISCORD_TOKEN="fake-test-token", BOT_DATA_DIR=temp, MEMORY_DATA_DIR=temp,
                          TAROT_DB_PATH=str(Path(temp)/"tarot.sqlite3"),
                          BOT_INTEGRATIONS_CONFIG=str(Path(temp)/"absent.json"))
        import memory
        memory._data_dir = temp
        memory.DB_PATH = str(Path(temp)/"local.db")
        memory.SHARED_DB_PATH = str(Path(temp)/"shared.db")
        print("PRESERVATION_JSON=" + json.dumps(asyncio.run(collect()), sort_keys=True))
if __name__ == "__main__":
    main()
