#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/scara-wanderer-bots}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$APP_DIR/.venv}"
DATA_DIR="${MEMORY_DATA_DIR:-/opt/scara-wanderer-data}"

install_packages() {
  if command -v dnf >/dev/null 2>&1; then
    echo "[oracle-free] Installing OS packages with dnf..."
    sudo dnf install -y \
      git \
      ffmpeg \
      python3 \
      python3-pip
  elif command -v apt-get >/dev/null 2>&1; then
    echo "[oracle-free] Installing OS packages with apt-get..."
    sudo apt-get update
    sudo apt-get install -y \
      git \
      ffmpeg \
      python3 \
      python3-venv \
      python3-pip
  else
    echo "[oracle-free] Unsupported package manager. Install git, ffmpeg, python3, and python3-pip manually."
    exit 1
  fi
}

install_packages

echo "[oracle-free] Creating persistent data directory..."
sudo mkdir -p "$DATA_DIR"
sudo chown "$(id -un)":"$(id -gn)" "$DATA_DIR"

echo "[oracle-free] Creating virtualenv..."
$PYTHON_BIN -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "[oracle-free] Upgrading pip..."
pip install --upgrade pip wheel

echo "[oracle-free] Installing Python dependencies..."
pip install -r "$APP_DIR/requirements.txt"

echo "[oracle-free] Done."
echo
echo "Next:"
echo "1. Copy env templates:"
echo "   cp $APP_DIR/deploy/oracle-free/scaramouche.env.example $APP_DIR/deploy/oracle-free/scaramouche.env"
echo "   cp $APP_DIR/deploy/oracle-free/wanderer.env.example $APP_DIR/deploy/oracle-free/wanderer.env"
echo "2. Fill in the real secrets."
echo "3. Copy the service files into /etc/systemd/system/ and enable them."
