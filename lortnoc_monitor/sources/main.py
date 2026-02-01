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
import json
import uuid
import secrets
from datetime import datetime
import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from nicegui import ui, app
from fastapi import Request
from fastapi.responses import RedirectResponse, FileResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Import Transport
from lortnoc_core.transport_discord import DiscordTransport
from lortnoc_core.logger import setup_logging
from lortnoc_core.config import load_config


# C L A S S ############################################################################################################
class AuthMiddleware(BaseHTTPMiddleware):
  """
  Simple Middleware to protect routes with a password.
  """
  def __init__ (self, app_instance, monitor_app) -> None:
    super().__init__(app_instance)
    self.monitor_app = monitor_app

  # --------------------------------------------------------------------------------------------------------------------
  async def dispatch (self, request: Request, call_next) -> Any:
    # If no password configured, pass through
    if not self.monitor_app.admin_password:
      return await call_next(request)

    path = request.url.path
    # Whitelist paths
    if path.startswith('/_nicegui') or \
      path.startswith('/static') or \
      path == '/login':
      return await call_next(request)

    # Check session cookie
    session_token = request.cookies.get('auth_token')
    if session_token and session_token in self.monitor_app.AUTH_SESSIONS:
      return await call_next(request)

    # Redirect to login
    return RedirectResponse('/login')


