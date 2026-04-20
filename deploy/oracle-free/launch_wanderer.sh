#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/scara-wanderer-bots}"
cd "$APP_DIR"
source "$APP_DIR/.venv/bin/activate"
exec python3 wanderer_bot.py

