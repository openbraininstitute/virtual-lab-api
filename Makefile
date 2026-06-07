.PHONY: help install upgrade-deps check-deps pip-audit dev init init-ci destroy destroy-ci build format lint type-check check-all test init-db check-db-schema migration tiers style-check

SHELL := /bin/bash

SERVICE_NAME=virtual-lab-manager

define load_env
	$(eval ENV_FILE := .env.$(1))
	@echo "Loading env from $(ENV_FILE)"
	$(eval include $(ENV_FILE))
endef

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-23s\033[0m %s\n", $$1, $$2}'

install:  ## Install all dependencies
	uv sync

upgrade-deps:  ## Upgrade all dependencies to latest compatible versions
	uv lock --upgrade
	uv sync

check-deps:  ## Check lock file is up to date
	uv lock --check

audit:  ## Run package auditing
	uv run --with pip-audit pip-audit -l

dev:  ## Run development api server
	uv run uvicorn virtual_labs.api:app --reload

init:  ## Run project with .env.local file (for local development)
	./dev-init.sh --env-file ./.env.local

init-ci:  ## Run project without env file (for CI/CD environments)
	./dev-init.sh

destroy:  ## Destroy project containers (with .env.local)
	docker compose --env-file ./.env.local -f docker-compose.yml -p vlm-project down --remove-orphans --volumes

destroy-ci:  ## Destroy project containers (without env file)
	docker compose -f docker-compose.ci.yml -p vlm-project down --remove-orphans --volumes

build:  ## Build the Docker image
	docker build --progress=plain -t $(SERVICE_NAME) . --platform=linux/amd64

format:  ## Run formatters and auto-fix linting issues
	uv run ruff format
	uv run ruff check --fix

lint:  ## Run linters (check only, no modifications)
	uv run ruff format --check
	uv run ruff check

style-check:  ## Run pre-commit style checks
	uv run pre-commit run --all-files --config ./.pre-commit-config-ci.yaml

type-check:  ## Run static type checks
	uv run ty check

check-all: format lint style-check type-check  ## Run format, lint, style-check and type-check

test:  ## Run tests
	uv run populate-tiers --test
	uv run pytest -x

init-db:  ## Create & seed db tables
	uv run alembic upgrade head

check-db-schema:  ## Check if db schema change requires a migration
	uv run alembic check

migration: MESSAGE ?= vlm migration
migration:  ## Create or update the alembic migration
	@$(call load_env,local)
	uv run alembic upgrade head
	uv run alembic revision --autogenerate -m "$(MESSAGE)"

tiers:  ## Populate subscription tiers
	uv run populate-tiers
