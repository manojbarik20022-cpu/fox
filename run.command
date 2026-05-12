#!/usr/bin/env bash
# Fox2-clone launcher for macOS. Double-click in Finder to run.
# First launch creates .venv and installs dependencies (takes a few minutes).
# Subsequent launches start the GUI in ~1 second.
#
# If macOS blocks the file with "cannot be opened because it is from an
# unidentified developer", right-click → Open, or run in Terminal once:
#   chmod +x run.command
# then double-click again.

set -e
cd "$(dirname "$0")"

# ---- Check Python ----
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] python3 not found. Install via https://www.python.org/downloads/ or:"
    echo "    brew install python@3.12"
    read -p "Press Enter to exit..."
    exit 1
fi

# ---- Check ffmpeg ----
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[WARNING] ffmpeg not found. Video assembly will not work."
    echo "Install: brew install ffmpeg"
    sleep 2
fi

# ---- Create venv if missing ----
if [ ! -x ".venv/bin/python" ]; then
    echo "[setup] Creating virtual environment .venv ..."
    python3 -m venv .venv
    echo "[setup] Installing dependencies (may take a few minutes) ..."
    ".venv/bin/python" -m pip install --upgrade pip
    ".venv/bin/python" -m pip install -e ".[browser]"
fi

# ---- Install Playwright Chromium (one-time, ~200MB) ----
if [ ! -f ".venv/.playwright-chromium-installed" ]; then
    echo "[setup] Installing Chromium for browser automation (Flow, Grok, Nano Banana) ..."
    echo "[setup] This is a one-time ~200MB download."
    ".venv/bin/python" -m pip install -e ".[browser]" >/dev/null 2>&1 || true
    if ".venv/bin/python" -m playwright install chromium; then
        touch ".venv/.playwright-chromium-installed"
        echo "[setup] Chromium installed."
    else
        echo "[WARNING] Chromium installation failed. Browser providers (Flow/Grok/Nano Banana) will not work."
        sleep 3
    fi
fi

# ---- Launch GUI ----
exec ".venv/bin/python" -m fox2
