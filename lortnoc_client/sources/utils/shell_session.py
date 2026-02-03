# -*- coding: utf-8 -*-
########################################################################################################################
# Project : Lortnoc
# Author  : PEB <pebdev@lavache.com>
# Date    : 03.02.2026
########################################################################################################################
# Copyright (C) 2026
# This file is copyright under the latest version of the EUPL.
# Please see LICENSE file for your rights under this license.
########################################################################################################################

# I M P O R T ##########################################################################################################
import os
import asyncio


# C L A S S ############################################################################################################
class ShellSession:
  """
  Manages a persistent shell session context (CWD, Environment Variables).
  Allows stateful execution of commands like 'cd' or 'export'.
  """

  # --------------------------------------------------------------------------------------------------------------------
  def __init__ (self, _initial_cwd: str = None) -> None:
    self.state = {
      "cwd": _initial_cwd or os.getcwd(),
      "env": os.environ.copy(),
      "aliases": {}
    }

  # --------------------------------------------------------------------------------------------------------------------
  async def execute (self, _command_line: str) -> (str, bool):
    """
    Executes a command within the persistent session context.
    Returns tuple (output, is_error).
    """
    cmd = _command_line.strip()
    if not cmd:
      return "", False

    # 1. Handle Builtins
    # ------------------

    # CD
    if cmd.startswith("cd ") or cmd == "cd":
      target = cmd[3:].strip() if len(cmd) > 2 else "~"
      return self._handle_cd(target)

    # EXPORT
    if cmd.startswith("export "):
      return self._handle_export(cmd[7:])

    # ALIAS
    if cmd.startswith("alias "):
      return self._handle_alias(cmd[6:])

    # SOURCE / .
    if cmd.startswith("source ") or cmd.startswith(". "):
      return await self._handle_source(cmd)

    # 1.5 Expand Aliases
    # Simple expansion of the first token
    parts = cmd.split(" ", 1)
    if parts[0] in self.state["aliases"]:
      expanded = self.state["aliases"][parts[0]]
      # Reconstruct command
      if len(parts) > 1:
        cmd = f"{expanded} {parts[1]}"
      else:
        cmd = expanded

    # 2. Handle System Commands
    # -------------------------
    return await self._run_subprocess(cmd)

  # H E L P E R S ------------------------------------------------------------------------------------------------------
  def _handle_cd (self, _path: str) -> (str, bool):
    """Updates the current working directory in state."""
    try:
      # Resolve path relative to current state cwd
      if _path == "~":
        new_path = os.path.expanduser("~")
      else:
        new_path = os.path.expanduser(_path)
        if not os.path.isabs(new_path):
          new_path = os.path.join(self.state["cwd"], new_path)

      # Canonicalize
      new_path = os.path.abspath(new_path)

      if os.path.isdir(new_path):
        self.state["cwd"] = new_path
        return f"Directory changed to: {self.state['cwd']}", False

      return f"cd: no such file or directory: {_path}", True

    except Exception as e: # pylint: disable=broad-except
      return f"cd: error: {str(e)}", True

  # --------------------------------------------------------------------------------------------------------------------
  def _handle_export (self, _args: str) -> (str, bool):
    """Updates environment variables in state."""
    # Simple parsing for KEY=VALUE
    try:
      if "=" not in _args:
        return "export: usage: export KEY=VALUE", True

      key, value = _args.split("=", 1)
      key = key.strip()
      value = value.strip().strip('"').strip("'")

      self.state["env"][key] = value
      return f"Exported {key}", False
    except Exception as e:
      return f"export: error: {str(e)}", True

  # --------------------------------------------------------------------------------------------------------------------
  def _handle_alias (self, _args: str) -> (str, bool):
    """Updates aliases in state."""
    # Format: alias name='value' or alias name=value
    try:
      if "=" not in _args:
        # List aliases if no assignment (simplification: just return error or list)
        return "alias: usage: alias name='value'", True

      key, value = _args.split("=", 1)
      key = key.strip()
      value = value.strip().strip('"').strip("'")

      self.state["aliases"][key] = value
      return f"Alias set: {key} -> {value}", False
    except Exception as e:
      return f"alias: error: {str(e)}", True

  # --------------------------------------------------------------------------------------------------------------------
  async def _handle_source (self, _cmd: str) -> (str, bool):
    """
    Simulates 'source' by hooking the environment output.
    Runs: source script.sh && echo __LORTNOC_ENV_HOOK__ && env
    """
    delimiter = "__LORTNOC_ENV_HOOK__"
    hooked_cmd = f"{_cmd} && echo '{delimiter}' && env"

    output, is_error = await self._run_subprocess(hooked_cmd)

    if is_error:
      return output, True

    # Parse output to find the env dump
    if delimiter in output:
      parts = output.split(delimiter)
      script_output = parts[0].strip()
      env_dump = parts[1].strip()

      # Parse env dump lines "KEY=VAL"
      count = 0
      for line in env_dump.splitlines():
        if "=" in line:
          try:
            k, v = line.split("=", 1)
            self.state["env"][k] = v
            count += 1
          except Exception: # pylint: disable=broad-except
            pass

      summary = f"{script_output}\n[System] Sourced {count} variables."
      return summary.strip(), False

    return output, False

  # --------------------------------------------------------------------------------------------------------------------
  async def _run_subprocess (self, _cmd: str) -> (str, bool):
    """Runs a standard subprocess with the state's CWD and ENV."""
    try:
      proc = await asyncio.create_subprocess_shell(
        _cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=self.state["cwd"],
        env=self.state["env"]
      )
      stdout, stderr = await proc.communicate()

      output = stdout.decode().strip()
      err_msg = stderr.decode().strip()

      if err_msg:
        output += f"\nSTDERR: {err_msg}"

      return output.strip(), bool(stderr)
    except Exception as e:
      return str(e), True
