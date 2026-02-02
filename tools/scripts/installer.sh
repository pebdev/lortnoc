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

# --- Configurations ---------------------------------------------------------------------------------------------------
# Fetch latest release tag from GitHub API
LATEST_VERSION=$(curl -s "https://api.github.com/repos/pebdev/lortnoc/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
TARBALL_URL="https://github.com/pebdev/lortnoc/archive/refs/tags/$LATEST_VERSION.tar.gz"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'


# --- Usage ------------------------------------------------------------------------------------------------------------
COMPONENT="$1"
TARGET_DIR="$2"
MODE="$3"
SERVICE_OPT="$4"

# Handle arguments shift if MODE is omitted or is a service flag
if [[ "$MODE" == "--no-service" || "$MODE" == "--with-service" ]]; then
  SERVICE_OPT="$MODE"
  MODE="--install"
fi

if [[ -z "$COMPONENT" || ("$COMPONENT" != "client" && "$COMPONENT" != "monitor") ]]; then
  echo -e "${RED}Usage: $0 <client|monitor> <install_directory> [mode] [service-option]${NC}"
  echo -e "${RED}Modes: --install (default), --update-runtime${NC}"
  echo -e "${RED}Service Options: --with-service, --no-service${NC}"
  exit 1
fi

if [[ -z "$TARGET_DIR" ]]; then
  echo -e "${RED}Error: Install directory argument is required.${NC}"
  exit 1
fi

if [ -z "$LATEST_VERSION" ] || [ "$LATEST_VERSION" == "null" ]; then
  echo -e "${RED}Error: Unable to fetch latest release version from GitHub.${NC}"
  exit 1
fi

[ -z "$MODE" ] && MODE="--install"

# Ensure absolute path
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


# --- Get Latest Release -----------------------------------------------------------------------------------------------
echo -e "${YELLOW}[*] Checking for updates...${NC}"

if [ -z "$LATEST_VERSION" ]; then
  echo -e "${RED}Error: Version fetch failed.${NC}"
  exit 1
fi

# Check Local Version
LOCAL_VERSION="none"
[ -f "$INSTALL_DIR/VERSION" ] && LOCAL_VERSION=$(cat "$INSTALL_DIR/VERSION")
[ -f "$INSTALL_DIR/VERSION" ] && LOCAL_VERSION=$(cat "$INSTALL_DIR/VERSION")

echo -e "    Local  : $LOCAL_VERSION"
echo -e "    Latest : $LATEST_VERSION"

if [ "$LOCAL_VERSION" == "$LATEST_VERSION" ]; then
  echo -e "${GREEN}[✓] Up to date.${NC}"
  exit 0
fi


# --- Download & Install -----------------------------------------------------------------------------------------------
echo -e "${YELLOW}[*] Downloading update...${NC}"
TEMP_DIR=$(mktemp -d)
curl -sL "$TARBALL_URL" | tar -xz -C "$TEMP_DIR" --strip-components=1

echo -e "${YELLOW}[*] Installing files...${NC}"
mkdir -p "$INSTALL_DIR/lortnoc_core"
mkdir -p "$INSTALL_DIR/config"
mkdir -p "$INSTALL_DIR/resources"
mkdir -p "$INSTALL_DIR/tools/scripts"

# Copy Core & Resources
cp -R "$TEMP_DIR/lortnoc_core/"* "$INSTALL_DIR/lortnoc_core/"
cp -R "$TEMP_DIR/resources/"* "$INSTALL_DIR/resources/"
[ -d "$TEMP_DIR/tools/scripts/" ] && cp -R "$TEMP_DIR/tools/scripts/"* "$INSTALL_DIR/tools/scripts/"

# Component specific copy
if [ "$COMPONENT" == "monitor" ]; then
  mkdir -p "$INSTALL_DIR/lortnoc_monitor"
  cp -R "$TEMP_DIR/lortnoc_monitor/"* "$INSTALL_DIR/lortnoc_monitor/"

  # Docker Specifics (Host only)
  if [ ! -f /.dockerenv ]; then
    DOCKER_DST="$INSTALL_DIR/tools/docker"
    mkdir -p "$DOCKER_DST"

    # We copy docker tools from module to global tools/docker
    if [ -d "$TEMP_DIR/lortnoc_monitor/tools/docker" ]; then
      cp -R "$TEMP_DIR/lortnoc_monitor/tools/docker/"* "$DOCKER_DST/"
    fi
  fi

else # client
  mkdir -p "$INSTALL_DIR/lortnoc_client"
  cp -R "$TEMP_DIR/lortnoc_client/"* "$INSTALL_DIR/lortnoc_client/"
fi


# --- Config Management -----------------------------------------------------------------------------------------------
CONFIG_FILE="config.json"
TEMPLATE_FILE="config_template.json"

# Move Config Template
if [ -f "$TEMP_DIR/config/$TEMPLATE_FILE" ]; then
  cp "$TEMP_DIR/config/$TEMPLATE_FILE" "$INSTALL_DIR/config/"
fi

# Interactive Config (Only if new)
CONFIG_STATUS="ok"
if [ ! -f "$INSTALL_DIR/config/$CONFIG_FILE" ]; then
  # Always ensure connection file exists to prevent startup crash
  echo -e "${YELLOW}[*] Creating default configuration from template...${NC}"
  if [ -f "$INSTALL_DIR/config/$TEMPLATE_FILE" ]; then
    cp "$INSTALL_DIR/config/$TEMPLATE_FILE" "$INSTALL_DIR/config/$CONFIG_FILE"
  else
    echo -e "${RED}[!] Template file missing. Configuration initialization failed.${NC}"
  fi

if [ -c /dev/tty ]; then
    echo -e "${YELLOW}[*] Starting Interactive Configuration...${NC}"

    python3 -c "
import json, os, sys, base64, getpass

target = '$INSTALL_DIR/config/$CONFIG_FILE'

def prompt(label, hidden=False):
  try:
    if hidden:
      val = getpass.getpass(f'{label}: ')
    else:
      val = input(f'{label}: ')
    return val.strip()
  except EOFError:
    return ''

if os.path.exists(target):
  with open(target, 'r') as f: config = json.load(f)

  # --- Prompting for Core Details ---
  if '$COMPONENT' == 'monitor':
    p = prompt('Lortnoc Admin Password', hidden=True)
    if p: config['admin_password'] = p

    t = prompt('Discord Token', hidden=True)
    if t: config['discord']['token'] = t

    c = prompt('Discord heartbeat Channel ID (Heartbeat)', hidden=True)
    if c: config['discord']['heartbeat_channel_id'] = c

    # --- TOTP Generation ---
    if 'totp_secret' not in config or not config['totp_secret']:
      import base64, os
      # Generate 32-char Base32 secret for TOTP (Google Authenticator compatible)
      # 20 bytes entropy -> base32 encoded -> string
      secret = base64.b32encode(os.urandom(20)).decode('utf-8')
      config['totp_secret'] = secret
      print('')
      print(f'[+] Lortnoc TOTP Secret Generated: {secret}')
      print('    !! ADD THIS KEY TO YOUR AUTHENTICATOR APP !!')

  else:
    n = prompt('Lortnoc client name')
    if n: config['client_name'] = n

    t = prompt('Discord Token', hidden=True)
    if t: config['discord']['token'] = t

    c = prompt('Discord heartbeat Channel ID (Heartbeat)', hidden=True)
    if c: config['discord']['heartbeat_channel_id'] = c

  # --- Key Generation / Check ---
  current_key = config.get('discord', {}).get('encryption_key', '')

  if current_key and len(current_key) > 5:
    print(f'[i] Encryption Key detected: {current_key[:5]}...*****')
  else:
    if 'discord' not in config: config['discord'] = {}

    if '$COMPONENT' == 'monitor':
      print('[*] Generating New Encryption Key...')
      key = base64.urlsafe_b64encode(os.urandom(32)).decode()
      config['discord']['encryption_key'] = key
      print(f'[+] New Key Generated: {key}')
      print('    !! COPY THIS KEY TO ALL CLIENTS !!')
    else:
      # For Client, we must ask for the key
      print('')
      print('[*] Security Setup (Encryption)')
      new_key = prompt('Encryption Key (Copy from Monitor)', hidden=True)
      if new_key:
        config['discord']['encryption_key'] = new_key
      else:
        print('[!] Warning: No encryption key provided. Client will not be able to communicate.')

  with open(target, 'w') as f: json.dump(config, f, indent=2)
  print('[+] Config updated.')
" < /dev/tty
    if [ $? -ne 0 ]; then
      CONFIG_STATUS="manual"
    fi
  else
    echo -e "${YELLOW}[!] Non-interactive mode detected using default config.${NC}"
    CONFIG_STATUS="manual"
  fi
fi

# Client ID Generation (Client Only)
if [ "$COMPONENT" == "client" ]; then
  CONF_PATH="$INSTALL_DIR/config/$CONFIG_FILE"
  if [ -f "$CONF_PATH" ]; then
    # Check if client_id is set or empty
    CURRENT_ID=$(grep '"client_id"' "$CONF_PATH" | head -1 | cut -d':' -f2 | tr -d '", ')

    if [ -z "$CURRENT_ID" ]; then
      echo -e "${YELLOW}[*] Generating unique system Client ID...${NC}"
      # Generates a random ID (Timestamp + Random)
      NEW_ID="$(date +%s)-$RANDOM"

      # Use temp file for sed to handle both Linux and macOS
      sed "s/\"client_id\"[[:space:]]*:[[:space:]]*\"\"/\"client_id\" : \"$NEW_ID\"/" "$CONF_PATH" > "$CONF_PATH.tmp" && mv "$CONF_PATH.tmp" "$CONF_PATH"
      echo -e "    Assigned ID: $NEW_ID"
    fi
  fi
fi

# Secure the config file
if [ -f "$INSTALL_DIR/config/$CONFIG_FILE" ]; then
  chmod 600 "$INSTALL_DIR/config/$CONFIG_FILE"
  echo -e "${GREEN}[*] Config file permissions secured.${NC}"
fi

# Save Version immediately after install so it's available for Docker build
echo "$LATEST_VERSION" > "$INSTALL_DIR/VERSION"

# --- Post Install -----------------------------------------------------------------------------------------------------
if [ "$MODE" == "--install" ] && [ "$COMPONENT" == "monitor" ]; then
  # Monitor Installation on Host -> Docker Build
  echo -e "${YELLOW}[*] Rebuilding Docker Container...${NC}"
  cd "$INSTALL_DIR"

  # Ensure Docker tools executable
  chmod +x tools/docker/*.sh 2>/dev/null || true

  # Rebuild
  if [ -f "tools/docker/Dockerfile" ]; then
    if command -v docker &> /dev/null; then
      docker build -t lortnoc-monitor -f tools/docker/Dockerfile .
      echo -e "${GREEN}[*] Docker Image Rebuilt.${NC}"
      echo -e "${GREEN}[*] You can now start the monitor using: ${INSTALL_DIR}/tools/docker/manage.sh run${NC}"
    else
      echo -e "${RED}[!] Docker not found. Cannot build image.${NC}"
    fi
  else
    echo -e "${RED}[!] Dockerfile not found.${NC}"
  fi

else
  # Runtime Update (Client OR Monitor inside Container OR Monitor Update-Only)
  # We enforce a virtualenv in all cases to ensure consistency and isolation
  echo -e "${YELLOW}[*] Updating Python Environment...${NC}"
  [ ! -d "$INSTALL_DIR/.venv" ] && python3 -m venv "$INSTALL_DIR/.venv"

  REQ_FILE="$INSTALL_DIR/lortnoc_$COMPONENT/requirements.txt"
  if [ -f "$REQ_FILE" ]; then
    "$INSTALL_DIR/.venv/bin/pip" install -r "$REQ_FILE" --upgrade
  fi
fi

# --- Systemd Service Proposal (Client Only) ---------------------------------------------------------------------------
if [ "$MODE" == "--install" ] && [ "$COMPONENT" == "client" ]; then
  response="n"

  if [ "$SERVICE_OPT" == "--with-service" ]; then
    response="y"
  elif [ "$SERVICE_OPT" == "--no-service" ]; then
    response="n"
  elif [ -c /dev/tty ]; then
    echo -e ""
    echo -e "${YELLOW}[?] Do you want to create a Systemd Service for auto-start? [y/N] ${NC}"
    read -r -n 1 response < /dev/tty
    echo ""
  fi

  if [[ "$response" =~ ^[yY]$ ]]; then
    SERVICE_NAME="lortnoc-client"
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    USER_NAME=$(whoami)

    # Check for root/sudo
    if [ "$EUID" -ne 0 ] && ! command -v sudo &> /dev/null; then
      echo -e "${RED}[!] Sudo is required to create systemd service. Skipping.${NC}"
    else
      SUDO=""
      [ "$EUID" -ne 0 ] && SUDO="sudo"

      echo -e "${YELLOW}[*] Creating ${SERVICE_FILE}...${NC}"

      # Generate Service Content using a temporary file
      TMP_SERVICE=$(mktemp)
      cat <<EOF > "$TMP_SERVICE"
[Unit]
Description=Lortnoc Client Service
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/tools/scripts/run.sh client
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

      # Move with sudo
      $SUDO mv "$TMP_SERVICE" "$SERVICE_FILE"
      $SUDO chmod 644 "$SERVICE_FILE"
      $SUDO systemctl daemon-reload
      $SUDO systemctl enable "$SERVICE_NAME"
      echo -e "${GREEN}[✓] Service created and enabled. It will start on boot.${NC}"
      echo -e "${GREEN}[*] You can start it now with: sudo systemctl start $SERVICE_NAME${NC}"
    fi
  fi
fi

rm -rf "$TEMP_DIR"
chmod +x "$INSTALL_DIR/tools/scripts/"*.sh
echo -e "${GREEN}[✓] $COMPONENT installed/updated to $LATEST_VERSION.${NC}"

echo -e ""
echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}   INSTALLATION SUMMARY                  ${NC}"
echo -e "${BLUE}=========================================${NC}"

if [ "$COMPONENT" == "monitor" ]; then
  echo -e "  Type       : Monitor (Server)"
  echo -e "  Location   : $INSTALL_DIR"
  echo -e "  Config     : $INSTALL_DIR/config/config.json"

  if [ "$CONFIG_STATUS" == "manual" ]; then
    echo -e "${RED}  [!] CONFIGURATION REQUIRED${NC}"
    echo -e "${RED}      You must edit config/config.json before starting.${NC}"
  fi

  echo -e ""
  echo -e "${YELLOW}  [i] TO START THE MONITOR:${NC}"
  echo -e "      $INSTALL_DIR/tools/docker/manage.sh run"
  echo -e ""
  echo -e "  Then access: http://<YOUR_SERVER_IP>:8080"
else
  echo -e "  Type       : Client (Device)"
  echo -e "  Location   : $INSTALL_DIR"
  echo -e "  Config     : $INSTALL_DIR/config/config.json"

  if [ "$CONFIG_STATUS" == "manual" ]; then
    echo -e "${RED}  [!] CONFIGURATION REQUIRED${NC}"
    echo -e "${RED}      You must edit config/config.json before starting.${NC}"
  fi

  echo -e ""
  echo -e "${YELLOW}  [i] TO START THE CLIENT:${NC}"
  echo -e "      $INSTALL_DIR/tools/scripts/run.sh client &"
  echo -e ""

  # Check if systemd setup occurred
  if [ -f "/etc/systemd/system/lortnoc-client.service" ]; then
    echo -e "${YELLOW}  [i] SYSTEMD SERVICE INSTALLED${NC}"
    echo -e "      sudo systemctl status lortnoc-client"
  else
    echo -e "${YELLOW}  [i] TO START ON BOOT (Systemd):${NC}"
    echo -e "      Create a service file pointing to the run script above."
  fi
fi
echo -e "${BLUE}=========================================${NC}"
