"""Validate actual runtime wiring in a disposable process and data directory."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

def main():
    with tempfile.TemporaryDirectory(prefix="preservation-check-") as temp:
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root))
        os.environ.update(GROQ_API_KEY="fake-test-key", GROQ_API_KEY_2="", GROQ_API_KEY_3="",
                          DISCORD_TOKEN="fake-test-token", BOT_DATA_DIR=temp, MEMORY_DATA_DIR=temp,
                          TAROT_DB_PATH=str(Path(temp)/"tarot.sqlite3"),
                          BOT_INTEGRATIONS_CONFIG=str(Path(temp)/"absent.json"))
        import memory
        memory._data_dir = temp
        memory.DB_PATH = str(Path(temp)/"local.db")
        memory.SHARED_DB_PATH = str(Path(temp)/"shared.db")
        from preservation_probe import collect
        data = asyncio.run(collect())
        import bot
        from preservation_contract import validate
        errors = validate(bot, data["help"])
        print(json.dumps({"errors": errors, "prefix_commands": len(data["prefix"]),
                          "slash_entries": len(data["slash"]), "help_chars": len(data["help"])}))
        return bool(errors)
if __name__ == "__main__":
    raise SystemExit(main())
