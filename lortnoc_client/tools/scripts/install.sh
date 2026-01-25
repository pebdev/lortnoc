#!/bin/bash
set -e

echo "========================================="
echo "   LORTNOC CLIENT INSTALLATION"
echo "========================================="

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed."
    exit 1
fi

echo "[+] Python3 found."

# 2. Setup Virtual Environment
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv $VENV_DIR
fi

echo "[+] Virtual environment ready."

# 3. Install Dependencies
echo "[*] Installing dependencies..."
./$VENV_DIR/bin/pip install -r requirements.txt
# Ensure lortnoc_core is accessible (simulated by repo structure, but we can install it cleanly given a setup.py, or just rely on path)
# Here we rely on main.py handling the path.

echo "[+] Dependencies installed."

# 4. Configuration
CONFIG_FILE="config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo ""
    echo "--- CONFIGURATION ---"
    read -p "Enter Discord Bot Token: " TOKEN
    read -p "Enter Channel ID: " CHANNEL_ID

    cat > $CONFIG_FILE <<EOF
{
    "token": "$TOKEN",
    "channel_id": $CHANNEL_ID
}
EOF
    echo "[+] Configuration saved to $CONFIG_FILE."
else
    echo "[+] Configuration file exists."
fi

# 5. Create Run Script
RUN_SCRIPT="run.sh"
cat > $RUN_SCRIPT <<EOF
#!/bin/bash
cd "\$(dirname "\$0")"
./$VENV_DIR/bin/python main.py
EOF
chmod +x $RUN_SCRIPT

echo ""
echo "========================================="
echo "   INSTALLATION COMPLETE"
echo "========================================="
echo "You can now start the client with:"
echo "  ./run.sh"
echo ""
echo "To run in background:"
echo "  nohup ./run.sh > client.log 2>&1 &"
echo "========================================="
