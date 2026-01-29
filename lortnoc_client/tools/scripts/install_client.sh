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

# Configurations
REPO_URL="https://api.github.com/repos/pebdev/lortnoc/releases/latest"
SERVICE_NAME="lortnoc-client"
CONFIG_FILE="config.json"
TEMPLATE_FILE="config_template.json"

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
mkdir -p "$1"
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

# Backup config if exists
if [ -f "$INSTALL_DIR/config/$CONFIG_FILE" ]; then
  cp "$INSTALL_DIR/config/$CONFIG_FILE" "$TEMP_DIR/$CONFIG_FILE.bak"
fi

# Copy necessary folders (Core + Client)
mkdir -p "$INSTALL_DIR/lortnoc_core"
mkdir -p "$INSTALL_DIR/lortnoc_client"
mkdir -p "$INSTALL_DIR/config"

cp -R "$TEMP_DIR/lortnoc_core/"* "$INSTALL_DIR/lortnoc_core/"
cp -R "$TEMP_DIR/lortnoc_client/"* "$INSTALL_DIR/lortnoc_client/"

# Copy template config only
if [ -f "$TEMP_DIR/config/$TEMPLATE_FILE" ]; then
  cp "$TEMP_DIR/config/$TEMPLATE_FILE" "$INSTALL_DIR/config/"
fi

# Restore config if backed up
if [ -f "$TEMP_DIR/$CONFIG_FILE.bak" ]; then
  mv "$TEMP_DIR/$CONFIG_FILE.bak" "$INSTALL_DIR/config/$CONFIG_FILE"
fi

# First configuration
if [ ! -f "$INSTALL_DIR/config/$CONFIG_FILE" ]; then
  read -p "Enter Client Name          : " CLIENT_NAME
  read -p "Enter Discord Bot Token    : " TOKEN
  read -p "Enter Heartbeat Channel ID : " CHANNEL_ID

  python3 -c "
import json
with open('$INSTALL_DIR/config/$TEMPLATE_FILE', 'r') as f:
  config = json.load(f)

config['client_name'] = '$CLIENT_NAME'
config['discord']['token'] = '$TOKEN'
config['discord']['heartbeat_channel_id'] = '$CHANNEL_ID'

with open('$INSTALL_DIR/config/$CONFIG_FILE', 'w') as f:
  json.dump(config, f, indent=2)
"
  echo "[+] Configuration saved to $CONFIG_FILE."
else
  echo "[+] Configuration file exists at $CONFIG_FILE."
fi


# --- Virtual Environment Setup -------------------------------------------------
echo -e "${YELLOW}[*] Setting up Python Environment...${NC}"
if [ ! -d "$INSTALL_DIR/.venv" ]; then
  python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/lortnoc_client/requirements.txt" --upgrade


# --- Finalize -----------------------------------------------------------------
echo "$LATEST_VERSION" > "$INSTALL_DIR/VERSION"
rm -rf "$TEMP_DIR"

# Ensure run.sh is executable
chmod +x "$INSTALL_DIR/lortnoc_client/tools/scripts/run.sh"

# Restart Service if exists
if systemctl list-units --full -all | grep -Fq "lortnoc-client.service"; then
  echo -e "${YELLOW}[*] Restarting lortnoc-client service...${NC}"
  sudo systemctl restart "lortnoc-client.service"
fi

echo -e "${GREEN}[✓] Installation/Update Complete ($LATEST_VERSION).${NC}"
