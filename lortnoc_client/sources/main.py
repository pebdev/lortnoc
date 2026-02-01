# -*- coding: utf-8 -*-
########################################################################################################################
# Project : Lortnoc
# Author  : PEB <pebdev@lavache.com>
# Date    : 24.01.2026
########################################################################################################################
# Copyright (C) 2026
# This file is copyright under the latest version of the EUPL.
# Please see LICENSE file for your rights under this license.
########################################################################################################################

# I M P O R T ##########################################################################################################
import sys
import os
import asyncio
import logging
import platform
import socket
import subprocess
import time
import psutil
import discord

# Adjust sys.path to include lortnoc_core
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
  sys.path.append(parent_dir)

try:
  from lortnoc_core.transport_discord import DiscordTransport
  from lortnoc_core.logger import setup_logging
  from lortnoc_core.config import load_config
except ImportError as e:
  logging.critical(f"Error: lortnoc_core module not found or import error: {e}")
  sys.exit(1)


# C L A S S ############################################################################################################
class LortnocClient:
  """
  Lortnoc Agent running on the target machine.
  Handles monitoring stats and executing remote commands.
  """

  # ----------------------------------------------------------------------------------------------------------------------
  def __init__ (self) -> None:
    # 1. Load Config & Logging
    self.config = load_config()
    setup_logging(self.config.get("log_file", "/tmp/lortnoc.log"))
    self.logger = logging.getLogger("lortnoc-client")

    # 2. Paths
    self.data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.data'))
    if not os.path.exists(self.data_dir):
      os.makedirs(self.data_dir)

    # 3. Configuration Validation
    # ---------------------------
    # Client ID
    self.client_id = self.config.get("client_id")
    if not self.client_id:
      self.logger.critical("'client_id' is missing in config.json.")
      self.logger.critical("Please reinstall or manually add a unique ID.")
      sys.exit(1)

    # Discord Token
    token = self.config.get("discord", {}).get("token")
    if not token:
      self.logger.critical("Discord Token is missing in config.json.")
      sys.exit(1)

    # Heartbeat Channel
    hb_id = self.config.get("discord", {}).get("heartbeat_channel_id")
    if not hb_id:
      self.logger.critical("Heartbeat Channel ID is missing in config.json.")
      sys.exit(1)

    try:
      self.heartbeat_channel_id = int(hb_id)
    except ValueError:
      self.logger.critical(f"Invalid Heartbeat Channel ID: '{hb_id}'. Must be a number.")
      sys.exit(1)

    # Encryption Key
    encryption_key = self.config.get("discord", {}).get("encryption_key")
    if not encryption_key:
      self.logger.critical("Encryption Key missing in config.")
      self.logger.critical("Please copy the 'encryption_key' from the Monitor's config.json.")
      sys.exit(1)

    # 4. Initialization
    # -----------------
    self.client_name = self.config.get("client_name", "Unknown-Device")
    self.logger.info(f"Identity: {self.client_name} ({self.client_id})")

    self.os_info = f"{platform.system()} {platform.release()}"
    self.cmd_channel_id = None

    # Transport
    # Initial listen list is empty (will dynamic add own channel) or legacy
    legacy_id = self.config.get("discord", {}).get("channel_id")
    channels_to_listen = [int(legacy_id)] if legacy_id else []

    self.transport = DiscordTransport(token, channels_to_listen, _encryption_key=encryption_key)
    self.transport.set_callback(self.handle_message)

    # Version Resolution
    self.version = "unknown"
    try:
      # VERSION file is expected at ../../VERSION relative to this file
      version_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../VERSION'))
      if os.path.exists(version_file):
        with open(version_file, 'r', encoding='utf-8') as f:
          self.version = f.read().strip()
    except Exception:
      pass

    self.logger.info(f"Initialized Lortnoc Client ({self.client_id}) v{self.version}")


  # L I F E C Y C L E --------------------------------------------------------------------------------------------------
  async def run (self) -> None:
    """Main entry point."""
    try:
      # 1. Connect Transport
      await self.transport.connect()

      # 2. Setup Channel (Dynamic V2 logic)
      await self._wait_for_connection()
      await self._setup_command_channel()

      # 3. Start Heartbeat Loop
      await self._run_stats_loop()

    except Exception as e:
      self.logger.critical(f"Critical error in main loop: {e}")
    finally:
      await self.transport.disconnect()

  # --------------------------------------------------------------------------------------------------------------------
  async def _wait_for_connection (self) -> None:
    """Waits until transport is fully connected."""
    self.logger.info("Waiting for transport connection...")
    while True:
      if isinstance(self.transport, DiscordTransport) and self.transport._connected:
        break
      await asyncio.sleep(1)


  # C H A N N E L   M G M T --------------------------------------------------------------------------------------------
  async def _setup_command_channel (self) -> None:
    """Resolves or creates the dedicated command channel for this client."""
    if not isinstance(self.transport, DiscordTransport):
      return

    try:
      guilds = self.transport.client.guilds
      if not guilds:
        self.logger.warning("Bot is not in any guild! Cannot create command channel.")
        return

      guild = guilds[0] # Assume first guild
      target_name = self.client_id.lower().replace('.', '-')

      # Check existence
      channel = discord.utils.get(guild.text_channels, name=target_name)
      if not channel:
        self.logger.info(f"Creating new command channel: {target_name}")
        channel = await guild.create_text_channel(target_name)

      self.cmd_channel_id = channel.id
      self.transport.add_listening_channel(self.cmd_channel_id)
      self.logger.info(f"Command Channel Ready: {target_name} ({self.cmd_channel_id})")

    except Exception as e:
      self.logger.error(f"Failed to setup command channel: {e}")


  # H E A R T B E A T --------------------------------------------------------------------------------------------------
  async def _run_stats_loop (self) -> None:
    interval = self.config.get("heartbeat_interval", 300)
    self.logger.info(f"Starting stats loop (interval={interval}s)")

    while True:
      try:
        await self.send_heartbeat()
      except Exception as e:
        self.logger.error(f"Heartbeat loop error: {e}")

      await asyncio.sleep(interval)

  # --------------------------------------------------------------------------------------------------------------------
  async def send_heartbeat (self) -> None:
    """Sends a single heartbeat payload."""
    try:
      stats = await self._get_system_stats()
      payload = {
        "type": "heartbeat",
        "client_id": self.client_id,
        "client_name": self.client_id,
        "timestamp": time.time(),
        "_target_channel_id": self.heartbeat_channel_id or None,
        "payload": {
          "status": "online",
          "version": self.version,
          "os": self.os_info,
          "command_channel_id": self.cmd_channel_id,
          **stats
        }
      }
      await self.transport.send(payload)

    except Exception as e:
      self.logger.error(f"Failed to send heartbeat: {e}")


  # C O M M A N D S ----------------------------------------------------------------------------------------------------
  async def handle_message (self, _msg: dict) -> None:
    """Handles incoming messages from the transport."""
    # Only process commands targeting us
    if _msg.get('type') != 'command' or _msg.get('target_id') != self.client_id:
      return

    result    = "Done"
    is_error  = False
    action    = _msg.get('action')
    args      = _msg.get('args', [])
    self.logger.info(f"Received command: {action} {args}")

    try:
      if action == 'reboot':
        result = "Executing system reboot..."
        asyncio.create_task(self._delayed_exec('sudo reboot', 2))
      elif action == 'shutdown':
        result = "Executing system shutdown..."
        asyncio.create_task(self._delayed_exec('sudo shutdown -h now', 2))
      elif action == 'exec':
        result, is_error = await self._exec_shell(args[0] if args else "")
      elif action == 'update':
        # Trigger Self-Update via the installer script
        current_file  = os.path.abspath(__file__)
        client_dir    = os.path.dirname(os.path.dirname(current_file)) # .../lortnoc_client
        install_root  = os.path.dirname(client_dir) # The directory containing lortnoc_client
        installer_url = "https://raw.githubusercontent.com/pebdev/lortnoc/master/tools/scripts/installer.sh"
        # Usage: installer.sh <component> <target_dir> <mode>
        cmd     = f"curl -sL {installer_url} | bash -s -- client {install_root} --update-runtime"
        result  = "Update initiated via Installer. Service will restart..."
        asyncio.create_task(self._delayed_exec(cmd, 1))

      elif action == 'ping':
        # Immediate Heartbeat
        await self.send_heartbeat()
        result = "Pong (Heartbeat sent)"

      else:
        result = f"Unknown action: {action}"
        is_error = True

    except Exception as e:
      result = str(e)
      is_error = True

    # Send Feedback Log
    origin_channel = _msg.get('_origin_channel_id')
    await self.transport.send({
      "type": "log",
      "client_id": self.client_id,
      "timestamp": time.time(),
      "level": "ERROR" if is_error else "INFO",
      "message": f"CMD '{action}': {result}",
      "_target_channel_id": origin_channel
    })


  # H E L P E R S ------------------------------------------------------------------------------------------------------
  async def _exec_shell (self, cmd: str) -> (str, bool):
    """Executes a shell command and returns output and error status."""
    if not cmd:
      return "No command provided", True

    try:
      proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
      )
      stdout, stderr = await proc.communicate()
      output = stdout.decode().strip()
      if stderr:
        output += "\nSTDERR: " + stderr.decode().strip()
      return output, bool(stderr)
    except Exception as e:
      return str(e), True

  # --------------------------------------------------------------------------------------------------------------------
  async def _delayed_exec (self, command: str, delay: int) -> None:
    """Executes a shell command after a delay."""
    await asyncio.sleep(delay)
    await self._exec_shell(command)

  # --------------------------------------------------------------------------------------------------------------------
  async def _get_system_stats (self) -> dict:
    """Gathers system statistics."""

    cpu   = psutil.cpu_percent(interval=None)
    ram   = psutil.virtual_memory().percent
    disk  = psutil.disk_usage('/').percent
    net   = psutil.net_io_counters()

    return {
      "cpu": cpu,
      "ram": ram,
      "disk": disk,
      "net_sent": net.bytes_sent,
      "net_recv": net.bytes_recv,
      "temp": self._get_cpu_temp(),
      "ip": self._get_ip_address()
    }

  # --------------------------------------------------------------------------------------------------------------------
  def _get_cpu_temp (self) -> float:
    """Try to get CPU temperature via various methods."""
    if platform.system() != "Linux":
      return 0.0

    try:
      # 1. Try psutil sensors
      if hasattr(psutil, "sensors_temperatures"):
        temps = psutil.sensors_temperatures()
        if temps:
          for _, entries in temps.items():
            if entries:
              return entries[0].current

      # 2. Try vcgencmd (Raspberry Pi)
      res = subprocess.check_output(["vcgencmd", "measure_temp"]).decode()
      # Format: temp=45.6'C
      return float(res.replace("temp=", "").replace("'C\n", ""))
    except Exception:
      pass

    return 0.0

  # --------------------------------------------------------------------------------------------------------------------
  def _get_ip_address (self) -> str:
    try:
      s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      s.connect(("1.1.1.1", 80))
      ip = s.getsockname()[0]
      s.close()
      return ip
    except Exception:
      return "127.0.0.1"


# M A I N ##############################################################################################################
if __name__ == "__main__":
  client = LortnocClient()
  try:
    asyncio.run(client.run())
  except KeyboardInterrupt:
    print("\n[!] Client stopped by user.")
    sys.exit(0)
