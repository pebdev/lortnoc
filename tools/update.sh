#!/bin/bash

# Lortnoc Universal Update Script
# Usage: ./update.sh [client|monitor]

MODE=$1

# Get the absolute path of the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Root of the repo is one level up from tools/
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT" || exit 1

if [ -z "$MODE" ]; then
    echo "Usage: $0 [client|monitor]"
    exit 1
fi

echo "[*] Starting Lortnoc Self-Update ($MODE)..."

# 1. Update Codebase
echo "[+] Pulling latest changes from Git..."
git pull origin master

if [ $? -ne 0 ]; then
    echo "[!] Git pull failed. Maybe local changes preventing pull? Aborting."
    exit 1
fi

# 2. Update based on Role
if [ "$MODE" == "client" ]; then
    echo "[*] Updating Client..."

    # Update Dependencies
    REQ_FILE="lortnoc_client/tools/requirements.txt"
    if [ -f "$REQ_FILE" ]; then
        echo "[+] Updating Python dependencies from $REQ_FILE..."

        # Check for Virtual Environment
        VENV_PIP="lortnoc_client/venv/bin/pip"
        if [ -f "$VENV_PIP" ]; then
            echo "[*] Using Virtual Environment pip: $VENV_PIP"
            "$VENV_PIP" install -r "$REQ_FILE"
        else
            echo "[!] Virtual Environment not found. Using system pip."
            # Using sys.executable to ensure we use the active python environment if possible,
            # but this is a bash script. 'pip' is assumed to be the correct one in the env.
            pip install -r "$REQ_FILE"
        fi
    else
        echo "[!] Warning: Requirements file not found at $REQ_FILE"
    fi

    # Restart Service (Native Systemd)
    echo "[+] Restarting Service 'lortnoc-client'..."
    # This requires sudo privileges or being root
    sudo systemctl restart lortnoc-client

    echo "[✓] Client Update Complete."

elif [ "$MODE" == "monitor" ]; then
    echo "[*] Updating Monitor..."

    if [ ! -d "lortnoc_monitor" ]; then
         echo "[!] Error: lortnoc_monitor directory not found."
         exit 1
    fi

    cd lortnoc_monitor

    echo "[+] Rebuilding Docker Container..."
    make build

    echo "[+] Restarting Container..."
    make run

    echo "[✓] Monitor Update Complete."

else
    echo "[!] Unknown mode: $MODE (Supported: client, monitor)"
    exit 1
fi
