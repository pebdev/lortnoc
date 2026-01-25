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
import asyncio
import random
import time
import logging
from typing import Dict, Any
from .transport_interface import Transport


# D E C L A R A T I O N S ##############################################################################################
logger = logging.getLogger(__name__)


# C L A S S ############################################################################################################
class LoopbackTransport(Transport):
  """
  Transport implementation for development and architecture validation.
  Simulates a fleet of Raspberry Pi clients and loops back commands as logs.
  """

  # ----------------------------------------------------------------------------------------------------------------------
  def __init__ (self) -> None:
    super().__init__()
    self.running = False
    self.simulated_clients = [
      {"id": "pi-OS1", "name": "Raspberry OS1", "ip": "192.168.1.10"},
      {"id": "pi-OS2", "name": "Raspberry OS2", "ip": "192.168.1.11"},
      {"id": "pi-OS3", "name": "Raspberry OS3", "ip": "192.168.1.12"},
    ]

  # ----------------------------------------------------------------------------------------------------------------------
  async def connect (self) -> None:
    self.running = True
    logger.info("Simulation started. Generating mock traffic...")
    # Start background task for simulated heartbeats
    asyncio.create_task(self._simulate_heartbeats())

  # ----------------------------------------------------------------------------------------------------------------------
  async def disconnect (self) -> None:
    self.running = False
    logger.info("Simulation stopped.")

  # ----------------------------------------------------------------------------------------------------------------------
  async def send (self, _message: Dict[str, Any]) -> None:
    """
    Simulates sending a command to the client.
    In Loopback mode, we simulate that the client receives the command,
    executes it, and returns a success log.
    """
    logger.info(f">> Command sent: {_message}")

    # Simulate network/processing delay
    await asyncio.sleep(0.5)

    if _message.get("type") == "command":
      target_id = _message.get("target_id")
      action = _message.get("action")

      # Response simulating command execution
      response_log = {
        "type"      : "log",
        "client_id" : target_id,
        "timestamp" : time.time(),
        "level"     : "INFO",
        "message"   : f"Command '{action}' received and executed successfully via Loopback."
      }
      await self._receive(response_log)

  # ----------------------------------------------------------------------------------------------------------------------
  async def _simulate_heartbeats (self) -> None:
    """Simulates sending regular heartbeats from mock clients."""
    while self.running:
      for client in self.simulated_clients:
        # Simulate CPU/RAM variations
        cpu_load  = round(random.uniform(5.0, 60.0), 1)
        ram_usage = round(random.uniform(30.0, 80.0), 1)
        temp      = round(random.uniform(40.0, 65.0), 1)

        # Simulate random outage for testing
        status = "online"
        if client["id"] == "pi-garage" and random.random() > 0.9:
          status = "offline"

        heartbeat = {
          "type"        : "heartbeat",
          "client_id"   : client["id"],
          "client_name" : client["name"],
          "timestamp"   : time.time(),
          "payload"   : {
            "status"  : status,
            "ip"      : client["ip"],
            "cpu"     : cpu_load,
            "ram"     : ram_usage,
            "temp"    : temp
          }
        }

        # Inject message as if coming from network
        if self.on_message:
          # In normal asyncio we await, but here we are in a background loop
          # Ensure _receive handles the async call properly
          await self._receive(heartbeat)

      # Wait before next heartbeat burst
      await asyncio.sleep(5)
