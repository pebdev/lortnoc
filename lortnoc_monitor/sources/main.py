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
import logging
import sys
import os
import secrets
from datetime import datetime
import asyncio
from typing import List, Dict, Optional
from contextlib import asynccontextmanager
import uvicorn

from nicegui import ui
from fastapi import FastAPI

# Import Transport & Core
try:
  from lortnoc_core.transport_discord import DiscordTransport
  from lortnoc_core.logger import setup_logging
  from lortnoc_core.config import load_config
except ImportError as e:
  # Fallback for dev if core is not installed but in adjacent folder
  sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
  from lortnoc_core.transport_discord import DiscordTransport
  from lortnoc_core.logger import setup_logging
  from lortnoc_core.config import load_config

# Refactored Modules
from modules.auth import AuthMiddleware
from modules.client_manager import ClientManager
from ui.manager import UIManager


# C L A S S ############################################################################################################
class LortnocMonitor:
  """
  Main class for the Lortnoc Monitor application.
  Handles initialization, configuration, and main event loop.
  """

  # --------------------------------------------------------------------------------------------------------------------
  def __init__ (self):
    # 1. Config Loading & Validation
    # ------------------------------
    self.config = load_config()

    # 2. Logging Setup
    # ----------------
    setup_logging(self.config.get("log_file"))
    self.logger = logging.getLogger("LortnocMonitor")

    discord_cfg = self.config.get("discord", {})

    self.discord_token      = discord_cfg.get("token")
    self.discord_channel_id = discord_cfg.get("heartbeat_channel_id")
    self.encryption_key     = discord_cfg.get("encryption_key")
    self.admin_password     = self.config.get("admin_password")

    # TOTP Setup
    self.totp_secret = self.config.get("totp_secret")
    if not self.totp_secret:
      self.logger.warning("No TOTP Secret found in config.json. Please run installer to generate one.")

    # Critical Config Check
    if not self.discord_token:
      self.logger.error("[FATAL] 'discord.token' missing in config.json")
      sys.exit(1)

    if not self.discord_channel_id:
      self.logger.error("[FATAL] 'discord.heartbeat_channel_id' missing in config.json")
      sys.exit(1)

    if not self.encryption_key:
      self.logger.error("[FATAL] 'discord.encryption_key' missing in config.json")
      sys.exit(1)

    if not self.admin_password:
      self.logger.error("[FATAL] 'admin_password' missing in config.json")
      sys.exit(1)

    # 2. Paths
    # --------
    self.data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.data'))
    if not os.path.exists(self.data_dir):
      os.makedirs(self.data_dir)

    # 3. Initialization
    # -----------------
    self.transport: Optional[DiscordTransport] = None
    self.current_version = "Unknown"
    try:
      # VERSION file is expected at ../../VERSION relative to this file
      version_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../VERSION'))
      if os.path.exists(version_file):
        with open(version_file, 'r', encoding='utf-8') as f:
          self.current_version = f.read().strip()
    except Exception as e:
      self.logger.warning(f"Could not read VERSION file: {e}")

    self.latest_version = "Unknown"
    self.update_available = False
    self.auth_sessions = set()

    # Components
    self.client_manager = ClientManager(os.path.join(self.data_dir, "clients.json"))
    self.ui_manager = UIManager(self)

    # Logs state
    self.logs: List[Dict] = []
    self.log_id_counter = 0

  # --------------------------------------------------------------------------------------------------------------------
  def add_log (self, _text: str, _client_id: str = "SYSTEM", _is_output=False, _is_user_input=False) -> None:
    """ Adds a log entry to the monitor's log list."""

    self.log_id_counter += 1
    entry = {
      "id": self.log_id_counter,
      "ts": datetime.now(),
      "client_id": _client_id,
      "text": _text,
      "is_output": _is_output,
      "is_user_input": _is_user_input
    }
    self.logs.append(entry)
    if len(self.logs) > 1000:
      self.logs.pop(0)

    # Notify UI
    try:
      self.ui_manager.refresh_logs()
      if self.ui_manager.selected_client_id == _client_id:
        self.ui_manager.refresh_terminal()
    except Exception:
      # Safely ignore UI updates if running in background task without client context
      pass

  # --------------------------------------------------------------------------------------------------------------------
  async def startup (self) -> None:
    """ Startup procedure for the monitor."""

    self.logger.info("Starting Lortnoc Monitor...")
    self.client_manager.load_clients()

    # Setup Transport
    self.transport = DiscordTransport(
      _token=self.discord_token,
      _listening_channels=[int(self.discord_channel_id)],
      _encryption_key=self.encryption_key
    )
    self.transport.on_message = self.on_transport_message

    await self.transport.connect()

    # Wait for connection to be ready (up to 10s)
    for _ in range(20):
      if getattr(self.transport, '_connected', False):
        break
      await asyncio.sleep(0.5)

    if not getattr(self.transport, '_connected', False):
      self.logger.warning("Discord Transport failed to connect within timeout. Startup pings may fail.")
    else:
      self.logger.info("Discord Transport connected and ready.")

    self.add_log("Monitor Started", "SYSTEM")

    # Wake up known clients
    count = 0
    for client in self.client_manager.get_all_clients():
      cmd_channel = client.get("command_channel_id")
      if cmd_channel:
        try:
          self.transport.add_listening_channel(int(cmd_channel))
          self.send_command(client["id"], "ping", _notify=False)
          count += 1
        except Exception as e:
          self.logger.warning(f"Failed to wake client {client['id']}: {e}")

    if count > 0:
      self.add_log(f"Ping sent to {count} devices", "SYSTEM")

    # Start Keep-Alive / Monitor Loop
    asyncio.create_task(self._monitor_loop())

  # --------------------------------------------------------------------------------------------------------------------
  async def _monitor_loop(self) -> None:
    """ Periodically checks for offline clients. """
    self.logger.info("Starting Offline Monitor Loop")
    while True:
      try:
        # Check for clients silent for more than 5 minutes (300s)
        # Assuming heartbeat interval is ~30s-60s
        changed = self.client_manager.check_offline_clients(timeout_seconds=300)
        if changed > 0:
          self.add_log(f"Marked {changed} clients as offline", "SYSTEM")
          # Force UI refresh
          self.ui_manager.refresh_sidebar()
          if self.ui_manager.current_view == "dashboard":
            self.ui_manager.show_dashboard()
      except Exception as e:
        self.logger.error(f"Error in monitor loop: {e}")

      await asyncio.sleep(60) # Run every minute

  # --------------------------------------------------------------------------------------------------------------------
  async def shutdown (self) -> None:
    """ Shutdown procedure for the monitor."""

    self.logger.info("Shutting down...")
    if self.transport:
      await self.transport.disconnect()
    self.client_manager.save_clients()

  # --------------------------------------------------------------------------------------------------------------------
  async def on_transport_message (self, _message: Dict) -> None:
    """ Callback from Transport when a message is received."""

    msg_type  = _message.get("type")
    client_id = _message.get("client_id")

    if not client_id and msg_type != "heartbeat":
      pass

    if msg_type == "heartbeat":
      self.handle_heartbeat(_message)
    elif msg_type == "output":
      self.handle_output(_message)
    elif msg_type == "log":
      self.add_log(f"Remote Log: {_message.get('data') or _message.get('message')}", client_id)

  # --------------------------------------------------------------------------------------------------------------------
  def handle_heartbeat (self, _message: Dict) -> None:
    """ Handles heartbeat messages from clients."""

    data = _message.get("data", {})
    client_payload = {
      "id": _message.get("client_id"),
      "name": data.get("hostname", "Unknown"),
      "ip": data.get("ip", "Unknown"),
      "cpu": data.get("cpu", 0),
      "ram": data.get("ram", 0),
      "disk": data.get("disk", 0),
      "temp": data.get("temp", 0),
      "net_sent": data.get("net_sent", 0),
      "net_recv": data.get("net_recv", 0),
      "version": data.get("version", "unknown"),
      "command_channel_id": data.get("command_channel_id"),
      "status": "online"
    }

    self.client_manager.update_client(client_payload)

    # Dynamic Channel Registration
    cmd_channel = data.get("command_channel_id")
    if cmd_channel and self.transport:
      try:
        self.transport.add_listening_channel(int(cmd_channel))
      except Exception:
        pass

    # Update Global version info if present
    if "latest_version" in data:
      self.latest_version = data["latest_version"]
      self.ui_manager.render_system_update_btn.refresh()

    self.ui_manager.refresh_dashboard()
    self.ui_manager.refresh_sidebar()
    self.ui_manager.refresh_client_view()

  # --------------------------------------------------------------------------------------------------------------------
  def handle_output (self, _message: Dict) -> None:
    """ Handles output messages from clients."""

    client_id = _message.get("client_id")
    data      = _message.get("data", "")
    self.add_log(data, client_id, _is_output=True)

  # --------------------------------------------------------------------------------------------------------------------
  def send_command (self, _client_id: str, _cmd: str, _args: List[str] = None, _notify: bool = True) -> None:
    """ Sends a command to a specific client."""

    if not self.transport:
      if _notify:
        ui.notify("Transport not connected", type="negative")
      return

    # Resolve target channel from client manager
    client = self.client_manager.get_client(_client_id)
    target_channel = None
    if client:
      target_channel = client.get("command_channel_id")

    if not target_channel:
      if _notify:
        ui.notify(f"Cannot send command: Unknown route to client {_client_id}", type="negative")
      else:
        self.logger.warning(f"Cannot send command to {_client_id}: Unknown route")
      return

    payload = {
      "type": "command",
      "target_id": _client_id,
      "action": _cmd,
      "args": _args or [],
      "_target_channel_id": int(target_channel)
    }

    # We don't await here to not block UI, fire and forget or create task
    asyncio.create_task(self.transport.send(payload))

    if _cmd == "exec":
      cmd_str = f"{_args[0]}" if _args else "exec"
      self.add_log(f"> {cmd_str}", _client_id, _is_user_input=True)
    else:
      self.add_log(f"Command: {_cmd}", _client_id, _is_user_input=False)
      if _notify:
        ui.notify(f"Sent {_cmd} to {_client_id}")

  # --------------------------------------------------------------------------------------------------------------------
  def delete_client (self, _client_id: str) -> None:
    """ Deletes a client from the monitor."""

    self.client_manager.remove_client(_client_id)
    self.ui_manager.show_dashboard()
    ui.notify("Client removed")

  # --------------------------------------------------------------------------------------------------------------------
  def trigger_update (self):
    """
    Handles the 'System Update' action.
    Since the Monitor runs efficiently in Docker, it cannot easily update itself and restart the container.
    """
    ui.notify("Update must be performed manually on the server (Docker pull & restart)",
              type="warning",
              close_button="OK",
              multi_line=True,
              timeout=0)


