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
from typing import Dict, Any, Optional
import json
import logging
import asyncio
import io
import discord

from cryptography.fernet import Fernet, InvalidToken

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
  def __init__ (self, _token: str, _listening_channels: Optional[list[int]] = None, _encryption_key: str = None) -> None:
    if not discord:
      raise ImportError("discord.py is not installed. Please install it with `pip install discord.py`.")

    super().__init__()
    self.token = _token
    self._keep_alive = False
    self.listening_channels = _listening_channels if _listening_channels else []

    # Encryption Setup
    if not _encryption_key:
      raise ValueError("Encryption Key is MANDATORY. Please configure 'encryption_key' in your config.")

    try:
      self.cipher_suite = Fernet(_encryption_key.encode())
    except Exception as e:
      logger.critical(f"Invalid Encryption Key: {e}")
      raise ValueError(f"Invalid Encryption Key provided: {e}") from e

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
    """Called when the Discord client is ready."""

    logger.info(f"Connected to Discord as {self.client.user}")
    self._connected = True

  # ----------------------------------------------------------------------------------------------------------------------
  async def on_message_event (self, _message) -> None:
    """Handles incoming Discord messages."""

    # Only listen to the specific channel
    if _message.channel.id not in self.listening_channels:
      return

    payload_str = await self._extract_content_from_message(_message)
    if not payload_str:
      return

    # Decryption Layer
    final_json_str = payload_str

    try:
      # Note: Discord messages are strings, but Fernet needs bytes (base64 token)
      # We assume the content IS the token
      # Strip potential markdown code blocks if any (though usually encrypted blobs are raw)
      clean_token     = payload_str.replace('```', '').strip()
      decrypted_bytes = self.cipher_suite.decrypt(clean_token.encode('utf-8'))
      final_json_str  = decrypted_bytes.decode('utf-8')
    except InvalidToken:
      logger.warning("Received undecryptable message (Invalid Token/Key). Ignoring.")
      return
    except Exception as e:
      logger.error(f"Decryption error: {e}")
      return

    try:
      data = json.loads(final_json_str)
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
  async def _extract_content_from_message (self, _message) -> Optional[str]:
    """Helper to extract raw content (JSON or Encrypted Token) from message."""

    # 1. Handle Attachments (Priority)
    if _message.attachments:
      for attachment in _message.attachments:
        try:
          file_content = await attachment.read()
          return file_content.decode('utf-8')
        except Exception as e:
          logger.warning(f"Failed to read attachment {attachment.filename}: {e}")

    # 2. Handle Text Content
    if _message.content:
      content = _message.content.strip()
      # Strip common markdown wrappers if present
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
    """Establishes connection to Discord."""

    if self._connected:
      return

    logger.info("Connecting to Discord Gateway...")
    self._keep_alive = True
    # client.start is an async task that runs forever. We spawn it via a recovery loop.
    asyncio.create_task(self._connect_loop())

  # ----------------------------------------------------------------------------------------------------------------------
  async def _connect_loop(self) -> None:
    """Internal loop to keep the client connected handling crashes."""
    while self._keep_alive:
      try:
        await self.client.start(self.token)
        if not self._keep_alive:
          break
        logger.warning("Discord client stopped unexpectedly. Restarting in 1s...")
        await asyncio.sleep(1)
      except discord.LoginFailure:
        logger.critical("Invalid Discord Token. Stopping connection loop.")
        self._keep_alive = False
        break
      except Exception as e:
        self._connected = False
        logger.error(f"Discord connection lost/failed: {e}. Retrying in 5s...")
        await asyncio.sleep(5)
        if not self.client.is_closed():
          try:
            await self.client.close()
          except Exception:
            pass

  # ----------------------------------------------------------------------------------------------------------------------
  async def disconnect (self) -> None:
    """Closes connection to Discord."""

    self._keep_alive = False
    await self.client.close()
    self._connected = False
    logger.info("Disconnected from Discord.")

  # ----------------------------------------------------------------------------------------------------------------------
  async def send (self, _message: Dict[str, Any]) -> None:
    """Sends a JSON message to the specified Discord channel."""

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
      payload_str = json.dumps(_message)

      # Encryption Layer (Mandatory)
      # Encrypt the JSON string
      # Result is bytes, decode to string for transport
      encrypted_bytes = self.cipher_suite.encrypt(payload_str.encode('utf-8'))
      payload_str = encrypted_bytes.decode('utf-8')

      await self._send_chunked(channel, payload_str)
    else:
      logger.error(f"Channel {target_channel_id} not found.")

  # ----------------------------------------------------------------------------------------------------------------------
  async def _send_chunked (self, _channel: discord.TextChannel, _payload: str) -> None:
    """Sends a payload to a Discord channel. Uses file attachment if too large."""

    max_chunk_size = 1900

    # 1. Small Payload
    if len(_payload) <= max_chunk_size:
      # If Encrypted, we don't need ```json wrapper, it's just a blob.
      # But keeping code block makes it copy-pasteable monospaced.
      await _channel.send(f"```\n{_payload}\n```")
      return

    # 2. Large Payload: Send as File Attachment
    try:
      with io.BytesIO(_payload.encode('utf-8')) as f:
        # Extension .bin for encrypted to avoid preview parsing attempts
        filename = "payload.bin"

        file_obj = discord.File(f, filename=filename)
        await _channel.send(content="[LARGE PAYLOAD] See attachment.", file=file_obj)
    except Exception as e:
      logger.error(f"Failed to send large payload as attachment: {e}")
      # Last resort error (Attempt to send log about failure) -> Only if not recursive
