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
from typing import Any
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import RedirectResponse


# C L A S S ############################################################################################################
class AuthMiddleware(BaseHTTPMiddleware):
  """
  Simple Middleware to protect routes with a password.
  """

  # --------------------------------------------------------------------------------------------------------------------
  def __init__ (self, _app_instance, _monitor_app) -> None:
    super().__init__(_app_instance)
    self.monitor_app = _monitor_app

  # --------------------------------------------------------------------------------------------------------------------
  async def dispatch (self, _request: Request, _call_next) -> Any:
    """ Middleware entry point."""

    path = _request.url.path
    # Whitelist paths
    if path.startswith('/_nicegui') or \
      path.startswith('/static') or \
      path == '/login':
      return await _call_next(_request)

    # Check session cookie
    session_token = _request.cookies.get('auth_token')
    if session_token and session_token in self.monitor_app.auth_sessions:
      return await _call_next(_request)

    # Redirect to login
    return RedirectResponse('/login')
