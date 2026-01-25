#!/bin/bash
# Lortnoc Universal Update Script
# Usage: ./update.sh [client|monitor]
set -e

MODE=$1

# Paths
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "   LORTNOC UPDATER"
echo "========================================="
cd "$REPO_ROOT"

# --- Environment Check -------------------------------------------------------
if [ "$MODE" != "client" ] && [ "$MODE" != "monitor" ]; then
  echo "Error: Invalid mode '$MODE'. Supported modes are 'client' and 'monitor'."
  exit 1
fi


# --- Update Process -----------------------------------------------------------
echo "[*] Starting Lortnoc Self-Update ($MODE)..."

# Check if we have uncommitted changes (ignore untracked files)
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "[!] Uncommitted changes detected. Please commit or stash them before updating."
  exit 1
fi

# Update Codebase
git pull origin master
if [ $? -ne 0 ]; then
  echo "[!] Git pull failed. Maybe local changes preventing pull? Aborting."
  exit 1
fi

if [ "$MODE" == "client" ]; then
  # Update Dependencies
  VENV_PIP="lortnoc_client/install/.venv/bin/pip"
  REQ_FILE="lortnoc_client/tools/scripts/requirements.txt"
  echo "[+] Updating Python dependencies from $REQ_FILE..."
  "$VENV_PIP" install -r "$REQ_FILE"

  # Restart Service (Native Systemd)
  SERVICE_FILE="/etc/systemd/system/lortnoc-client.service"
  if [ -f "$SERVICE_FILE" ]; then
    echo "[+] Restarting Service 'lortnoc-client'..."
    sudo systemctl restart lortnoc-client
  fi

elif [ "$MODE" == "monitor" ]; then
  # Restart Docker Container
  cd lortnoc_monitor
  echo "[+] Rebuilding Docker Container..."
  make build
  echo "[+] Restarting Container..."
  make run
fi

echo "[✓] Lortnoc Update Complete."
