.PHONY: init

SHELL := /bin/bash

SERVICE_NAME=virtual-lab-manager

define HELPTEXT
	Usage: make COMMAND
	commands for managing the project
	
	Commands:
		dev			Run development api server.
		init		Run project with .env.local file (for local development)
		init-ci		Run project without env file (for CI/CD environments)
		kill		Kill project containers (with .env.local)
		kill-ci		Kill project containers (without env file)
		build		Build docker image
		format          Check formatting of files and fixes any formatting issues
		format-check    Only check formatting of files but do not modify them to fix formatting issues 
		lint            Fix linting issues in files, if any
		lint-check      Check linting issues in files but do not modify them to fix linting issues
		style-check     Run formatting, and linting
		type-check      Run static type checks
		test            Run tests
		init-db         Create & seed db tables
		check-db-schema Checks if db schema change requires a migration. Note: Not all changes can be checked here.

endef
export HELPTEXT

define load_env
	# all the variables in the included file must be prefixed with export
	$(eval ENV_FILE := .env.$(1))
	@echo "Loading env from $(ENV_FILE)"
	$(eval include $(ENV_FILE))
endef

help:
	@echo "$$HELPTEXT"

dev:
	poetry run uvicorn virtual_labs.api:app --reload

init:
	./dev-init.sh --env-file ./.env.local

init-ci:
	./dev-init.sh

kill: 
	docker compose --env-file ./.env.local -f docker-compose.yml -p vlm-project down --remove-orphans --volumes

kill-ci:
	docker compose -f docker-compose.ci.yml -p vlm-project down --remove-orphans --volumes

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

style-check:
	poetry run pre-commit run --all-files --config ./.pre-commit-config-ci.yaml

type-check:
	poetry run mypy . --strict

test:
	poetry run populate-tiers --test
	poetry run pytest --cov=virtual_labs

init-db:
	poetry run alembic upgrade head

check-db-schema:
	poetry run alembic check

migration: MESSAGE ?= vlm migration
migration:  ## Create or update the alembic migration
	@$(call load_env,local)
	poetry run alembic upgrade head
	poetry run alembic revision --autogenerate -m "$(MESSAGE)"

tiers:
	poetry run populate-tiers