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

# pylint: disable=too-many-statements, too-many-branches, too-many-arguments, too-many-positional-arguments

# I M P O R T ##########################################################################################################
from datetime import datetime
import uuid
import pyotp
from nicegui import ui


# C L A S S ############################################################################################################
class UIManager:
  THEME = {
    'card': 'bg-slate-800 border-none shadow-lg text-white p-4',
    'card_hover': 'bg-slate-800 border-none shadow-lg text-white p-4 cursor-pointer hover:bg-slate-700 transition-colors',
    'page_bg': 'bg-slate-900 text-slate-200',
    'sidebar': 'bg-slate-950 border-r border-slate-800',
    'terminal': 'bg-[#1e1e1e] text-slate-300 border-slate-700 shadow-xl font-mono text-sm'
  }

  # --------------------------------------------------------------------------------------------------------------------
  def __init__ (self, monitor):
    self.monitor = monitor
    self.current_view = "dashboard"
    self.selected_client_id = None
    self.main_container = None

    # History for each client
    self.cmd_history = {} # client_id -> list of commands
    self.cmd_history_idx = {} # client_id -> int

  # --------------------------------------------------------------------------------------------------------------------
  def setup_ui (self):
    @ui.page('/login')
    def login_view():
      self.render_login_view()

    @ui.page('/')
    def main_page():
      self.render_main_page()

  # --------------------------------------------------------------------------------------------------------------------
  def render_login_view (self):
    # Simple state container
    class LoginState:
      password = ""
      otp_code = ""
      step = 1

    ls = LoginState()

    def finalize_login():
      token = str(uuid.uuid4())
      self.monitor.auth_sessions.add(token)
      ui.run_javascript(f'document.cookie = "auth_token={token}; path=/"; window.location.href = "/"')

    def check_password():
      if ls.password == self.monitor.admin_password:
        ls.step = 2
        render_form.refresh()
      else:
        ui.notify('Invalid Password', color='negative')

    def check_totp():
      if not self.monitor.totp_secret:
        ui.notify('System Error: No TOTP Secret loaded', color='negative')
        return

      totp = pyotp.TOTP(self.monitor.totp_secret)
      if totp.verify(ls.otp_code):
        finalize_login()
      else:
        ui.notify('Invalid OTP Code', color='negative')

    ui.query('.nicegui-content').classes('p-0 m-0 w-full h-screen flex items-center justify-center bg-slate-950')

    with ui.card().classes('w-96 p-8 bg-slate-900 border border-slate-800 shadow-xl items-center'):
      ui.icon('lock', size='3rem').classes('text-blue-500 mb-4')
      ui.label('Lortnoc Access').classes('text-xl font-bold text-white mb-6')

      @ui.refreshable
      def render_form():
        if ls.step == 1:
          # Password Input
          ui.input('Password', password=True).bind_value(ls, 'password').classes(
            'w-full mb-4 text-slate-200').props(
              'outlined autofocus dark name="password" autocomplete="current-password"'
          ).on('keydown.enter', check_password)

          ui.button('Next', on_click=check_password).classes('w-full bg-blue-600 hover:bg-blue-700 text-white font-bold')
        else:
          # TOTP Input
          ui.input('2FA Code (Google Auth)').bind_value(ls, 'otp_code').classes(
            'w-full mb-4 text-slate-200').props(
              'outlined autofocus dark name="totp" autocomplete="one-time-code" inputmode="numeric"'
          ).on('keydown.enter', check_totp)

          ui.button('Login', on_click=check_totp).classes('w-full bg-blue-600 hover:bg-blue-700 text-white font-bold')
          ui.button('Back', on_click=lambda: [setattr(ls, 'step', 1), render_form.refresh()]).props('flat').classes('w-full mt-2 text-slate-400')

      render_form()

  # --------------------------------------------------------------------------------------------------------------------
  def render_main_page (self):
    ui.colors(primary='#3b82f6')
    ui.query('.nicegui-content').classes('p-0 m-0 w-full h-full')
    ui.dark_mode().enable()
    ui.add_head_html('''
      <style>
        body { background-color: #0f172a; }

        /* Global Selection Enforcer
           NOTE: We exclude interactive elements (buttons, cursor-pointer) to fix touch events on iOS/Mobile.
           Forcing user-select: text on buttons makes the browser interpret taps as text selection attempts.
        */
        .nicegui-content, .nicegui-content * {
            user-select: text;
            -webkit-user-select: text;
        }

        /* Re-disable selection on interactive elements to ensure click events fire correctly */
        button, .q-btn, .cursor-pointer, .cursor-pointer * {
           cursor: pointer;
           user-select: none !important;
           -webkit-user-select: none !important;
        }

        /* Specific class for heavy enforcement if really needed */
        .selectable-text, .selectable-text * {
            user-select: text !important;
            -webkit-user-select: text !important;
        }

        /* Terminal Input Styling */
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
        with ui.row().classes('items-center gap-3 mb-4 cursor-pointer').on('click', self.show_dashboard):
          ui.icon('hub', size='md', color='blue-500')
          ui.label('Lortnoc').classes('text-2xl font-black text-white tracking-wide')

        self.render_sidebar_list()
        ui.separator().classes('border-slate-800')

        with ui.scroll_area().classes('flex-grow w-full pr-2 min-h-0'):
          self.render_logs_panel()

        ui.separator().classes('border-slate-800')
        with ui.row().classes('w-full justify-between items-center'):
          lbl = ui.label().classes('text-xs text-slate-600 font-mono')
          lbl.bind_text_from(
            self.monitor, 'current_version',
            backward=lambda v: f"{v}" if v and v.lower() != "unknown" else "vDEV"
          )
          self.render_system_update_btn()

      # Content
      with ui.column().classes(f'flex-grow h-full overflow-hidden {self.THEME["page_bg"]} p-0 gap-0'):
        self.main_container = ui.column().classes('w-full h-full p-0 gap-0 items-stretch')
        with self.main_container:
          self.render_dashboard_content()

  # --------------------------------------------------------------------------------------------------------------------
  def show_dashboard (self):
    self.current_view = "dashboard"
    self.selected_client_id = None
    if self.main_container:
      self.main_container.clear()
      with self.main_container:
        self.render_dashboard_content()
    self.refresh_sidebar()

  # --------------------------------------------------------------------------------------------------------------------
  def show_client (self, client_id: str):
    self.current_view = "client"
    self.selected_client_id = client_id
    if self.main_container:
      self.main_container.clear()
      with self.main_container:
        self.render_client_content()
    self.refresh_sidebar()

  # --------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_system_update_btn (self):
    if not self.monitor.update_available:
      return
    with ui.button(icon='system_update', on_click=self.monitor.trigger_update).props('round dense color=green'):
      ui.tooltip('Update Available!')

  # --------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_sidebar_list (self):
    ui.label('DEVICES').classes('text-xs font-bold text-slate-500 tracking-wider')
    with ui.column().classes('w-full gap-2'):
      clients = self.monitor.client_manager.get_all_clients()
      if not clients:
        ui.label("Waiting for devices...").classes('text-xs text-slate-600 italic')

      for client in clients:
        active = (self.current_view == "client" and self.selected_client_id == client["id"])
        bg_class = 'bg-slate-800 border-slate-600' if active else 'hover:bg-slate-800 border-transparent'

        card_classes = f'w-full p-3 {bg_class} bg-transparent shadow-none border hover:border-slate-700 transition-all rounded-lg cursor-pointer'
        with ui.card().classes(card_classes).on('click', lambda c=client: self.show_client(c["id"])):
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

  # --------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_logs_panel (self):
    ui.label('SYSTEM ACTIVITY').classes('text-xs font-bold text-slate-500 tracking-wider')
    with ui.column().classes('gap-2 w-full'):
      for log in self.monitor.logs:
        ts_str = log['ts'].strftime('%H:%M:%S')

        # Only show content for SYSTEM, mask client details for security
        if log['client_id'] == "SYSTEM":
          content = log.get('log_msg', log['text'])
          display_str = f"SYSTEM: {content}"
        else:
          # Try to resolve client name from ID
          client_ref = self.monitor.client_manager.get_client(log['client_id'])
          client_name = client_ref.get('name', 'Unknown') if client_ref else log['client_id']
          display_str = f"{client_name}"

        with ui.row().classes('w-full items-start gap-2 text-[11px] font-mono text-slate-400 border-l-2 border-slate-800 pl-2 py-1'):
          ui.label(f"[{ts_str}] {display_str}").classes('break-all leading-tight')

  # --------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_dashboard_content (self):
    clients = self.monitor.client_manager.get_all_clients()
    with ui.scroll_area().classes('w-full h-full p-10'):
      with ui.column().classes('w-full max-w-5xl mx-auto'):
        ui.label('Dashboard Global').classes('text-3xl font-bold tracking-tight text-white mb-4')

        total_online = sum(1 for c in clients if c.get("status") == "online")

        with ui.grid(columns=3).classes('w-full gap-4'):
          with ui.card().classes(self.THEME['card']):
            ui.label('Online Devices').classes('text-sm text-slate-400')
            ui.label(f"{total_online} / {len(clients)}").classes('text-4xl font-bold mt-2')

          avg_cpu = 0
          if clients:
            avg_cpu = sum(c.get("cpu", 0) for c in clients) / len(clients)

          with ui.card().classes(self.THEME['card']):
            ui.label('Avg Flotte CPU').classes('text-sm text-slate-400')
            ui.label(f"{avg_cpu:.1f}%").classes('text-4xl font-bold mt-2 text-blue-400')

        ui.label('Vue d\'ensemble').classes('text-xl font-bold text-white mt-8 mb-4')

        if not clients:
          ui.label("Aucun appareil détecté. En attente de heartbeats...").classes('text-slate-500 italic')

        with ui.grid(columns=3).classes('w-full gap-4'):
          for client in clients:
            self.render_mini_client_card(client)

  # --------------------------------------------------------------------------------------------------------------------
  def render_mini_client_card (self, client):
    status = client.get("status", "offline")
    status_color = 'green-500' if status == 'online' else 'red-500'

    with ui.card().classes(self.THEME['card_hover']).on('click', lambda c=client: self.show_client(c["id"])):
      with ui.row().classes('w-full justify-between items-start'):
        with ui.row().classes('items-center gap-3'):
          with ui.avatar(color='slate-700', text_color='white'):
            ui.icon('dns')
          ui.label(client["name"]).classes('font-bold text-lg')

        ui.element('div').classes(
          f'w-3 h-3 rounded-full bg-{status_color}' +
          (' shadow-[0_0_8px_rgba(34,197,94,0.5)]' if status == 'online' else '')
        )

      if status == "online":
        with ui.row().classes('w-full gap-4 mt-6'):
          self._stat_mini(client, 'CPU', 'cpu')
          self._stat_mini(client, 'RAM', 'ram')
          self._stat_mini(client, 'DISK', 'disk')
          self._stat_mini_text(client, 'IP', 'ip')
      else:
        ui.label('Hors ligne').classes('mt-6 text-slate-500 italic')

  # --------------------------------------------------------------------------------------------------------------------
  def _stat_mini (self, client, label, key):
    with ui.column().classes('gap-1'):
      ui.label(label).classes('text-xs text-slate-400')
      ui.label(f"{client.get(key,0)}%").classes('font-bold')

  # --------------------------------------------------------------------------------------------------------------------
  def _stat_mini_text (self, client, label, key):
    with ui.column().classes('gap-1'):
      ui.label(label).classes('text-xs text-slate-400')
      ui.label(client.get(key, '-')).classes('font-mono text-xs')

  # --------------------------------------------------------------------------------------------------------------------
  def render_client_content (self):
    client = self.monitor.client_manager.get_client(self.selected_client_id)
    if not client:
      ui.label("Client introuvable").classes('text-red-500')
      return

    with ui.column().classes('w-full h-full max-w-5xl mx-auto flex flex-col overflow-hidden no-wrap gap-4 p-6 selectable-text'):
      self.render_client_header(client)

      if client.get("status") == 'online':
        self.render_client_stats(client)

        term_classes = f"{self.THEME['terminal']} w-full flex-1 flex flex-col min-h-0 overflow-hidden p-0 selectable-text"
        with ui.card().classes(term_classes):
          with ui.row().classes('w-full bg-[#2d2d2d] px-4 py-1 items-center gap-2 border-b border-black flex-none'):
            ui.label(f"ssh root@{client.get('ip','remote')}").classes('ml-2 text-xs text-slate-400')

          with ui.column().classes('p-4 w-full gap-1 flex-1 overflow-y-auto bg-[#1e1e1e] terminal-scroll-container selectable-text'):
            self.render_client_terminal()

          with ui.row().classes('w-full bg-[#1e1e1e] pl-4 pr-2 py-2 items-center border-t border-slate-700 flex-none relative z-10'):
            ui.label("root@monitor-cmd:~#").classes('text-green-400 font-bold mr-2')
            cmd_input = ui.input(placeholder='Send raw command...').props(
              'dense borderless autofocus'
            ).classes(
              'flex-grow text-green-400 font-mono tracking-wider cmd-input'
            ).on('keydown.enter', lambda e: self._on_cmd_enter(e, client['id']))

            # History binding
            cmd_input.on('keydown.up', lambda e: self._on_cmd_history(e, cmd_input, client['id'], -1))
            cmd_input.on('keydown.down', lambda e: self._on_cmd_history(e, cmd_input, client['id'], 1))
      else:
        with ui.column().classes('w-full items-center justify-center flex-1 opacity-50 selectable-text'):
          ui.icon('cloud_off', size='160px', color='slate-700')
          ui.label('Device Offline').classes('text-5xl font-bold text-slate-500 mt-8 mb-2')

  # --------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_client_header (self, client):
    status = client.get("status", "offline")
    client_ver = client.get("version", "unknown")
    is_outdated = False
    if self.monitor.latest_version and self.monitor.latest_version != "Unknown" and client_ver != "unknown":
      if self.monitor.latest_version.lstrip('v') != client_ver.lstrip('v'):
        is_outdated = True

    with ui.row().classes('w-full items-center justify-between pb-4 border-b border-slate-700'):
      with ui.row().classes('items-center gap-4 flex-grow'):
        with ui.avatar(color='primary' if status == 'online' else 'grey', text_color='white'):
          ui.icon('dns')

        with ui.column().classes('gap-0 flex-grow'):
          with ui.row().classes('items-center justify-between w-full'):
            ui.label(client["name"]).classes('text-3xl font-bold tracking-tight text-white')

            if status == 'online':
              with ui.row().classes('gap-3'):
                self._action_btn('replay', 'warning', 'Reboot', lambda: self._confirm_and_send(client, 'reboot'))
                self._action_btn('power_off', 'negative', 'Shutdown', lambda: self._confirm_and_send(client, 'shutdown'))
                if is_outdated:
                  with ui.button(icon='system_update', on_click=lambda: self._confirm_and_send(client, 'update')) \
                    .props('flat dense color=green').classes('text-green-400 border border-green-500'):
                    ui.tooltip(f'Update to {self.monitor.latest_version}')
                    ui.label('UPDATE AVAILABLE').classes('ml-2 font-bold')
            else:
              self._action_btn('delete', 'negative', 'Delete Client', lambda: self._confirm_delete(client))

          with ui.row().classes('items-center gap-2'):
            status_class = 'bg-green-500' if status == 'online' else 'bg-red-500'
            ui.element('div').classes(f'w-2 h-2 rounded-full {status_class}')

            version_color = 'text-green-400' if not is_outdated and client_ver != 'unknown' else 'text-slate-500'
            if is_outdated:
              version_color = 'text-amber-500'
            ui.label(client_ver).classes(f'text-xs font-mono {version_color} font-bold mr-2')

            ui.separator().props('vertical').classes('h-4 border-slate-700')

            seen_time = client.get('last_seen')
            if isinstance(seen_time, str):
              try:
                seen_time = datetime.fromisoformat(seen_time)
              except ValueError:
                pass
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
            ui.label(f"{status.upper()} • {client.get('ip', 'N/A')} • {seen_str}").classes('text-sm text-slate-400')

  # --------------------------------------------------------------------------------------------------------------------
  def _action_btn (self, icon, color, tooltip, callback):
    ui.button(icon=icon, color=color, on_click=callback).props('flat round size=md').tooltip(tooltip)

  # --------------------------------------------------------------------------------------------------------------------
  def _confirm_delete (self, client):
    with ui.dialog() as dialog:
      with ui.card().classes('bg-slate-800 text-white border border-slate-600'):
        ui.label(f"Delete '{client['name']}'?").classes('text-lg font-bold text-red-500')
        ui.label("This will remove the client from the list.").classes('text-slate-300')
        with ui.row().classes('w-full justify-end mt-4'):
          ui.button('Cancel', on_click=dialog.close).props('flat text-color=white')
          ui.button('DELETE', color='negative', on_click=lambda: [
            self.monitor.delete_client(client['id']),
            dialog.close()
          ])

    dialog.open()

  # --------------------------------------------------------------------------------------------------------------------
  def _confirm_and_send (self, client, action):
    with ui.dialog() as dialog:
      with ui.card().classes('bg-slate-800 text-white border border-slate-600'):
        ui.label(f"Execute '{action}'?").classes('text-lg font-bold')
        ui.label(f"Do you really want to {action} {client['name']}?").classes('text-slate-300')
        with ui.row().classes('w-full justify-end mt-4'):
          ui.button('Cancel', on_click=dialog.close).props('flat text-color=white')
          ui.button('CONFIRM', color='red' if action in ['reboot', 'shutdown'] else 'primary',
            on_click=lambda: [self.monitor.send_command(client['id'], action), dialog.close()])
    dialog.open()

  # --------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_client_stats (self, client):
    def sizeof_fmt(num):
      for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(num) < 1024.0:
          return f"{num:3.1f} {unit}"
        num /= 1024.0
      return f"{num:.1f} TB"

    with ui.grid(columns=6).classes('w-full gap-2'):
      cpu = client.get("cpu", 0)
      self._stat_card_big('CPU', f"{cpu}%", 'memory', 'blue', cpu / 100)
      ram = client.get("ram", 0)
      self._stat_card_big('RAM', f"{ram}%", 'sd_storage', 'purple', ram / 100)
      disk = client.get("disk", 0)
      self._stat_card_big('Disk', f"{disk}%", 'storage', 'amber', disk / 100)
      temp = client.get("temp", 0)
      self._stat_card_big('Temp', f"{temp}°C", 'thermostat', 'red', temp / 85)
      net_sent = sizeof_fmt(client.get("net_sent", 0))
      self._stat_card_big('Up', net_sent, 'upload', 'cyan')
      net_recv = sizeof_fmt(client.get("net_recv", 0))
      self._stat_card_big('Down', net_recv, 'download', 'cyan')

  # --------------------------------------------------------------------------------------------------------------------
  def _stat_card_big (self, title, value, icon, color_name, progress=None):
    with ui.card().classes(self.THEME['card'].replace('p-4', 'p-2').replace('shadow-lg', 'shadow-md')):
      with ui.row().classes('justify-between w-full items-center mb-0 gap-1 no-wrap'):
        ui.label(title).classes('text-[10px] text-slate-400 font-bold uppercase truncate')
        ui.icon(icon, color=f'{color_name}-400', size='xs')
      ui.label(value).classes('text-base font-bold mb-0 leading-tight truncate')
      if progress is not None:
        ui.linear_progress(progress, show_value=False).props(
          f'size=3px color={color_name}-400 track-color={color_name}-900'
        ).classes('rounded-full mt-1')

  # --------------------------------------------------------------------------------------------------------------------
  @ui.refreshable
  def render_client_terminal (self):
    try:
      relevant_logs = [l for l in self.monitor.logs if self.selected_client_id and l.get('client_id') == self.selected_client_id]
      if not relevant_logs:
        ui.label("No logs available...").classes("text-slate-500 italic")
        return

      for log in relevant_logs:
        ts_str = log['ts'].strftime('%H:%M:%S')
        raw_text = str(log.get('text', ''))
        lid = log.get('id')
        style_class = 'font-mono text-[10px] text-slate-500 italic'
        prefix = f"[{ts_str}] "

        if log.get('is_user_input'):
          style_class = 'font-mono text-xs text-green-400 font-bold mt-1'
        elif log.get('is_output'):
          style_class = 'font-mono text-xs text-slate-300 whitespace-pre-wrap break-all ml-2'
          prefix = ""

        limit = 1000
        display_text = raw_text
        truncated = False
        if len(raw_text) > limit:
          display_text = raw_text[:limit] + "\n... [TRUNCATED]"
          truncated = True

        with ui.column().classes('gap-0 items-start'):
          ui.label(prefix + display_text).classes(style_class)
          if truncated and lid:
            btn = ui.button('View Full', icon='visibility', on_click=lambda i=lid: self._show_full_log(i))
            btn.props('flat dense size=sm color=warning').classes('text-xs ml-2')

    except Exception as e:
      ui.label(f"RENDER ERROR: {e}").classes('text-red-500 font-bold')
    ui.run_javascript("var el = document.querySelector('.terminal-scroll-container'); if(el) el.scrollTop = el.scrollHeight;")

  # --------------------------------------------------------------------------------------------------------------------
  def _show_full_log (self, log_id):
    log = next((l for l in self.monitor.logs if l.get('id') == log_id), None)
    content = log['text'] if log else "Log entry not found / expired."
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-6xl h-[90vh] bg-slate-900 border border-slate-700 p-0 flex flex-col'):
      with ui.row().classes('w-full items-center justify-between border-b border-slate-700 p-4 bg-slate-950'):
        ui.label('Full Command Output').classes('text-lg font-bold text-white')
        ui.button(icon='close', on_click=dialog.close).props('flat round dense color=white')
      with ui.scroll_area().classes('w-full flex-grow bg-[#1e1e1e] p-4'):
        ui.label(content).classes('font-mono text-xs text-slate-300 whitespace-pre-wrap break-all')
    dialog.open()

  # --------------------------------------------------------------------------------------------------------------------
  def _on_cmd_enter (self, e, client_id):
    val = e.sender.value
    if val:
      self.monitor.send_command(client_id, "exec", [val])
      e.sender.value = ""

      # Add to history
      if client_id not in self.cmd_history:
        self.cmd_history[client_id] = []

      # Avoid duplicate consecutive entries
      if not self.cmd_history[client_id] or self.cmd_history[client_id][-1] != val:
        self.cmd_history[client_id].append(val)

      # Reset index
      self.cmd_history_idx[client_id] = len(self.cmd_history[client_id])

  # --------------------------------------------------------------------------------------------------------------------
  def _on_cmd_history (self, _e, input_el, client_id, direction):
    """
    Handles Up/Down arrow for command history.
    direction: -1 (up/back), 1 (down/forward)
    """
    hist = self.cmd_history.get(client_id, [])
    if not hist:
      return

    idx = self.cmd_history_idx.get(client_id, len(hist))

    # Calculate new index
    new_idx = idx + direction

    # Boundary checks
    if new_idx < 0:
      new_idx = 0
    elif new_idx > len(hist):
      new_idx = len(hist)

    self.cmd_history_idx[client_id] = new_idx

    if 0 <= new_idx < len(hist):
      input_el.value = hist[new_idx]
    else:
      input_el.value = "" # Clear if moving past last item (new command)

  # Refresh helpers
  def refresh_sidebar(self):
    self.render_sidebar_list.refresh()
  def refresh_logs(self):
    self.render_logs_panel.refresh()
  def refresh_dashboard(self):
    self.render_dashboard_content.refresh()
  def refresh_client_view(self):
    if self.selected_client_id:
      client = self.monitor.client_manager.get_client(self.selected_client_id)
      if client:
        self.render_client_header.refresh(client)
        self.render_client_stats.refresh(client)
  def refresh_terminal(self):
    self.render_client_terminal.refresh()
