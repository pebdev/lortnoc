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
from typing import Dict, Any
import json
import logging
import asyncio
import io
import discord

from .transport_interface import Transport


# D E C L A R A T I O N S ##############################################################################################
logger = logging.getLogger(__name__)


# C L A S S ############################################################################################################
class DiscordTransport(Transport):
  """
  Transport implementation using Discord as a message bus.
  Uses a Bot User to send and receive JSON messages in a specific channel.
  """

  # ----------------------------------------------------------------------------------------------------------------------
  def __init__ (self, _token: str, _listening_channels: list[int] = None) -> None:
    if not discord:
      raise ImportError("discord.py is not installed. Please install it with `pip install discord.py`.")

    super().__init__()
    self.token = _token
    self.listening_channels = _listening_channels if _listening_channels else []

    # Configure Intents
    intents = discord.Intents.default()
    intents.message_content = True

    self.client = discord.Client(intents=intents)

    # Bind events
    # Important: The function registered must be named 'on_message' for discord.py to recognize it.
    # Since we can't rename our method 'on_message' (conflict with Transport.on_message attribute),
    # we define a wrapper here.
    async def on_message(msg):
      await self.on_message_event(msg)

    self.client.event(self.on_ready)
    self.client.event(on_message)

    self._connected = False

  # ----------------------------------------------------------------------------------------------------------------------
  async def on_ready (self) -> None:
    logger.info(f"Connected to Discord as {self.client.user} (ID: {self.client.user.id})")
    self._connected = True

  # ----------------------------------------------------------------------------------------------------------------------
  async def on_message_event (self, _message) -> None:
    # Only listen to the specific channel
    if _message.channel.id not in self.listening_channels:
      return

    json_str = await self._extract_json_from_message(_message)
    if not json_str:
      return

    try:
      data = json.loads(json_str)
      # Inject origin channel ID for reply routing
      if isinstance(data, dict):
        data['_origin_channel_id'] = _message.channel.id

      # Pass to callback
      if self.on_message:
        await self.on_message(data)
    except json.JSONDecodeError:
      # Not a JSON message, ignore
      pass

  # ----------------------------------------------------------------------------------------------------------------------
  async def _extract_json_from_message (self, _message) -> str | None:
    """Helper to extract JSON string from message attachments or content."""
    # 1. Handle Attachments (Priority)
    if _message.attachments:
      for attachment in _message.attachments:
        if attachment.filename.endswith('.json') or \
           attachment.content_type.startswith('text') or \
           attachment.content_type.startswith('application/json'):
          try:
            file_content = await attachment.read()
            return file_content.decode('utf-8')
          except Exception as e:
            logger.warning(f"Failed to read attachment {attachment.filename}: {e}")

    # 2. Handle Text Content (Fallback)
    if _message.content:
      content = _message.content.strip()
      if content.startswith("```json") and content.endswith("```"):
        return content[7:-3].strip()
      if content.startswith("```") and content.endswith("```"):
        return content[3:-3].strip()
      return content

    return None

  # ----------------------------------------------------------------------------------------------------------------------
  def add_listening_channel (self, _channel_id: int) -> None:
    """Dynamically adds a channel to the list of watched channels."""
    if _channel_id not in self.listening_channels:
      self.listening_channels.append(_channel_id)
      logger.info(f"Dynamically added channel watching: {_channel_id}")

  # ----------------------------------------------------------------------------------------------------------------------
  async def connect (self) -> None:
    if self._connected:
      return

    logger.info("Connecting to Discord Gateway...")
    # client.start is an async task that runs forever. We spawn it.
    asyncio.create_task(self.client.start(self.token))

  # ----------------------------------------------------------------------------------------------------------------------
  async def disconnect (self) -> None:
    if not self._connected:
      return

    await self.client.close()
    self._connected = False
    logger.info("Disconnected from Discord.")

  # ----------------------------------------------------------------------------------------------------------------------
  async def send (self, _message: Dict[str, Any]) -> None:
    if not self._connected:
      logger.warning("Cannot send message: Transport not connected.")
      return

    # Determine target channel
    target_channel_id = _message.pop("_target_channel_id", None)

    # If no target specified
    if not target_channel_id:
      if self.listening_channels:
        # If explicit target missing, only allow default if there is NO ambiguity (single channel)
        if len(self.listening_channels) == 1:
          target_channel_id = self.listening_channels[0]
        else:
          logger.error("Cannot send: No target channel specified and multiple channels configured. Aborting to prevent routing errors.")
          return
      else:
        logger.error("No target channel specified and no listening channels configured.")
        return

    channel = self.client.get_channel(target_channel_id)
    if not channel:
      # maybe cache not ready, try fetch
      try:
        channel = await self.client.fetch_channel(target_channel_id)
      except Exception as e:
        logger.error(f"Failed to fetch channel {target_channel_id}: {e}")
        return

    if channel:
      payload = json.dumps(_message)
      await self._send_chunked(channel, payload)
    else:
      logger.error(f"Channel {target_channel_id} not found.")

  # ----------------------------------------------------------------------------------------------------------------------
  async def _send_chunked (self, channel, payload: str) -> None:
    """Sends a payload to a Discord channel. Uses file attachment if too large."""
    max_chunk_size = 1900

    # 1. Small Payload: Send as text block (Preferred for speed/readability)
    if len(payload) <= max_chunk_size:
      await channel.send(f"```json\n{payload}\n```")
      return

    # 2. Large Payload: Send as File Attachment
    # Discord supports 10MB+ files, which is plenty for text logs.
    try:
      with io.BytesIO(payload.encode('utf-8')) as f:
        file_obj = discord.File(f, filename="payload.json")
        await channel.send(content="[LARGE PAYLOAD] See attachment.", file=file_obj)
    except Exception as e:
      logger.error(f"Failed to send large payload as attachment: {e}")
      # Last resort error
      error_msg = json.dumps({"type": "log", "message": f"\n[ERROR] Payload too large and attachment failed: {e}"})
      await channel.send(f"```json\n{error_msg}\n```")