# C L A S S ############################################################################################################
class LortnocMonitor:
  """
  Main Application class for Lortnoc Monitor.
  Handles state, transport, and UI rendering.
  """

  # Theme Constants
  THEME = {
    'card': 'bg-slate-800 border-none shadow-lg text-white p-4',
    'card_hover': 'bg-slate-800 border-none shadow-lg text-white p-4 cursor-pointer hover:bg-slate-700 transition-colors',
    'page_bg': 'bg-slate-900 text-slate-200',
    'sidebar': 'bg-slate-950 border-r border-slate-800',
    'terminal': 'bg-[#1e1e1e] text-slate-300 border-slate-700 shadow-xl font-mono text-sm'
  }

  DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../data'))
  CLIENTS_FILE = os.path.join(DATA_DIR, 'clients.json')

  # Auth State
  AUTH_SESSIONS = set() # Stores valid session tokens

  # Update Status
  latest_version = "Checking..."
  current_version = "Unknown"
  update_available = False

  # ----------------------------------------------------------------------------------------------------------------------
  def __init__ (self) -> None:
    # Load Config
    self.config = load_config()
    setup_logging(self.config.get("log_file", "/tmp/lortnoc.log"))
    self.logger = logging.getLogger("lortnoc-monitor")

    # Auth Config
    self.admin_password = self.config.get("admin_password")
    self.otp_enabled = self.config.get("otp_enabled", False)
    if not self.admin_password:
      # If no password set, warn but allow (or default to 'admin')
      self.logger.warning("No 'admin_password' in config. Authentication DISABLED.")

    # Initialize Transport
    self.logger.info("Running in PRODUCTION MODE (Discord)")
    discord_conf = self.config.get("discord", {})
    token = discord_conf.get("token")
    hb_id = discord_conf.get("heartbeat_channel_id")

    # Critical Config Validation
    if not token:
      self.logger.critical("Discord Token is missing in config. Exiting.")
      sys.exit(1)

    if not hb_id:
      self.logger.critical("Heartbeat Channel ID is missing in config. Exiting.")
      sys.exit(1)

    # Load persisted clients first to get their channels
    self.clients: List[Dict[str, Any]] = self._load_persisted_clients()

    # Version State
    self.current_version = "Unknown"
    self.latest_version = "Unknown"
    self.update_available = False

    # Monitor listens to EVERYTHING: Heartbeats AND Commands (for feedback logs)
    # Use a set to automatically deduplicate channel IDs
    channels_to_listen = {
      int(cid) for cid in [
        discord_conf.get("heartbeat_channel_id"),
        discord_conf.get("command_channel_id"),
        discord_conf.get("channel_id")
      ] if cid
    }

    # Add dynamic channels from persisted clients
    for client in self.clients:
      if cid := client.get('command_channel_id'):
        channels_to_listen.add(int(cid))

    if not token or not channels_to_listen:
      raise ValueError("Discord token or channel IDs missing in config")

    self.logger.info(f"Listening on {len(channels_to_listen)} channels")
    self.transport = DiscordTransport(token, list(channels_to_listen))

    # Identical to previous block, removed self.transport.set_callback call from constructor as it was redundant or misplaced
    self.transport.set_callback(self.handle_message)

    # Logs now store dicts: {ts, client_id, text, is_cmd}
    self.logs: List[Dict[str, Any]] = []
    self.current_view: str = "dashboard"
    self.selected_client_id: Optional[str] = None
    self.main_container: Optional[Any] = None

  # ----------------------------------------------------------------------------------------------------------------------
  def _load_persisted_clients (self) -> List[Dict[str, Any]]:
    if not os.path.exists(self.CLIENTS_FILE):
      return []
    try:
      with open(self.CLIENTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # Mark all loaded clients as offline initially (waiting for heartbeat)
        for client in data:
          client['status'] = 'offline'
        self.logger.info(f"Loaded {len(data)} known clients from disk.")
        return data
    except Exception as e:
      self.logger.error(f"Failed to load persisted clients: {e}")
      return []

  # ----------------------------------------------------------------------------------------------------------------------
  def _save_persisted_clients (self) -> None:
    try:
      if not os.path.exists(self.DATA_DIR):
        os.makedirs(self.DATA_DIR)

      # Determine path relative to file
      with open(self.CLIENTS_FILE, 'w', encoding='utf-8') as f:
        # Save current state.
        json.dump(self.clients, f, default=str)
    except Exception as e:
      self.logger.error(f"Failed to save clients: {e}")


  # ----------------------------------------------------------------------------------------------------------------------
  async def handle_message (self, _msg: Dict[str, Any]) -> None:
    """Processes incoming messages from the transport layer."""

    # Check for legacy clients
    if 'client_name' not in _msg and 'client_id' in _msg:
      _msg['client_name'] = _msg['client_id']

    if _msg['type'] == 'heartbeat':
      self._handle_heartbeat(_msg)
    elif _msg['type'] == 'log':
      self._handle_log(_msg)

  # ----------------------------------------------------------------------------------------------------------------------
  def _handle_heartbeat (self, _msg: Dict[str, Any]) -> None:
    cid = _msg['client_id']
    payload = _msg['payload']

    should_save_clients = False

    # Update or Add Client
    existing = next((c for c in self.clients if c['id'] == cid), None)
    if existing:
      # Check for structural changes that require saving
      if existing.get('name') != _msg.get('client_name', existing['name']) or \
        existing.get('command_channel_id') != payload.get('command_channel_id'):
        should_save_clients = True

      existing.update(payload)
      existing['status'] = payload['status']
      existing['name'] = _msg.get('client_name', existing['name'])
      existing['last_seen'] = datetime.now()

      # DYNAMIC LISTENING: If monitor isn't listening to this channel yet, add it!
      if 'command_channel_id' in payload:
        cmd_channel = payload['command_channel_id']
        existing['command_channel_id'] = cmd_channel
        if cmd_channel and isinstance(self.transport, DiscordTransport):
          # Check if new before processing to trigger save only on change
          if cmd_channel not in self.transport.listening_channels:
            self.transport.add_listening_channel(cmd_channel)
    else:
      should_save_clients = True
      cmd_channel = payload.get("command_channel_id")
      new_client = {
        "id": cid,
        "name": _msg.get('client_name', cid),
        "command_channel_id": cmd_channel,
        "last_seen": datetime.now(),
        **payload
      }
      # DYNAMIC LISTENING for new clients
      if cmd_channel and isinstance(self.transport, DiscordTransport):
        if cmd_channel not in self.transport.listening_channels:
          self.transport.add_listening_channel(cmd_channel)

      self.clients.append(new_client)
      self.clients.sort(key=lambda x: x['name'])

    if should_save_clients:
      self._save_persisted_clients()

    # Refresh UI
    self.refresh_sidebar()
    if self.current_view == "dashboard":
      self.refresh_dashboard()
    elif self.current_view == "client" and self.selected_client_id == cid:
      self.refresh_client_view()

  # ----------------------------------------------------------------------------------------------------------------------
  def _handle_log (self, _msg: Dict[str, Any]) -> None:
    ts = datetime.fromtimestamp(_msg.get('timestamp', 0))
    raw_msg = _msg.get('message', '')
    cid = _msg.get('client_id', 'SYSTEM')

    display_text = raw_msg
    is_cmd_output = False

    # Generic detection for any command output: CMD 'action': result
    if raw_msg.strip().startswith("CMD '") and "':" in raw_msg:
      try:
        # Extract content after the first "':"
        parts = raw_msg.split("':", 1)
        if len(parts) == 2:
          display_text = parts[1].strip()
          is_cmd_output = True
      except Exception:
        pass

    entry = {
      "id": str(uuid.uuid4()),
      "ts": ts,
      "client_id": cid,
      "text": display_text,
      "is_output": is_cmd_output,
      "is_user_input": False
    }

    self.logs.insert(0, entry)
    self.logs = self.logs[:50]
    self.refresh_logs()
    if self.current_view == "client":
      self.refresh_terminal()

  # ----------------------------------------------------------------------------------------------------------------------
  def send_command (self, _client_id: str, _action: str, _args: Optional[List[Any]] = None) -> None:
    if _args is None:
      _args = []

    # Identify target channel
    target_channel_id = None
    client = next((c for c in self.clients if c["id"] == _client_id), None)
    if client and client.get("command_channel_id"):
      target_channel_id = client["command_channel_id"]

    logger_msg = f"Sending '{_action}' to {_client_id}"
    term_text = f"MONITOR: {logger_msg}..."
    is_user_input = False

    if _action == "exec" and _args:
      term_text = f"$ {_args[0]}"
      is_user_input = True
    elif _action in ["reboot", "shutdown", "update"]:
      term_text = f"$ {_action}"
      is_user_input = True
    elif target_channel_id:
      logger_msg += f" (on channel {target_channel_id})"

    entry = {
      "id": str(uuid.uuid4()),
      "ts": datetime.now(),
      "client_id": _client_id,
      "text": term_text,
      "is_output": False,
      "is_user_input": is_user_input,
      "log_msg": logger_msg # For global panel
    }
    self.logs.insert(0, entry)
    self.refresh_logs()

    asyncio.create_task(self.transport.send({
      "type": "command",
      "target_id": _client_id,
      "action": _action,
      "args": _args,
      "_target_channel_id": int(target_channel_id) if target_channel_id else None
    }))

    if self.current_view == "client" and self.selected_client_id == _client_id:
      self.refresh_terminal()

  # ----------------------------------------------------------------------------------------------------------------------
  def trigger_update (self) -> None:
    with ui.dialog() as dialog, ui.card().classes('bg-slate-900 border border-slate-700 p-6'):
      ui.label('Update Monitor').classes('text-lg font-bold text-white mb-2')
      ui.label('The monitor allows running in a container, so it cannot update itself autonomously.').classes('text-sm text-slate-400 mb-2')
      ui.html('To update, please run this command on the host:<br/><div class="mt-2 p-3 bg-black rounded font-mono text-xs select-all text-green-400">curl -sL https://raw.githubusercontent.com/lortnoc/lortnoc/main/tools/installers/install_monitor.sh | bash</div>').classes('text-sm text-slate-300')
      with ui.row().classes('w-full justify-end mt-6'):
        ui.button('Close', on_click=dialog.close).props('color=primary')
    dialog.open()


  # U I   M E T H O D S ------------------------------------------------------------------------------------------------
  def setup_ui (self) -> None:
    """Defines the main UI structure."""

    # ------------------------------------------------------------------------------------------------------------------
    @ui.page('/login')
    def login_view () -> None:
      # Simple state container
      class LoginState:
        otp_sent = False
        generated_otp = None
        password = ""
        otp_code = ""

      ls = LoginState()

      def finalize_login():
        token = str(uuid.uuid4())
        self.AUTH_SESSIONS.add(token)
        ui.run_javascript(f'document.cookie = "auth_token={token}; path=/"; window.location.href = "/"')

      async def process_password():
        if ls.password == self.admin_password:
          if not self.otp_enabled:
            finalize_login()
          else:
            # Generate OTP
            otp = str(secrets.randbelow(1000000)).zfill(6)
            ls.generated_otp = otp

            # Send to Discord
            success = await self.transport.send_message_to_channel_name("authentication", f"🔑 Lortnoc Login OTP: **{otp}**")

            if success:
              ls.otp_sent = True
              form_area.refresh()
              ui.notify('OTP sent to Discord', type='positive')
            else:
              ui.notify('Failed to send OTP (Discord Error)', type='negative')
        else:
          ui.notify('Invalid Password', color='negative')

      def process_otp():
        # Simple string comparison
        if ls.otp_code and ls.otp_code.strip() == ls.generated_otp:
          finalize_login()
        else:
          ui.notify('Invalid OTP code', color='negative')

      def reset_state():
        ls.otp_sent = False
        ls.password = ""
        ls.otp_code = ""
        form_area.refresh()

      # Use h-screen to ensure full viewport height for centering
      ui.query('.nicegui-content').classes('p-0 m-0 w-full h-screen flex items-center justify-center bg-slate-950')
      with ui.card().classes('w-96 p-8 bg-slate-900 border border-slate-800 shadow-xl items-center'):
        ui.icon('lock', size='3rem').classes('text-blue-500 mb-4')
        ui.label('Lortnoc Access').classes('text-xl font-bold text-white mb-6')

        @ui.refreshable
        def form_area():
          if not ls.otp_sent:
            ui.input('Password', password=True).bind_value(ls, 'password').classes('w-full mb-6').props('outlined autofocus').on('keydown.enter', process_password)
            ui.button('Login', on_click=process_password).classes('w-full bg-blue-600 hover:bg-blue-700 text-white font-bold')
          else:
            ui.label('Enter the 6-digit code sent to Discord').classes('text-sm text-slate-400 mb-4 text-center')
            ui.input('OTP Code').bind_value(ls, 'otp_code').classes('w-full mb-6').props('outlined autofocus input-class="text-center tracking-widest"').on('keydown.enter', process_otp)
            ui.button('Verify', on_click=process_otp).classes('w-full bg-green-600 hover:bg-green-700 text-white font-bold')
            ui.button('Back', on_click=reset_state).classes('w-full mt-2 flat text-slate-500 hover:text-white')

        form_area()

    # ------------------------------------------------------------------------------------------------------------------
    @ui.page('/')
    def main_page () -> None:
      ui.colors(primary='#3b82f6') # blue-500
      ui.query('.nicegui-content').classes('p-0 m-0 w-full h-full')
      ui.dark_mode().enable()
      ui.add_head_html('''
        <style>
          body { background-color: #0f172a; }
          .cmd-input .q-field__native {
              color: #4ade80 !important;
              caret-color: #4ade80 !important;
              font-family: monospace !important;
              font-weight: bold !important;
          }
        </style>
      ''')

      with ui.row().classes('w-full h-screen no-wrap bg-slate-900 text-slate-200 overflow-hidden'):
        # Sidebar
        with ui.column().classes(f'w-72 {self.THEME["sidebar"]} p-6 h-full gap-6 overflow-hidden'):
          # Logo
          with ui.row().classes('items-center gap-3 mb-4 cursor-pointer').on('click', self.show_dashboard):
            ui.icon('hub', size='md', color='blue-500')
            ui.label('Lortnoc').classes('text-2xl font-black text-white tracking-wide')

          # Client List
          self.render_sidebar_list()
          ui.separator().classes('border-slate-800')

          # Logs
          with ui.scroll_area().classes('flex-grow w-full pr-2 min-h-0'):
            self.render_logs_panel()

          # System Footer
          ui.separator().classes('border-slate-800')
          with ui.row().classes('w-full justify-between items-center'):
            # Only display version if known, otherwise hide or show as Dev
            ui.label().classes('text-xs text-slate-600 font-mono').bind_text_from(
                self, 'current_version',
                backward=lambda v: f"v{v}" if v and v.lower() != "unknown" else "Dev"
            )
            # Dynamic Update Button Component
            self.render_system_update_btn()

        # Content
        # We use a simple flex column that fills the screen. Overflow hidden preventing the window scrollbar.
        with ui.column().classes(f'flex-grow h-full overflow-hidden {self.THEME["page_bg"]} p-0 gap-0'):
          self.main_container = ui.column().classes('w-full h-full p-0 gap-0 items-stretch')
          with self.main_container:
            self.render_dashboard_content()

  # ----------------------------------------------------------------------------------------------------------------------
  def show_dashboard (self) -> None:
    self.current_view = "dashboard"
    self.selected_client_id = None
    if self.main_container:
      self.main_container.clear()
      with self.main_container:
        self.render_dashboard_content()
    self.refresh_sidebar()

  # ----------------------------------------------------------------------------------------------------------------------
  def show_client (self, _client_id: str) -> None:
    self.current_view = "client"
    self.selected_client_id = _client_id
    if self.main_container:
      self.main_container.clear()
      with self.main_container:
        self.render_client_content()
    self.refresh_sidebar()


  # C O M P O N E N T S (Refreshable wrappers) --------------------------------------------------------------------------
  @ui.refreshable
  def render_system_update_btn(self) -> None:
      if not self.update_available:
        return

      # Use system_update instead of system_update_alt
      with ui.button(icon='system_update', on_click=self.trigger_update) \
               .props('round dense color=green'):
          ui.tooltip('Update Available!')

  @ui.refreshable
  def render_sidebar_list (self) -> None:
    ui.label('DEVICES').classes('text-xs font-bold text-slate-500 tracking-wider')
    with ui.column().classes('w-full gap-2'):
      if not self.clients:
        ui.label("Waiting for devices...").classes('text-xs text-slate-600 italic')

      for client in self.clients:
        active = (self.current_view == "client" and self.selected_client_id == client["id"])
        bg_class = 'bg-slate-800 border-slate-600' if active else 'hover:bg-slate-800 border-transparent'

        with ui.card().classes(f'w-full p-3 {bg_class} bg-transparent shadow-none border hover:border-slate-700 transition-all rounded-lg cursor-pointer').on(
          'click', lambda c=client: self.show_client(c["id"])
        ):
          with ui.row().classes('items-center justify-between w-full no-wrap'):
            with ui.row().classes('items-center gap-3 no-wrap'):
              ui.icon('dns', size='xs', color='blue-400' if active else 'slate-400')
              with ui.column().classes('gap-0'):
                ui.label(client["name"]).classes(
                  f'text-sm font-bold leading-tight {"text-blue-400" if active else "text-slate-200"}'
                )
                ui.label(client.get("ip", "???")).classes('text-xs text-slate-500 leading-tight')

            status = client.get("status", "offline")
            status_color = 'green-500' if status == 'online' else 'red-500'
            ui.element('div').classes(
              f'w-2 h-2 rounded-full bg-{status_color}' +
              (' shadow-[0_0_8px_rgba(34,197,94,0.5)]' if status == 'online' else '')
            )

  # ----------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_logs_panel (self) -> None:
    ui.label('SYSTEM ACTIVITY').classes('text-xs font-bold text-slate-500 tracking-wider')
    with ui.column().classes('gap-2 w-full'):
      for log in self.logs:
        ts_str = log['ts'].strftime('%H:%M:%S')
        # Use specific log message if available, else generic text
        content = log.get('log_msg', log['text'])
        # Truncate content for global log if too long (output)
        if len(content) > 100:
          content = content[:100] + "..."

        with ui.row().classes('w-full items-start gap-2 text-[11px] font-mono text-slate-400 border-l-2 border-slate-800 pl-2 py-1'):
          ui.label(f"[{ts_str}] {log['client_id']}: {content}").classes('break-all leading-tight')

  # ----------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_dashboard_content (self) -> None:
    with ui.scroll_area().classes('w-full h-full p-10'):
      with ui.column().classes('w-full max-w-5xl mx-auto'):
        ui.label('Dashboard Global').classes('text-3xl font-bold tracking-tight text-white mb-4')

        total_online = sum(1 for c in self.clients if c.get("status") == "online")

        with ui.grid(columns=3).classes('w-full gap-4'):
          # Summary Cards
          with ui.card().classes(self.THEME['card']):
            ui.label('Online Devices').classes('text-sm text-slate-400')
            ui.label(f"{total_online} / {len(self.clients)}").classes('text-4xl font-bold mt-2')

          avg_cpu = 0
          if self.clients:
            avg_cpu = sum(c.get("cpu", 0) for c in self.clients) / len(self.clients)

          with ui.card().classes(self.THEME['card']):
            ui.label('Avg Flotte CPU').classes('text-sm text-slate-400')
            ui.label(f"{avg_cpu:.1f}%").classes('text-4xl font-bold mt-2 text-blue-400')

        ui.label('Vue d\'ensemble').classes('text-xl font-bold text-white mt-8 mb-4')

        if not self.clients:
          ui.label("Aucun appareil détecté. En attente de heartbeats...").classes('text-slate-500 italic')

        with ui.grid(columns=3).classes('w-full gap-4'):
          for client in self.clients:
            self.render_mini_client_card(client)

  # ----------------------------------------------------------------------------------------------------------------------
  def render_mini_client_card (self, _client) -> None:
    status = _client.get("status", "offline")
    status_color = 'green-500' if status == 'online' else 'red-500'

    with ui.card().classes(self.THEME['card_hover']).on('click', lambda c=_client: self.show_client(c["id"])):
      with ui.row().classes('w-full justify-between items-start'):
        with ui.row().classes('items-center gap-3'):
          with ui.avatar(color='slate-700', text_color='white'):
            ui.icon('dns')
          ui.label(_client["name"]).classes('font-bold text-lg')

        ui.element('div').classes(
          f'w-3 h-3 rounded-full bg-{status_color}' +
          (' shadow-[0_0_8px_rgba(34,197,94,0.5)]' if status == 'online' else '')
        )

      if status == "online":
        with ui.row().classes('w-full gap-4 mt-6'):
          self._stat_mini(_client, 'CPU', 'cpu')
          self._stat_mini(_client, 'RAM', 'ram')
          self._stat_mini_text(_client, 'IP', 'ip')
      else:
        ui.label('Hors ligne').classes('mt-6 text-slate-500 italic')

  # ----------------------------------------------------------------------------------------------------------------------
  def _stat_mini (self, _client, _label, _key) -> None:
    with ui.column().classes('gap-1'):
      ui.label(_label).classes('text-xs text-slate-400')
      ui.label(f"{_client.get(_key,0)}%").classes('font-bold')

  # ----------------------------------------------------------------------------------------------------------------------
  def _stat_mini_text (self, _client, _label, _key) -> None:
    with ui.column().classes('gap-1'):
      ui.label(_label).classes('text-xs text-slate-400')
      ui.label(_client.get(_key, '-')).classes('font-mono text-xs')

  # ----------------------------------------------------------------------------------------------------------------------
  def render_client_content (self) -> None:
    client = next((c for c in self.clients if c["id"] == self.selected_client_id), None)
    if not client:
      ui.label("Client introuvable").classes('text-red-500')
      return

    # Main container restricted to screen height
    with ui.column().classes('w-full h-full max-w-5xl mx-auto flex flex-col overflow-hidden no-wrap gap-4 p-6'):
      self.render_client_header(client)

      if client.get("status") == 'online':
        self.render_client_stats(client)

        # Terminal Area
        # Flex-1 ensures it takes all remaining space but RESPECTS the parent height.
        # min-h-0 is critical for nested scrolling flex children.
        with ui.card().classes(f"{self.THEME['terminal']} w-full flex-1 flex flex-col min-h-0 overflow-hidden p-0"):
          with ui.row().classes('w-full bg-[#2d2d2d] px-4 py-1 items-center gap-2 border-b border-black flex-none'):
            ui.label(f"ssh root@{client.get('ip','remote')}").classes('ml-2 text-xs text-slate-400')

          # Terminal Output: flex-1 + overflow-y-auto to scroll INSIDE this box
          # Added unique class 'terminal-scroll-container' for JS targeting
          # Removed scroll-smooth to prevent fighting with JS auto-scroll
          with ui.column().classes('p-4 w-full gap-1 flex-1 overflow-y-auto bg-[#1e1e1e] terminal-scroll-container'):
            self.render_client_terminal()

          # Input: flex-none to stay fixed at bottom
          # Added z-10 and relative to ensure it sits ON TOP of the scroll area if they overlap
          with ui.row().classes('w-full bg-[#1e1e1e] pl-4 pr-2 py-2 items-center border-t border-slate-700 flex-none relative z-10'):
            ui.label("root@monitor-cmd:~#").classes('text-green-400 font-bold mr-2')
            cmd_input = ui.input(placeholder='Send raw command...').props(
              'dense borderless autofocus'
            ).classes(
              'flex-grow text-green-400 font-mono tracking-wider cmd-input'
            ).on('keydown.enter', lambda e: self._on_cmd_enter(e, client['id']))

            # Force keep focus if lost during updates
            cmd_input.on('blur', lambda: cmd_input.run_method('focus'))
      else:
        with ui.column().classes('w-full items-center justify-center flex-1 opacity-50'):
          ui.icon('cloud_off', size='160px', color='slate-700')
          ui.label('Device Offline').classes('text-5xl font-bold text-slate-500 mt-8 mb-2')

  # ----------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_client_header (self, _client) -> None:
    status = _client.get("status", "offline")
    client_ver = _client.get("version", "unknown")

    # Check update status
    is_outdated = False
    if self.latest_version and self.latest_version != "Unknown" and client_ver != "unknown":
      # basic string compare (assumes vX.Y.Z)
      if self.latest_version.lstrip('v') != client_ver.lstrip('v'):
        is_outdated = True

    with ui.row().classes('w-full items-center justify-between pb-4 border-b border-slate-700'):
      with ui.row().classes('items-center gap-4 flex-grow'):
        with ui.avatar(color='primary' if status == 'online' else 'grey', text_color='white'):
          ui.icon('dns')

        with ui.column().classes('gap-0 flex-grow'):
          with ui.row().classes('items-center justify-between w-full'):
            ui.label(_client["name"]).classes('text-3xl font-bold tracking-tight text-white')

            if status == 'online':
              with ui.row().classes('gap-3'):
                self._action_btn('replay', 'warning', 'Reboot', lambda: self._confirm_and_send(_client, 'reboot'))
                self._action_btn('power_off', 'negative', 'Shutdown', lambda: self._confirm_and_send(_client, 'shutdown'))

                # Update Button Logic
                if is_outdated:
                   with ui.button(icon='system_update', on_click=lambda: self._confirm_and_send(_client, 'update')) \
                        .props('flat dense color=green').classes('text-green-400 border border-green-500'):
                     ui.tooltip(f'Update to {self.latest_version}')
                     ui.label('UPDATE AVAILABLE').classes('ml-2 font-bold')

            else:
              # Only allow delete if offline
              self._action_btn('delete', 'negative', 'Delete Client', lambda: self._confirm_delete(_client))

          with ui.row().classes('items-center gap-2'):
            status_class = 'bg-green-500' if status == 'online' else 'bg-red-500'
            ui.element('div').classes(f'w-2 h-2 rounded-full {status_class}')

            # Version Badge
            version_color = 'text-green-400' if not is_outdated and client_ver != 'unknown' else 'text-slate-500'
            if is_outdated:
              version_color = 'text-amber-500'

            ui.label(f"v{client_ver}").classes(f'text-xs font-mono {version_color} font-bold mr-2')

            ui.separator().props('vertical').classes('h-4 border-slate-700')

            seen_time = _client.get('last_seen')
            if isinstance(seen_time, str):
               # Try parse if loaded from JSON
               try: seen_time = datetime.fromisoformat(seen_time)
               except: pass

            seen_str = "Never"
            if isinstance(seen_time, datetime):
                diff = (datetime.now() - seen_time).total_seconds()
                if diff < 60:
                    seen_str = "Just now"
                elif diff < 3600:
                    seen_str = f"{int(diff // 60)} min ago"
                elif diff < 86400:
                    seen_str = f"{int(diff // 3600)} h ago"
                else:
                    seen_str = f"{int(diff // 86400)} days ago"

            ui.label(f"{status.upper()} • {_client.get('ip', 'N/A')} • {seen_str}").classes('text-sm text-slate-400')

  # ----------------------------------------------------------------------------------------------------------------------
  def _confirm_delete (self, _client) -> None:
    with ui.dialog() as dialog:
      with ui.card().classes('bg-slate-800 text-white border border-slate-600'):
        ui.label(f"Delete '{_client['name']}'?").classes('text-lg font-bold text-red-500')
        ui.label(f"This will remove the client from the list.").classes('text-slate-300')
        ui.label(f"It will reappear automatically if it sends a heartbeat.").classes('text-xs text-slate-500 italic mt-1')

        with ui.row().classes('w-full justify-end mt-4'):
          ui.button('Cancel', on_click=dialog.close).props('flat text-color=white')
          ui.button('DELETE', color='negative',
                    on_click=lambda: [self._delete_client(_client['id']), dialog.close()])
    dialog.open()

  # ----------------------------------------------------------------------------------------------------------------------
  def _delete_client (self, _client_id: str) -> None:
    self.clients = [c for c in self.clients if c['id'] != _client_id]
    self._save_persisted_clients()
    self.show_dashboard()
    ui.notify(f'Client {_client_id} removed', type='positive')

  # ----------------------------------------------------------------------------------------------------------------------
  def _confirm_and_send (self, _client, _action) -> None:
    with ui.dialog() as dialog:
      with ui.card().classes('bg-slate-800 text-white border border-slate-600'):
        ui.label(f"Execute '{_action}'?").classes('text-lg font-bold')
        ui.label(f"Do you really want to {_action} {_client['name']}?").classes('text-slate-300')

        with ui.row().classes('w-full justify-end mt-4'):
          ui.button('Cancel', on_click=dialog.close).props('flat text-color=white')
          ui.button('CONFIRM', color='red' if _action in ['reboot', 'shutdown'] else 'primary',
                    on_click=lambda: [self.send_command(_client['id'], _action), dialog.close()])

    dialog.open()

  # ----------------------------------------------------------------------------------------------------------------------
  def _action_btn (self, _icon, _color, _tooltip, _callback) -> None:
    ui.button(icon=_icon, color=_color, on_click=_callback).props('flat round size=md').tooltip(_tooltip)

  # ----------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_client_stats (self, _client) -> None:
    with ui.grid(columns=3).classes('w-full gap-4'):
      cpu = _client.get("cpu", 0)
      self._stat_card_big('CPU Load', f"{cpu}%", 'memory', 'blue', cpu / 100)

      ram = _client.get("ram", 0)
      self._stat_card_big('Memory', f"{ram}%", 'sd_storage', 'purple', ram / 100)

      temp = _client.get("temp", 0)
      self._stat_card_big('Temperature', f"{temp}°C", 'thermostat', 'red', temp / 85)

  # ----------------------------------------------------------------------------------------------------------------------
  def _stat_card_big (self, _title, _value, _icon, _color_name, _progress=None) -> None:
    with ui.card().classes(self.THEME['card']):
      with ui.row().classes('justify-between w-full items-center mb-2'):
        ui.label(_title).classes('text-sm text-slate-400 font-medium')
        ui.icon(_icon, color=f'{_color_name}-400', size='3xl')

      ui.label(_value).classes('text-3xl font-bold mb-2')
      if _progress is not None:
        ui.linear_progress(_progress, show_value=False).props(f'color={_color_name}-400 track-color={_color_name}-900').classes('rounded-full')

  # ----------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_client_terminal (self) -> None:
    try:
      # Filter logs for selected client
      relevant_logs = [l for l in self.logs if self.selected_client_id and l.get('client_id') == self.selected_client_id]

      if not relevant_logs:
        ui.label("No logs available for this device...").classes("text-slate-500 italic")
        return

      # We want chronological order in terminal (oldest at top), but logs are stored newest-first
      for log in reversed(relevant_logs):
        ts_str = log['ts'].strftime('%H:%M:%S')
        raw_text = log.get('text', '')

        # Ensure text is string and safe
        if not isinstance(raw_text, str):
          raw_text = str(raw_text)

        lid = log.get('id')

        # Determine style based on type
        style_class = 'font-mono text-[10px] text-slate-500 italic' # Default
        prefix = f"[{ts_str}] "

        if log.get('is_user_input'):
          style_class = 'font-mono text-xs text-green-400 font-bold mt-1'
        elif log.get('is_output'):
          style_class = 'font-mono text-xs text-slate-300 whitespace-pre-wrap break-all ml-2'
          prefix = ""

        # Hard limit for display
        limit = 1000
        display_text = raw_text
        truncated = False

        if len(raw_text) > limit:
          display_text = raw_text[:limit] + "\n... [TRUNCATED]"
          truncated = True

        # Render
        with ui.column().classes('gap-0 items-start'):
          ui.label(prefix + display_text).classes(style_class)
          if truncated and lid:
            ui.button('View Full', icon='visibility', on_click=lambda i=lid: self._show_full_log(i)) \
              .props('flat dense size=sm color=warning').classes('text-xs ml-2')

    except Exception as e:
      self.logger.error(f"Error rendering terminal: {e}")
      ui.label(f"RENDER ERROR: {e}").classes('text-red-500 font-bold')

    # Auto-scroll to bottom
    ui.run_javascript("var el = document.querySelector('.terminal-scroll-container'); if(el) el.scrollTop = el.scrollHeight;")

  # ----------------------------------------------------------------------------------------------------------------------
  def _show_full_log (self, _log_id: str) -> None:
    # Find log by ID to avoid passing huge strings in lambdas
    log = next((l for l in self.logs if l.get('id') == _log_id), None)
    content = log['text'] if log else "Log entry not found / expired."

    with ui.dialog() as dialog, ui.card().classes('w-full max-w-6xl h-[90vh] bg-slate-900 border border-slate-700 p-0 flex flex-col'):
      with ui.row().classes('w-full items-center justify-between border-b border-slate-700 p-4 bg-slate-950'):
        ui.label('Full Command Output').classes('text-lg font-bold text-white')
        ui.button(icon='close', on_click=dialog.close).props('flat round dense color=white')

      with ui.scroll_area().classes('w-full flex-grow bg-[#1e1e1e] p-4'):
        # Render full content
        ui.label(content).classes('font-mono text-xs text-slate-300 whitespace-pre-wrap break-all')
    dialog.open()

  # ----------------------------------------------------------------------------------------------------------------------
  def _on_cmd_enter (self, _e, _client_id) -> None:
    val = _e.sender.value
    if val:
      self.send_command(_client_id, "exec", [val])
      _e.sender.value = ""


  # R E F R E S H   H E L P E R S ----------------------------------------------------------------------------------------
  def refresh_sidebar (self) -> None:
    self.render_sidebar_list.refresh()  # type: ignore

  # ----------------------------------------------------------------------------------------------------------------------
  def refresh_logs (self) -> None:
    self.render_logs_panel.refresh()  # type: ignore

  # ----------------------------------------------------------------------------------------------------------------------
  def refresh_dashboard (self) -> None:
    self.render_dashboard_content.refresh()  # type: ignore

  # ----------------------------------------------------------------------------------------------------------------------
  def refresh_client_view (self) -> None:
    # Trigger update of stats and header components for the currently selected client
    if self.selected_client_id:
      current = next((c for c in self.clients if c["id"] == self.selected_client_id), None)
      if current:
        self.render_client_header.refresh(current)  # type: ignore
        self.render_client_stats.refresh(current)  # type: ignore

  # ----------------------------------------------------------------------------------------------------------------------
  def refresh_terminal (self) -> None:
    self.render_client_terminal.refresh()  # type: ignore


  # ----------------------------------------------------------------------------------------------------------------------
  async def check_for_updates(self) -> None:
    """
    Checks for updates by comparing local version with GitHub latest release.
    """
    try:
      # 1. Determine Local Version
      # In Docker, we expect /app/version.txt (mounted or copied)
      version_path = '/app/version.txt'
      if not os.path.exists(version_path):
        # Fallback for local testing if file exists in project root (assuming structure)
        # sources/main.py -> sources/ -> lortnoc_monitor/ -> repo root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        potential_path = os.path.join(current_dir, '../../version.txt')
        if os.path.exists(potential_path):
          version_path = potential_path

      if os.path.exists(version_path):
        with open(version_path, 'r', encoding='utf-8') as f:
          self.current_version = f.read().strip()
      else:
        self.logger.warning(f"Version file not found at {version_path}. Assuming dev/unknown version.")

      self.logger.info(f"Local Version: {self.current_version}")

      # 2. Fetch Latest from GitHub
      url = "https://api.github.com/repos/lortnoc/lortnoc/releases/latest"
      async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=10) as response:
          if response.status == 200:
            data = await response.json()
            self.latest_version = data.get("tag_name", "Unknown")

            # 3. Compare
            if self.current_version != "Unknown" and self.latest_version != "Unknown":
              # Remove 'v' prefix for comparison
              curr = self.current_version.lstrip('v')
              lat = self.latest_version.lstrip('v')

              if curr != lat:
                self.update_available = True
                self.logger.info(f"New version available: {self.latest_version}")
                ui.notify(f"Update Available: {self.latest_version}", type='info', close_button=True, timeout=0)

              # Refresh UI button
              self.render_system_update_btn.refresh()
          else:
            self.logger.warning(f"Failed to fetch updates from GitHub: {response.status}")

    except Exception as e:
      self.logger.error(f"Error checking for updates: {e}")


  # A P P   L I F E C Y C L E --------------------------------------------------------------------------------------------
  def run (self) -> None:
    # Add Auth Middleware
    app.add_middleware(AuthMiddleware, monitor_app=self)


    # Startup hooks
    app.on_startup(self.transport.connect)
    # Ping all known clients on startup to check availability
    app.on_startup(self.ping_all_clients)
    # Check for updates in background
    app.on_startup(self.check_for_updates)
    app.on_shutdown(self.transport.disconnect)

    # UI
    self.setup_ui()

    try:
      self.logger.info("Starting Lortnoc Monitor UI...")
      current_dir = os.path.dirname(os.path.abspath(__file__))
      # Resources are at root/resources relative to lortnoc_monitor/sources/
      # In Repo: lortnoc/lortnoc_monitor/sources -> ../../resources
      # In Docker: /app/lortnoc_monitor/sources -> ../../resources
      favicon_path = os.path.abspath(os.path.join(current_dir, '../../resources/lortnoc.png'))

      # Serve Apple Icons to prevent 404 logs
      @app.get('/apple-touch-icon.png')
      @app.get('/apple-touch-icon-precomposed.png')
      def apple_icon():
          if os.path.exists(favicon_path):
              return FileResponse(favicon_path)
          return RedirectResponse('/favicon.ico')

      ui.run(host='0.0.0.0', port=8080, title='Lortnoc Monitor', dark=True, reload=False, favicon=favicon_path)
    except Exception as e:
      self.logger.critical(f"Error initializing: {e}")
      sys.exit(-1)

  async def ping_all_clients(self) -> None:
    """Sends a ping command to all known clients to provoke a heartbeat."""
    # Give some time for transport to be fully ready
    await asyncio.sleep(5)
    self.logger.info("Broadcasting PING to all known clients...")
    for client in self.clients:
      if client.get('command_channel_id'):
        # Fire and forget PING
        self.send_command(client['id'], 'ping')


# M A I N ##############################################################################################################
if __name__ in {"__main__", "__mp_main__"}:
  try:
    monitor = LortnocMonitor()
    monitor.run()

  except KeyboardInterrupt:
    print("\n[!] User interrupted execution. Exiting...")
    sys.exit(0)

  except Exception as e:
    print(f"[!] Critical error: {e}")
    sys.exit(1)
