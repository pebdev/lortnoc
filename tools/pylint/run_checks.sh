#!/bin/bash
########################################################################################################################
# Project : Lortnoc
# Author  : PEB <pebdev@lavache.com>
# Date    : 24.01.2026
########################################################################################################################
# Copyright (C) 2026
# This file is copyright under the latest version of the EUPL.
# Please see LICENSE file for your rights under this license.
########################################################################################################################
set -e

# Ensure execution from the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")" # tools/pylint/ -> ../../

echo "========================================================================"
echo " Running Static Analysis from $REPO_ROOT"
echo "========================================================================"

TARGETS=()
PYLINTRC="$SCRIPT_DIR/.pylintrc"

if ! command -v pylint &> /dev/null; then
  echo "Error: pylint is not installed directly or not in PATH."
  exit 1
fi

# Determine targets
if [ -d "$REPO_ROOT/lortnoc_monitor/sources" ]; then
  TARGETS+=("$REPO_ROOT/lortnoc_monitor/sources")
fi

if [ -d "$REPO_ROOT/lortnoc_client/sources" ]; then
  TARGETS+=("$REPO_ROOT/lortnoc_client/sources")
fi

if [ -d "$REPO_ROOT/lortnoc_core" ]; then
  TARGETS+=("$REPO_ROOT/lortnoc_core")
fi

# Run pylint
echo " > Checking targets: ${TARGETS[*]}"
find "${TARGETS[@]}" -name "*.py" -print0 | xargs -0 pylint --rcfile="$PYLINTRC" --recursive=y
echo " > Checks Completed."