# I N I T ##############################################################################################################
# Global variable to be accessed by lifespan
_monitor_instance: Optional[LortnocMonitor] = None

# ----------------------------------------------------------------------------------------------------------------------
# Lifespan Context Manager replacement for startup/shutdown events
@asynccontextmanager
async def lifespan(_app: FastAPI):
  """ Lifespan context manager for FastAPI application."""

  # Determine if we have access to monitor here
  # Since we create monitor in main scope or init context, let's access it.
  if _monitor_instance:
    await _monitor_instance.startup()
  yield
  if _monitor_instance:
    await _monitor_instance.shutdown()

# ----------------------------------------------------------------------------------------------------------------------
def setup_app_components (_app: FastAPI, _monitor: LortnocMonitor) -> None:
  """ Sets up the FastAPI application components including middleware and UI."""

  # Add Middleware
  _app.add_middleware(AuthMiddleware, _monitor_app=_monitor)

  # Setup UI
  _monitor.ui_manager.setup_ui()


# M A I N ##############################################################################################################
if __name__ in {"__main__", "__mp_main__"}:
  try:
    _monitor_instance = LortnocMonitor()

    # Create FastAPI app with lifespan
    app_api = FastAPI(lifespan=lifespan)

    # 1. Setup Pages (Routes) FIRST
    _monitor_instance.ui_manager.setup_ui()

    # 2. Add Middleware (Last, to wrap everything)
    app_api.add_middleware(AuthMiddleware, _monitor_app=_monitor_instance)

    # Start NiceGUI
    current_ver = _monitor_instance.current_version if _monitor_instance else "Unknown"
    ui.run_with(app_api, title=f"Lortnoc Monitor {current_ver}", favicon='⌘', storage_secret=secrets.token_hex(16))

    # Silence noisy loggers (WebSockets, Access, etc)
    noisy_loggers = [
      "uvicorn", "uvicorn.access", "uvicorn.error", "uvicorn.asgi",
      "websockets", "multipart",
      "engineio", "engineio.server", "socketio", "socketio.server", "socketio.client"
    ]
    for _logger_name in noisy_loggers:
      logging.getLogger(_logger_name).setLevel(logging.WARNING)

    # Force disable uvicorn access logger propagation
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False

    uvicorn.run(app_api, host="0.0.0.0", port=8080, access_log=False)

  except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
