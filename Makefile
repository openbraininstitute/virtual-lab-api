SHELL := /bin/bash

SERVICE_NAME=virtual-lab-manager

define HELPTEXT
	Usage: make COMMAND
	commands for managing the project
	
	Commands:
		dev		Run development api server.
		init		Run project (keycloak and postgres) containers
		kill		Kill project (keycloak and postgres) containers
		build		Build docker image
		format          Check formatting of files and fixes any formatting issues
		format-check    Only check formatting of files but do not modify them to fix formatting issues 
		lint            Fix linting issues in files, if any
		lint-check      Check linting issues in files but do not modify them to fix linting issues
		static-checks   Run static type checks, formatting, and linting
		test            Run tests

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

format:
	poetry run ruff format

format-check:
	poetry run ruff format --check

lint:
	poetry run ruff check --fix

lint-check:
	poetry run ruff check

static-checks:
	poetry run pre-commit run --all-files --config ./.pre-commit-config-ci.yaml

test:
	poetry run pytest