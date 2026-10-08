"""Offline command registration inventory. Uses synthetic credentials and isolated data."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

def main():
    with tempfile.TemporaryDirectory(prefix="command-inventory-") as temp:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        os.environ.update(GROQ_API_KEY="fake-test-key", GROQ_API_KEY_2="", GROQ_API_KEY_3="",
                          DISCORD_TOKEN="fake-test-token", BOT_DATA_DIR=temp,
                          TAROT_DB_PATH=str(Path(temp)/"tarot.sqlite3"),
                          BOT_INTEGRATIONS_CONFIG=str(Path(temp)/"absent.json"))
        import memory
        memory._data_dir = temp
        memory.DB_PATH = str(Path(temp)/"local.db")
        memory.SHARED_DB_PATH = str(Path(temp)/"shared.db")
        import bot
        prefix = sorted(bot.bot.all_commands)
        slash = sorted(command.name for command in bot.bot.tree.get_commands())
        baseline = json.loads((Path(__file__).resolve().parents[1]/"tests/legacy_command_surface.json").read_text())
        result = {
            "prefix_names_and_aliases": prefix,
            "slash_roots": slash,
            "missing_legacy_prefix": sorted(set(baseline["prefix"])-set(prefix)),
            "missing_legacy_slash": sorted(set(baseline["slash"])-set(slash)),
        }
        print("COMMAND_AUDIT_JSON=" + json.dumps(result, sort_keys=True))
        asyncio.run(bot.bot.close())
if __name__ == "__main__":
    main()
