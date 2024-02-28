SHELL := /bin/bash

SERVICE_NAME=virtual-lab-manager

define HELPTEXT
	Usage: make COMMAND
	commands for managing the project
	
	Commands:
		dev	Run development api server.
		init	Run project (keycloak and postgres) containers
		kill	Kill project (keycloak and postgres) containers
		build	Build docker image	

endef
export HELPTEXT

help:
	@echo "$$HELPTEXT"

dev: 
	poetry run uvicorn virtual_labs.api:app --reload

init: 
	docker compose -f docker-compose-dev.yml -p vlm-project up

kill: 
	docker compose -f docker-compose-dev.yml -p vlm-project down --remove-orphans

build: 
	docker build -t $(SERVICE_NAME) . --platform=linux/amd64