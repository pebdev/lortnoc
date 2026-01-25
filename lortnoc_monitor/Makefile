.PHONY: build run stop logs clean pylint

# Docker configuration
IMAGE_NAME 			=	lortnoc-monitor
CONTAINER_NAME 	= lortnoc-monitor-app
DOCKER_ARGS 		= --rm \
									-p 8080:8080 \
									--name $(CONTAINER_NAME)

# Build the Docker image
build:
	docker build -t $(IMAGE_NAME) -f tools/docker/Dockerfile ..

# Run the Docker container
run:
	docker stop $(CONTAINER_NAME) 2>/dev/null || true
	docker rm $(CONTAINER_NAME) 2>/dev/null || docker rename $(CONTAINER_NAME) $(CONTAINER_NAME)-broken-$$(date +%s) 2>/dev/null || true
	docker run -d $(DOCKER_ARGS) $(IMAGE_NAME)

# Run the Docker container in development mode (with source code mounted)
run-dev:
	docker stop $(CONTAINER_NAME) 2>/dev/null || true
	docker rm $(CONTAINER_NAME) 2>/dev/null || docker rename $(CONTAINER_NAME) $(CONTAINER_NAME)-broken-$$(date +%s) 2>/dev/null || true
	docker run -it \
		-v $(shell pwd)/sources:/app/sources \
		-v $(shell pwd)/../lortnoc_core:/app/lortnoc_core \
		-v $(shell pwd)/../config:/app/config \
		$(DOCKER_ARGS) \
		$(IMAGE_NAME) \
		bash

# Stop the Docker container
stop:
	docker stop $(CONTAINER_NAME) 2>/dev/null || true

# Follow the Docker container logs
logs:
	docker logs -f $(CONTAINER_NAME)

# Access the Docker container shell
exec:
	docker exec -it $(CONTAINER_NAME) bash

# Clean the Docker image
clean:
	docker stop $(CONTAINER_NAME) 2>/dev/null || true
	docker rm $(CONTAINER_NAME) 2>/dev/null || true
	docker rmi $(IMAGE_NAME)

# Run pylint on the source code
pylint:
	pylint --rcfile=../tools/pylint/.pylintrc sources/*.py ../lortnoc_core/*.py
