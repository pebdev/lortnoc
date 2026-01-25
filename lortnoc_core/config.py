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
import os


# F U N C T I O N S ####################################################################################################
def load_config () -> Dict[str, Any]:
  """
  Loads configuration from config/config.json located at the project root.
  """

  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  config_path = os.path.join(base_dir, 'config', 'config.json')

  if not os.path.exists(config_path):
    print(f"Warning: Config file not found at {config_path}. Returning empty config.")
    return {}

  try:
    with open(config_path, 'r', encoding='utf-8') as f:
      return json.load(f)

  except Exception as e:
    print(f"Error loading config file: {e}")
    return {}
