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
import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone


# C L A S S ############################################################################################################
class ClientManager:

  # --------------------------------------------------------------------------------------------------------------------
  def __init__ (self, _persistence_file: str) -> None:
    self.clients_file = _persistence_file
    self.logger = logging.getLogger("LortnocMonitor.ClientManager")
    self.clients: List[Dict[str, Any]] = []

  # --------------------------------------------------------------------------------------------------------------------
  def load_clients (self) -> None:
    """ Loads persisted clients from disk. """

    if not os.path.exists(self.clients_file):
      self.clients = []
      return

    try:
      with open(self.clients_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # Mark all loaded clients as offline initially
        for client in data:
          client['status'] = 'offline'
        self.clients = data
        self.logger.info(f"Loaded {len(data)} known clients from disk.")
    except Exception as e:
      self.logger.error(f"Failed to load persisted clients: {e}")
      self.clients = []

  # --------------------------------------------------------------------------------------------------------------------
  def save_clients (self) -> None:
    """ Saves current clients to disk. """

    try:
      # save to same dir as file
      directory = os.path.dirname(self.clients_file)
      if directory and not os.path.exists(directory):
        os.makedirs(directory)

      with open(self.clients_file, 'w', encoding='utf-8') as f:
        json.dump(self.clients, f, default=str, indent=2)
    except Exception as e:
      self.logger.error(f"Failed to save clients: {e}")

  # --------------------------------------------------------------------------------------------------------------------
  def get_all_clients (self) -> List[Dict[str, Any]]:
    """ Returns the list of all known clients. """
    return self.clients

  # --------------------------------------------------------------------------------------------------------------------
  def get_client (self, _client_id: str) -> Optional[Dict[str, Any]]:
    """ Returns a client by its ID. """
    return next((c for c in self.clients if c.get('id') == _client_id), None)

  # --------------------------------------------------------------------------------------------------------------------
  def remove_client (self, _client_id: str) -> None:
    """ Removes a client by its ID. """
    self.clients = [c for c in self.clients if c.get('id') != _client_id]
    self.save_clients()

  # --------------------------------------------------------------------------------------------------------------------
  def update_client (self, _client_data: Dict[str, Any]) -> None:
    """
    Updates a client or adds it if new.
    _client_data must contain 'id'.
    """

    client_id = _client_data.get('id')
    if not client_id:
      return

    existing = self.get_client(client_id)
    # Use timezone-aware UTC datetime for storage
    _client_data['last_seen'] = datetime.now(timezone.utc).isoformat()

    if existing:
      existing.update(_client_data)
    else:
      self.clients.append(_client_data)
      self.save_clients()
