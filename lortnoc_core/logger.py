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
from typing import Optional
import logging
import sys


# F U N C T I O N S ####################################################################################################
def setup_logging (_log_file: Optional[str] = None) -> None:
  """
  Configures the root logger with console and optional file handlers.

  :param _log_file: Path to the log file. If None, only console logging is enabled.
  """
  root_logger = logging.getLogger()

  if root_logger.hasHandlers():
    root_logger.handlers.clear()

  # logger configuration
  root_logger.setLevel(logging.INFO)
  formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

  # Console handler
  console_handler = logging.StreamHandler(sys.stdout)
  console_handler.setLevel(logging.INFO)
  console_handler.setFormatter(formatter)
  root_logger.addHandler(console_handler)

  # File handler
  if _log_file:
    try:
      file_handler = logging.FileHandler(_log_file)
      file_handler.setLevel(logging.INFO)
      file_handler.setFormatter(formatter)
      root_logger.addHandler(file_handler)
    except IOError as e:
      print(f"Error setting up log file handler: {e}", file=sys.stderr)
