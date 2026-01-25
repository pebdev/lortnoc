#!/bin/bash

# Ensure execution from the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

IMAGE_NAME="lortnoc-monitor"
CONTAINER_NAME="lortnoc-monitor-app"
DOCKER_ARGS="--rm -p 8080:8080 --name $CONTAINER_NAME"

case "$1" in
  build)
    docker build -t $IMAGE_NAME -f tools/docker/Dockerfile ..
    ;;
  run)
    docker stop $CONTAINER_NAME 2>/dev/null || true
    # Rename broken container if removal fails (e.g. valid but stopped container that refuses to be removed? usually rm works on stopped)
    # The original makefile had a rename fallback.
    docker rm $CONTAINER_NAME 2>/dev/null || docker rename $CONTAINER_NAME $CONTAINER_NAME-broken-$(date +%s) 2>/dev/null || true
    docker run -d $DOCKER_ARGS $IMAGE_NAME
    ;;
  run-dev)
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || docker rename $CONTAINER_NAME $CONTAINER_NAME-broken-$(date +%s) 2>/dev/null || true
    docker run -it \
      -v $(pwd)/sources:/app/sources \
      -v $(pwd)/../lortnoc_core:/app/lortnoc_core \
      -v $(pwd)/../config:/app/config \
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
