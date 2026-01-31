#!/bin/bash
########################################################################################################################
# Project : Lortnoc
# Author  : PEB <pebdev@lavache.com>
# Date    : 29.01.2026
########################################################################################################################
# Installer expects: <component> <install_dir>
set -e

# --- Configurations ---------------------------------------------------------------------------------------------------
COMPONENT="$1"
INSTALLER_URL="https://raw.githubusercontent.com/pebdev/lortnoc/feature/major-update/tools/scripts/installer.sh"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Get script location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INSTALL_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$INSTALL_DIR"


# --- Argument Handling ------------------------------------------------------------------------------------------------
if [[ "$COMPONENT" != "client" && "$COMPONENT" != "monitor" ]]; then
  echo -e "${RED}Error: Invalid argument. Usage: $0 <client|monitor>${NC}"
  exit 1
fi


# --- UPDATE -----------------------------------------------------------------------------------------------------------
echo "[*] Checking updates for $COMPONENT..."
if command -v curl &> /dev/null; then
  TEMP_INSTALLER=$(mktemp)
  if curl -fsL "$INSTALLER_URL" -o "$TEMP_INSTALLER"; then
    bash "$TEMP_INSTALLER" "$COMPONENT" "$INSTALL_DIR"
    rm "$TEMP_INSTALLER"
  else
    echo -e "${YELLOW}[!] Update check skipped (Remote installer unavailable).${NC}"
  fi
else
  echo -e "${YELLOW}[!] curl missing, skipping update.${NC}"
fi


# --- LAUNCH -----------------------------------------------------------------------------------------------------------
cd "$INSTALL_DIR"
export PYTHONPATH="$PYTHONPATH:$INSTALL_DIR"

PYTHON_BIN="python3"
[ -f ".venv/bin/python" ] && PYTHON_BIN=".venv/bin/python"
echo -e "${BLUE}[*] Starting $COMPONENT...${NC}"
exec "$PYTHON_BIN" lortnoc_$COMPONENT/sources/main.py
