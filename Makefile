# BTU AI Skills Passport — dev commands (IN-03). Targets are added per milestone.
# First-time setup: cp .env.example .env  →  make infra-up  →  make api / make web

SHELL := /bin/bash

ifneq (,$(wildcard .env))
include .env
export
endif

# Foundry installs to ~/.foundry/bin, which non-login shells often lack.
export PATH := $(HOME)/.foundry/bin:$(PATH)

COMPOSE := docker compose --env-file .env -f infra/docker-compose.yml

.PHONY: infra-up infra-down infra-reset infra-ps api web lint lint-backend lint-web test test-backend test-web

## Infrastructure ------------------------------------------------------------

infra-up:
	$(COMPOSE) up -d --wait db minio keycloak anvil
	$(COMPOSE) up minio-init --exit-code-from minio-init
	$(COMPOSE) ps

infra-down:
	$(COMPOSE) down

infra-reset:
	@read -p "This deletes all local data (Postgres, MinIO, Anvil chain). Type 'yes': " ans && [ "$$ans" = yes ]
	$(COMPOSE) down -v

infra-ps:
	$(COMPOSE) ps -a

## Dev servers (host, hot reload) ---------------------------------------------

api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

web:
	cd web && pnpm dev

## Quality ----------------------------------------------------------------------

lint: lint-backend lint-web

lint-backend:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy

lint-web:
	cd web && pnpm lint && pnpm tsc --noEmit

test: test-backend test-web

test-backend:
	cd backend && uv run pytest -m "not chain"

test-web:
	cd web && pnpm vitest run --passWithNoTests
