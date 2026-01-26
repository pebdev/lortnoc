#!/bin/bash
set -e

# Configurations
REPO_URL="https://api.github.com/repos/pebdev/lortnoc/releases/latest"
SERVICE_NAME="lortnoc-client"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}   LORTNOC CLIENT INSTALLER / UPDATER    ${NC}"
echo -e "${BLUE}=========================================${NC}"


# --- Environment Check -------------------------------------------------------
for cmd in curl tar python3; do
  if ! command -v $cmd &> /dev/null; then
    echo -e "${RED}Error: $cmd is required.${NC}"
    exit 1
  fi
done

# Argument handling for INSTALL_DIR
if [ -z "$1" ]; then
  echo -e "${RED}Error: Usage: $0 <install_dir>${NC}"
  exit 1
fi

# Ensure absolute path
INSTALL_DIR=$(cd "$1" && pwd)
mkdir -p "$INSTALL_DIR"
echo -e "${YELLOW}[*] Target Directory : $INSTALL_DIR${NC}"


# --- Get Latest Release Info from GitHub --------------------------------------
echo -e "${YELLOW}[*] Checking for updates...${NC}"
LATEST_RELEASE=$(curl -s $REPO_URL)
LATEST_VERSION=$(echo "$LATEST_RELEASE" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
TARBALL_URL=$(echo "$LATEST_RELEASE" | grep '"tarball_url":' | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z "$LATEST_VERSION" ]; then
  echo -e "${RED}Error: Could not fetch latest release version. Ensure the repo has at least one release.${NC}"
  exit 1
fi


# --- Check Local Version -------------------------------------------------------
CURRENT_VERSION="none"
if [ -f "$INSTALL_DIR/VERSION" ]; then
  CURRENT_VERSION=$(cat "$INSTALL_DIR/VERSION")
fi

echo -e "    Local Version  : $CURRENT_VERSION"
echo -e "    Latest Version : $LATEST_VERSION"

if [ "$CURRENT_VERSION" == "$LATEST_VERSION" ]; then
  echo -e "${GREEN}[✓] System is up to date.${NC}"
  exit 0
fi


# --- Download and Install ------------------------------------------------------
echo -e "${YELLOW}[*] Downloading version $LATEST_VERSION...${NC}"
TEMP_DIR=$(mktemp -d)
curl -sL "$TARBALL_URL" | tar -xz -C "$TEMP_DIR" --strip-components=1

echo -e "${YELLOW}[*] Installing files to $INSTALL_DIR...${NC}"
mkdir -p "$INSTALL_DIR"

# Backup config if exists
if [ -f "$INSTALL_DIR/config/config.json" ]; then
  cp "$INSTALL_DIR/config/config.json" "$TEMP_DIR/config.json.bak"
fi

# Copy necessary folders (Core + Client)
mkdir -p "$INSTALL_DIR/lortnoc_core"
mkdir -p "$INSTALL_DIR/lortnoc_client"
mkdir -p "$INSTALL_DIR/config"
cp -R "$TEMP_DIR/lortnoc_core/"* "$INSTALL_DIR/lortnoc_core/"
cp -R "$TEMP_DIR/lortnoc_client/"* "$INSTALL_DIR/lortnoc_client/"

# Copy template config only
if [ -f "$TEMP_DIR/config/config_template.json" ]; then
  cp "$TEMP_DIR/config/config_template.json" "$INSTALL_DIR/config/"
fi

# Restore config if backed up
if [ -f "$TEMP_DIR/config.json.bak" ]; then
  mv "$TEMP_DIR/config.json.bak" "$INSTALL_DIR/config/config.json"
fi


# --- Virtual Environment Setup -------------------------------------------------
echo -e "${YELLOW}[*] Setting up Python Environment...${NC}"
if [ ! -d "$INSTALL_DIR/.venv" ]; then
  python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/lortnoc_client/tools/scripts/requirements.txt" --upgrade


# --- Finalize -----------------------------------------------------------------
echo "$LATEST_VERSION" > "$INSTALL_DIR/VERSION"
rm -rf "$TEMP_DIR"

# Create/Update Launcher
cat > "$INSTALL_DIR/run.sh" <<EOF
#!/bin/bash
cd "$INSTALL_DIR"
export PYTHONPATH="\$PYTHONPATH:$INSTALL_DIR"
"$INSTALL_DIR/.venv/bin/python" lortnoc_client/sources/main.py
EOF
chmod +x "$INSTALL_DIR/run.sh"

# Create Update Script
cat > "$INSTALL_DIR/update.sh" <<EOF
#!/bin/bash
curl -sL "https://raw.githubusercontent.com/pebdev/lortnoc/main/tools/installers/install_client.sh" | bash -s -- "$INSTALL_DIR"
EOF
chmod +x "$INSTALL_DIR/update.sh"

# Restart Service if exists
if systemctl list-units --full -all | grep -Fq "lortnoc-client.service"; then
  echo -e "${YELLOW}[*] Restarting lortnoc-client service...${NC}"
  sudo systemctl restart "lortnoc-client.service"
fi

echo -e "${GREEN}[✓] Installation/Update Complete ($LATEST_VERSION).${NC}"
