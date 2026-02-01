#!/bin/bash

# Ensure execution from the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Resolve Repo Root (Looking for .git or just going up 3 levels)
# Structure Dev: lortnoc_client/tools/docker -> ../../../ (Repo Root)
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

IMAGE_NAME="lortnoc-client"
CONTAINER_NAME="lortnoc-client-app"

# Data Dir (renamed to .data per requirement)
DATA_DIR="$REPO_ROOT/.data"
CONFIG_DIR="$REPO_ROOT/config"
mkdir -p "$DATA_DIR"

# Mount config volume to ensure configuration is available and up-to-date
DOCKER_ARGS="--rm --name $CONTAINER_NAME -v $CONFIG_DIR:/app/config -v $DATA_DIR:/app/data -v /etc/localtime:/etc/localtime:ro"

case "$1" in
  build)
    # Context must be Repo Root to include sibling core modules
    echo "Building from $REPO_ROOT using Dockerfile in $SCRIPT_DIR"
    docker build -t $IMAGE_NAME -f Dockerfile "$REPO_ROOT"
    ;;
  run)
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || true
    docker run -d $DOCKER_ARGS $IMAGE_NAME
    ;;
  run-dev)
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || true
    docker run -it \
      -v "$REPO_ROOT/lortnoc_client":/app/lortnoc_client \
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
    pylint --rcfile="$REPO_ROOT/tools/pylint/.pylintrc" "$REPO_ROOT/lortnoc_client/sources/"*.py "$REPO_ROOT/lortnoc_core/"*.py
    ;;
  *)
    echo "Usage: $0 {build|run|run-dev|stop|logs|exec|clean|pylint}"
    exit 1
    ;;
esac
