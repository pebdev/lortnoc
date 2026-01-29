#!/bin/bash
########################################################################################################################
# Project : Lortnoc
# Author  : PEB <pebdev@lavache.com>
# Date    : 28.01.2026
########################################################################################################################
# Copyright (C) 2026
# This file is copyright under the latest version of the EUPL.
# Please see LICENSE file for your rights under this license.
########################################################################################################################
set -e

# Get script location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INSTALL_DIR="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# --- UPDATE ------------------------------------------------------------------
echo "[*] Checking for updates..."
BRANCH="feature/major-update"
INSTALLER_URL="https://raw.githubusercontent.com/pebdev/lortnoc/$BRANCH/lortnoc_client/tools/scripts/install_client.sh"
curl -sL "$INSTALLER_URL" | bash -s -- "$INSTALL_DIR"

# --- LAUNCH ------------------------------------------------------------------
echo "[*] Launching Lortnoc Client..."
cd "$INSTALL_DIR"
export PYTHONPATH="$PYTHONPATH:$INSTALL_DIR"

PYTHON_BIN="python3"
if [ -f ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

exec "$PYTHON_BIN" lortnoc_client/sources/main.py
