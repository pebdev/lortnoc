#!/bin/bash
########################################################################################################################
# Project : Lortnoc
# Author  : PEB <pebdev@lavache.com>
# Date    : 29.01.2026
########################################################################################################################
# Copyright (C) 2026
# This file is copyright under the latest version of the EUPL.
# Please see LICENSE file for your rights under this license.
########################################################################################################################
set -e

REPO_URL="https://api.github.com/repos/pebdev/lortnoc/releases/latest"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'


# --- Usage ------------------------------------------------------------------------------------------------------------
COMPONENT="$1"
TARGET_DIR="$2"

if [[ -z "$COMPONENT" || ("$COMPONENT" != "client" && "$COMPONENT" != "monitor") ]]; then
  echo -e "${RED}Usage: $0 <client|monitor> [install_directory]${NC}"
  exit 1
fi

# Ensure absolute path
TARGET_DIR="${HOME}/lortnoc_$COMPONENT"
mkdir -p "$TARGET_DIR"
INSTALL_DIR=$(cd "$TARGET_DIR" && pwd)

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}   LORTNOC INSTALLER ($COMPONENT)        ${NC}"
echo -e "${BLUE}=========================================${NC}"
echo -e "${YELLOW}[*] Target Directory : $INSTALL_DIR${NC}"


# --- Environment Check ------------------------------------------------------------------------------------------------
REQUIRED="curl tar python3"
[ "$COMPONENT" == "monitor" ] && [ ! -f /.dockerenv ] && REQUIRED="$REQUIRED docker"

for cmd in $REQUIRED; do
  if ! command -v $cmd &> /dev/null; then
    echo -e "${RED}Error: $cmd is required.${NC}"
    exit 1
  fi
done


# --- Get Latest Release ------------------------------------------------------------------------------------------------
echo -e "${YELLOW}[*] Checking for updates...${NC}"
LATEST_RELEASE=$(curl -s $REPO_URL)
LATEST_VERSION=$(echo "$LATEST_RELEASE" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
TARBALL_URL=$(echo "$LATEST_RELEASE" | grep '"tarball_url":' | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z "$LATEST_VERSION" ]; then
  echo -e "${RED}Error: Version fetch failed.${NC}"
  exit 1
fi

# Check Local Version
LOCAL_VERSION="none"
[ -f "$INSTALL_DIR/VERSION" ] && LOCAL_VERSION=$(cat "$INSTALL_DIR/VERSION")
[ -f "$INSTALL_DIR/version.txt" ] && LOCAL_VERSION=$(cat "$INSTALL_DIR/version.txt")

echo -e "    Local  : $LOCAL_VERSION"
echo -e "    Latest : $LATEST_VERSION"

if [ "$LOCAL_VERSION" == "$LATEST_VERSION" ]; then
  echo -e "${GREEN}[✓] Up to date.${NC}"
  exit 0
fi


# --- Download & Install ------------------------------------------------------------------------------------------------
echo -e "${YELLOW}[*] Downloading update...${NC}"
TEMP_DIR=$(mktemp -d)
curl -sL "$TARBALL_URL" | tar -xz -C "$TEMP_DIR" --strip-components=1

echo -e "${YELLOW}[*] Installing files...${NC}"

# Common dirs
mkdir -p "$INSTALL_DIR/lortnoc_core"
mkdir -p "$INSTALL_DIR/config"
mkdir -p "$INSTALL_DIR/resources"
mkdir -p "$INSTALL_DIR/tools/scripts"

# Copy Core & Resources
cp -R "$TEMP_DIR/lortnoc_core/"* "$INSTALL_DIR/lortnoc_core/"
cp -R "$TEMP_DIR/resources/"* "$INSTALL_DIR/resources/"
cp -R "$TEMP_DIR/tools/scripts/"* "$INSTALL_DIR/tools/scripts/"

# Component specific copy
if [ "$COMPONENT" == "monitor" ]; then
  mkdir -p "$INSTALL_DIR/lortnoc_monitor"
  cp -R "$TEMP_DIR/lortnoc_monitor/"* "$INSTALL_DIR/lortnoc_monitor/"

  # Docker Specifics (Host only)
  if [ ! -f /.dockerenv ]; then
    DOCKER_DST="$INSTALL_DIR/tools/docker"
    mkdir -p "$DOCKER_DST"
    # We need Dockerfile and manage.sh which might be in lortnoc_monitor/tools/docker in the repo
    # OR in tools/docker if we moved them?
    # Based on current repo state: lortnoc_monitor/tools/docker
    if [ -d "$TEMP_DIR/lortnoc_monitor/tools/docker" ]; then
      cp -R "$TEMP_DIR/lortnoc_monitor/tools/docker/"* "$DOCKER_DST/"
    fi
  fi

else # client
  mkdir -p "$INSTALL_DIR/lortnoc_client"
  cp -R "$TEMP_DIR/lortnoc_client/"* "$INSTALL_DIR/lortnoc_client/"
fi


# --- Config Management ------------------------------------------------------------------------------------------------
CONFIG_FILE="config.json"
TEMPLATE_FILE="config_template.json"

# Move Config Template
if [ -f "$TEMP_DIR/config/$TEMPLATE_FILE" ]; then
  cp "$TEMP_DIR/config/$TEMPLATE_FILE" "$INSTALL_DIR/config/"
fi

# Interactive Config (Only if new)
if [ ! -f "$INSTALL_DIR/config/$CONFIG_FILE" ]; then
  echo -e "${YELLOW}[*] Initial Configuration Required${NC}"

  python3 -c "
import json, os
template = '$INSTALL_DIR/config/$TEMPLATE_FILE'
target = '$INSTALL_DIR/config/$CONFIG_FILE'

if os.path.exists(template):
  with open(template, 'r') as f: config = json.load(f)

  if '$COMPONENT' == 'monitor':
    config['discord']['token'] = input('Discord Token: ')
    config['discord']['heartbeat_channel_id'] = input('Channel ID: ')
    config['admin_password'] = input('Admin Password: ')
  else:
    config['client_name'] = input('Client Name: ')
    config['discord']['token'] = input('Discord Token: ')
    config['discord']['heartbeat_channel_id'] = input('Channel ID: ')

  with open(target, 'w') as f: json.dump(config, f, indent=2)
  print('[+] Config saved.')
"
fi


# --- Post Install ------------------------------------------------------------------------------------------------

if [ "$COMPONENT" == "monitor" ]; then
  # Docker Rebuild (Host only)
  if [ ! -f /.dockerenv ] && command -v docker &> /dev/null; then
    echo -e "${YELLOW}[*] Rebuilding Docker Container...${NC}"
    cd "$INSTALL_DIR"
    # Assuming Dockerfile is now in tools/docker/Dockerfile relative to install dir
    if [ -f "tools/docker/Dockerfile" ]; then
      docker build -t lortnoc-monitor -f tools/docker/Dockerfile .
      $INSTALL_DIR/tools/docker/manage.sh run
    fi
  fi
else
  # Client Venv
  echo -e "${YELLOW}[*] Updating Python Environment...${NC}"
  [ ! -d "$INSTALL_DIR/.venv" ] && python3 -m venv "$INSTALL_DIR/.venv"
  "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/lortnoc_client/requirements.txt" --upgrade
fi

# Save Version
echo "$LATEST_VERSION" > "$INSTALL_DIR/VERSION"
rm -rf "$TEMP_DIR"
chmod +x "$INSTALL_DIR/tools/scripts/"*.sh

echo -e "${GREEN}[✓] $COMPONENT updated to $LATEST_VERSION.${NC}"
