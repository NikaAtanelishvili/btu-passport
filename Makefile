# BTU AI Skills Passport — dev commands (IN-03). Targets are added per milestone.
# First-time setup: cp .env.example .env  →  make infra-up  →  make chain-deploy  →
# make migrate seed bootstrap  →  make dev

SHELL := /bin/bash

ifneq (,$(wildcard .env))
include .env
export
endif

# Foundry installs to ~/.foundry/bin, which non-login shells often lack.
export PATH := $(HOME)/.foundry/bin:$(PATH)

COMPOSE := docker compose --env-file .env -f infra/docker-compose.yml

.PHONY: infra-up infra-down infra-reset infra-ps api web worker signer dev stop lan-url types migrate migrate-test seed bootstrap demo-users issue-pending chain-deploy chain-abi merkle-vectors \
	lint lint-backend lint-web lint-contracts test test-backend test-web test-contracts test-chain

## Infrastructure ------------------------------------------------------------

infra-up:
	$(COMPOSE) up -d --wait db minio mailpit anvil
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
# Each recipe execs its server, so Ctrl-C (SIGINT from the terminal) and honcho's SIGTERM
# reach the server itself rather than a wrapper shell. Ctrl-Z only suspends: a stopped
# server keeps its port, which port-free then reports.

# Fails when a port is taken instead of letting a server pick another one, and names the
# holder; state T means a suspended (Ctrl-Z) server.
define port-free
@if ss -ltnH "sport = :$(1)" | grep -q .; then \
	pid=$$(ss -ltnpH "sport = :$(1)" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); \
	echo "Port $(1) is already in use$${pid:+ by PID $$pid: $$(ps -o stat=,args= -p $$pid)}" >&2; \
	echo "State T = suspended with Ctrl-Z: run fg and press Ctrl-C, or make stop." >&2; \
	exit 1; \
fi
endef

api:
	$(call port-free,8000)
	cd backend && exec uv run uvicorn app.main:app --reload --port 8000

# Always 3000 to match PUBLIC_BASE_URL. Runs next directly: pnpm's shell wrapper forwards
# only SIGINT, so honcho's SIGTERM left next-server holding the port and web/.next/dev/lock.
web:
	$(call port-free,3000)
	cd web && exec ./node_modules/.bin/next dev --port 3000

# The address a phone on the same Wi-Fi uses (README "Phone test over the LAN").
lan-url:
	@ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($$i == "src") print "http://" $$(i + 1) ":3000"}'

# api, worker, signer and web together (Procfile.dev); Ctrl-C stops all four.
dev:
	backend/.venv/bin/honcho -f Procfile.dev start

# Fallback only, for servers left behind (e.g. suspended with Ctrl-Z): kills this checkout's
# dev processes and their make/pnpm parents, stopped ones too, and removes the Next.js lock.
# Skips its own ancestors, whose command lines may contain the patterns.
stop:
	@self=" $$$$ "; p=$$$$; while [ "$$p" -gt 1 ]; do p=$$(awk '{print $$4}' /proc/$$p/stat); self+="$$p "; done; \
	pids=$$(for p in $$(pgrep -f '^make (api|web|worker|signer|dev)$$|^pnpm dev|honcho -f Procfile[.]dev|next dev|next-server|web/[.]next/dev/build|uvicorn (app|signer)[.]main|python -m worker'); do \
		[[ "$$self" != *" $$p "* && $$(readlink /proc/$$p/cwd 2>/dev/null) == $(CURDIR)* ]] && echo $$p; done); \
	if [ -n "$$pids" ]; then \
		echo "stopping: $$(echo $$pids)"; kill -TERM $$pids 2>/dev/null; kill -CONT $$pids 2>/dev/null; \
		for i in $$(seq 50); do alive=; for p in $$pids; do [ -e /proc/$$p ] && alive=1; done; [ -z "$$alive" ] && break; sleep 0.1; done; \
		kill -KILL $$pids 2>/dev/null; \
	fi; true
	rm -f web/.next/dev/lock

# Background jobs: PDF rendering and anchoring (BE-26).
worker:
	cd backend && exec uv run python -m worker

# Issuer-key service (BC-07). Needs secrets/issuer_key and a deployed registry.
signer:
	$(call port-free,8100)
	cd backend && exec uv run uvicorn signer.main:app --port 8100

## Database ----------------------------------------------------------------------

migrate:
	cd backend && uv run alembic upgrade head

# Same migrations on passport_test (tests also rebuild it themselves).
migrate-test:
	cd backend && DATABASE_URL=$(DATABASE_URL:%/passport=%/passport_test) uv run alembic upgrade head

seed:
	cd backend && uv run python -m cli seed

bootstrap:
	cd backend && uv run python -m cli bootstrap --dev-users

# Demo super admin, admin and student with real inboxes, from DEMO_* in the demo env file,
# which is read on top of .env (its ALLOWED_EMAIL_DOMAINS must include their domains).
DEMO_ENV ?= .env.demo
demo-users:
	@test -f $(DEMO_ENV) || { echo "$(DEMO_ENV) not found; see 'Demo accounts' in README.md" >&2; exit 1; }
	set -a && . $(abspath $(DEMO_ENV)) && set +a && cd backend && uv run python -m cli demo-users

# A new version for every student whose awards aren't all in their latest one (BE-04 step 8).
issue-pending:
	cd backend && uv run python -m cli issue-pending

## Chain -------------------------------------------------------------------------

# Deploys PassportRegistry(ISSUER_ADDRESS) and writes CONTRACT_ADDRESS into .env (BC-03).
# Override for Sepolia: make chain-deploy RPC_URL=... DEPLOY_FLAGS=--verify (M10).
chain-deploy:
	cd contracts && forge script script/Deploy.s.sol --rpc-url $(RPC_URL) --broadcast \
		--private-key $(DEPLOYER_PRIVATE_KEY) $(DEPLOY_FLAGS)
	python3 contracts/script/post_deploy.py $$(cast chain-id --rpc-url $(RPC_URL)) $(RPC_URL)

# ABI for Python (shared/) and the browser (web/lib/, typed `as const` for viem).
chain-abi:
	cd contracts && forge inspect PassportRegistry abi --json > ../shared/PassportRegistry.abi.json
	{ echo '// Generated by `make chain-abi` from contracts/src/PassportRegistry.sol. Do not edit.'; \
	  printf 'export const passportRegistryAbi = %s as const;\n' "$$(cat shared/PassportRegistry.abi.json)"; \
	} > web/lib/passport-registry-abi.ts

merkle-vectors:
	cd backend && uv run python -m cli merkle-vectors

## API types ---------------------------------------------------------------------

# web/lib/api-types.ts from the API's OpenAPI schema (FE-02). Reads the schema from the
# FastAPI app directly, so the API doesn't have to be running.
types:
	@tmp=$$(mktemp --suffix=.json) && \
	(cd backend && uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi()))") > $$tmp && \
	cd web && pnpm exec openapi-typescript $$tmp -o lib/api-types.ts && rm -f $$tmp

## Quality ----------------------------------------------------------------------

lint: lint-backend lint-web lint-contracts

lint-backend:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy

lint-web:
	cd web && pnpm lint && pnpm tsc --noEmit

test: test-backend test-web test-contracts

test-backend:
	cd backend && uv run pytest -m "not chain"

# Needs infra-up and chain-deploy (Anvil with the registry).
test-chain:
	cd backend && uv run pytest -m chain

test-web:
	cd web && pnpm vitest run --passWithNoTests

lint-contracts:
	cd contracts && forge fmt --check

test-contracts:
	cd contracts && forge test
