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

# Ensure execution from the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"


# --- CONFIGURATION ----------------------------------------------------------------------------------------------------
APPLICATION="monitor"

# Resolve Repo Root (Looking for .git or just going up 3 levels)
# Structure Dev: lortnoc_$APPLICATION/tools/docker -> ../../../ (Repo Root)
# Structure Prod: tools/docker -> ../../ (Install Dir)
ROOT_CANDIDATE_2="$(dirname "$(dirname "$SCRIPT_DIR")")"
ROOT_CANDIDATE_3="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

if [ -d "$ROOT_CANDIDATE_2/lortnoc_core" ]; then
  REPO_ROOT="$ROOT_CANDIDATE_2"
  echo "Detected Install Environment (Root: $REPO_ROOT)"
else
  REPO_ROOT="$ROOT_CANDIDATE_3"
  echo "Detected Dev Environment (Root: $REPO_ROOT)"
fi

IMAGE_NAME="lortnoc-$APPLICATION"
CONTAINER_NAME="lortnoc-$APPLICATION-app"

# Data Dir
DATA_DIR="$REPO_ROOT/.data"
CONFIG_DIR="$REPO_ROOT/config"
mkdir -p "$DATA_DIR"

# Mount config volume to ensure configuration is available and up-to-date
DOCKER_ARGS="--rm -p 8080:8080 --name $CONTAINER_NAME -v $CONFIG_DIR:/app/config -v $DATA_DIR:/app/.data -v /etc/localtime:/etc/localtime:ro"


# --- COMMANDS ---------------------------------------------------------------------------------------------------------
case "$1" in
  build)
    # Context must be Repo Root to include sibling core modules
    echo "Building from $REPO_ROOT using Dockerfile in $SCRIPT_DIR"
    docker build -t $IMAGE_NAME -f Dockerfile "$REPO_ROOT"
    ;;
  run)
    docker stop $CONTAINER_NAME 2>/dev/null || true
    # Rename broken container if removal fails
    docker rm $CONTAINER_NAME 2>/dev/null || docker rename $CONTAINER_NAME $CONTAINER_NAME-broken-$(date +%s) 2>/dev/null || true
    docker run -d $DOCKER_ARGS $IMAGE_NAME
    ;;
  run-dev)
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || docker rename $CONTAINER_NAME $CONTAINER_NAME-broken-$(date +%s) 2>/dev/null || true
    docker run -it \
      -v "$REPO_ROOT/lortnoc_$APPLICATION":/app/lortnoc_$APPLICATION \
      -v "$REPO_ROOT/lortnoc_core":/app/lortnoc_core \
      -v "$REPO_ROOT/resources":/app/resources \
      $DOCKER_ARGS \
      $IMAGE_NAME \
      bash
    ;;
  stop)
    docker stop $CONTAINER_NAME 2>/dev/null || true
    ;;
  logs)
    docker logs -f $CONTAINER_NAME
    ;;
  exec)
    docker exec -it $CONTAINER_NAME bash
    ;;
  clean)
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || true
    docker rmi $IMAGE_NAME
    ;;
  pylint)
    "$REPO_ROOT/tools/pylint/run_checks.sh"
    ;;
  *)
    echo "Usage: $0 {build|run|run-dev|stop|logs|exec|clean|pylint}"
    exit 1
    ;;
esac
