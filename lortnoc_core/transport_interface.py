# -*- coding: utf-8 -*-
########################################################################################################################
# Project : Lortnoc
# Author  : PEB <pebdev@lavache.com>
# Date    : 21.01.2026
########################################################################################################################
# Copyright (C) 2026
# This file is copyright under the latest version of the EUPL.
# Please see LICENSE file for your rights under this license.
########################################################################################################################

# I M P O R T ##########################################################################################################
from abc import ABC, abstractmethod
from typing import Callable, Any, Dict, Optional, Awaitable


# C L A S S ############################################################################################################
class Transport(ABC):
  """
  Abstract interface for message transport.
  This class decouples business logic from the communication medium (Discord, MQTT, Loopback, etc.).
  """

  # ----------------------------------------------------------------------------------------------------------------------
  def __init__ (self) -> None:
    self.on_message: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None

  # ----------------------------------------------------------------------------------------------------------------------
  def set_callback (self, _callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
    """Sets the function to be called when a message is received."""
    self.on_message = _callback

  # ----------------------------------------------------------------------------------------------------------------------
  @abstractmethod
  async def connect (self) -> None:
    """Establishes the connection."""

  # ----------------------------------------------------------------------------------------------------------------------
  @abstractmethod
  async def disconnect (self) -> None:
    """Closes the connection."""

  # ----------------------------------------------------------------------------------------------------------------------
  @abstractmethod
  async def send (self, _message: Dict[str, Any]) -> None:
    """Sends a message."""

  # ----------------------------------------------------------------------------------------------------------------------
  async def _receive (self, _message: Dict[str, Any]) -> None:
    """Internal method to trigger the callback upon message reception."""
    if self.on_message:
      await self.on_message(_message)
