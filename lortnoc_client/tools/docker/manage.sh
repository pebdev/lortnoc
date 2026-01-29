#!/bin/bash

# Ensure execution from the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Resolve Repo Root (Assuming manage.sh is in lortnoc_client/tools/docker)
REPO_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

IMAGE_NAME="lortnoc-client"
CONTAINER_NAME="lortnoc-client-app"
CONFIG_DIR="$REPO_ROOT/config"

# Mount config volume to ensure configuration is available and up-to-date
DOCKER_ARGS="--rm --name $CONTAINER_NAME -v $CONFIG_DIR:/app/config"

case "$1" in
  build)
    # Context must be Repo Root
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
    pylint --rcfile=../tools/pylint/.pylintrc sources/*.py ../lortnoc_core/*.py
    ;;
  *)
    echo "Usage: $0 {build|run|run-dev|stop|logs|exec|clean|pylint}"
    exit 1
    ;;
esac
