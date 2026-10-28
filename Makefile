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

.PHONY: infra-up infra-down infra-reset infra-ps api web worker signer dev stop lan-url types migrate migrate-test seed bootstrap demo-users issue-pending sheets-check sheets-reset demo-reset export-sheets railway-env chain-deploy-sepolia verify-contract prod-build prod-up prod-down prod-ps prod-logs prod-cli prod-smoke chain-deploy chain-abi merkle-vectors \
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

# Google Sheets (M11): read the Sheet once / write the seed as the three import CSVs.
sheets-check:
	cd backend && uv run python -m cli sheets-check

sheets-reset:
	cd backend && uv run python -m cli sheets-reset

# Back to a clean demo: the Sheet to the seed data (rows below it deleted, the sync columns
# emptied; nothing else touched), then a fresh database. Keeps the chain and object storage:
# the new versions get new codes, so new Merkle roots.
#   make demo-reset              dev: stops the dev servers, drops the dev database
#   make demo-reset STACK=prod   the prod stack (make prod-up): stops its worker, runs
#                                `python -m cli demo-reset --yes` in an api container, restarts it
STACK ?= dev
demo-reset:
ifeq ($(STACK),prod)
	@read -p "This deletes the prod stack's database and every Sheet row below the seed data. Type 'yes': " ans && [ "$$ans" = yes ]
	$(PROD_COMPOSE) stop worker
	$(PROD_COMPOSE) run --rm --no-deps api python -m cli demo-reset --yes; status=$$?; \
		$(PROD_COMPOSE) start worker; exit $$status
else
	@read -p "This deletes the dev database and every Sheet row below the seed data. Type 'yes': " ans && [ "$$ans" = yes ]
	$(MAKE) stop
	$(MAKE) sheets-reset
	$(COMPOSE) exec -T db psql -U passport -d postgres -c 'DROP DATABASE IF EXISTS passport WITH (FORCE)' -c 'CREATE DATABASE passport'
	$(MAKE) migrate seed bootstrap issue-pending
	@echo "demo-reset: done. Run make dev: the worker renders and anchors the seed passports."
endif

export-sheets:
	cd backend && uv run python -m cli export-sheets

# Railway variables per service from .env.demo into secrets/railway/*.env (README "Railway
# deploy"); prints variable names only.
railway-env:
	python3 infra/railway/env_blocks.py $(DEMO_ENV)

## Production stack (M10) ---------------------------------------------------------
# infra/docker-compose.prod.yml with .env.demo: the images Railway runs, with Postgres, MinIO
# and Caddy as containers (README "Local production rehearsal" / "Plain server deploy").
# Local (default): http://localhost:3000. On the server: PROD_MODE=server (HTTPS on 80/443).
# Compose runs with a clean environment, so the dev .env this Makefile exports can't leak
# into the stack's variables.
PROD_MODE ?= local
PROD_COMPOSE = env -i PATH="$(PATH)" HOME="$(HOME)" $(if $(DOCKER_HOST),DOCKER_HOST="$(DOCKER_HOST)") \
	docker compose -f infra/docker-compose.prod.yml --env-file $(DEMO_ENV) \
	$(if $(filter server,$(PROD_MODE)),,--env-file infra/prod-local.env)

prod-build:
	$(PROD_COMPOSE) build

prod-up:
	$(PROD_COMPOSE) up -d --build --wait
	$(PROD_COMPOSE) ps

prod-down:
	$(PROD_COMPOSE) down

prod-ps:
	$(PROD_COMPOSE) ps -a

prod-logs:
	$(PROD_COMPOSE) logs -f --tail 100 $(SERVICE)

# Checks the running stack from outside (infra/smoke.py): health, issuer file, /admin, and
# with SMOKE_COOKIE=name=value or SMOKE_EMAIL + SMOKE_CODE, that sign-in sticks.
# Local: http://localhost:3000; PROD_MODE=server: PUBLIC_BASE_URL from $(DEMO_ENV).
prod-smoke:
	@python3 infra/smoke.py $(if $(filter server,$(PROD_MODE)),$$(grep -E '^PUBLIC_BASE_URL=' $(DEMO_ENV) | cut -d= -f2-),http://localhost:3000)

# One-off CLI command in an api container, e.g. make prod-cli ARGS="demo-users"
prod-cli:
	$(PROD_COMPOSE) run --rm --no-deps api python -m cli $(ARGS)

## Chain -------------------------------------------------------------------------

# Deploys PassportRegistry(ISSUER_ADDRESS) and writes CONTRACT_ADDRESS into .env (BC-03).
# Override for Sepolia: make chain-deploy RPC_URL=... DEPLOY_FLAGS=--verify (M10).
chain-deploy:
	cd contracts && forge script script/Deploy.s.sol --rpc-url $(RPC_URL) --broadcast \
		--private-key $(DEPLOYER_PRIVATE_KEY) $(DEPLOY_FLAGS)
	python3 contracts/script/post_deploy.py $$(cast chain-id --rpc-url $(RPC_URL)) $(RPC_URL)

# BC-08: deploys PassportRegistry to the chain in $(DEMO_ENV) (Sepolia) with the key in its
# ISSUER_PRIVATE_KEY_FILE, after checking the wallet has at least 0.01 ETH. The key and the RPC
# URL travel only in this recipe's environment (never argv, never printed). Gas comes from the
# node (--skip-simulation): forge's local EVM under-estimated Sepolia's contract creation and
# the first deploy ran out of gas. Writes
# contracts/deployments/<chainId>.json (committed) and CONTRACT_ADDRESS into $(DEMO_ENV).
chain-deploy-sepolia:
	@test -f $(DEMO_ENV) || { echo "$(DEMO_ENV) not found" >&2; exit 1; }
	@set -a && . ./$(DEMO_ENV) && set +a && \
	export ETH_RPC_URL="$$RPC_URL" DEMO_RPC_URL="$$RPC_URL" DEPLOYER_PRIVATE_KEY_ENV="$$(tr -d '[:space:]' < "$$ISSUER_PRIVATE_KEY_FILE")" && \
	unset DEPLOYER_PRIVATE_KEY RPC_URL && \
	chain=$$(cast chain-id) && [ "$$chain" = "$$CHAIN_ID" ] || { echo "RPC chain $$chain != CHAIN_ID $$CHAIN_ID" >&2; exit 1; } && \
	bal=$$(cast balance --ether "$$ISSUER_ADDRESS") && echo "issuer $$ISSUER_ADDRESS on chain $$chain: $$bal ETH" && \
	python3 -c "import sys; sys.exit(float('$$bal') < 0.01)" || { echo "not funded (< 0.01 ETH); nothing deployed" >&2; exit 1; } && \
	cd contracts && forge script script/Deploy.s.sol --rpc-url demo --broadcast --skip-simulation $(DEPLOY_FLAGS) && \
	python3 script/post_deploy.py "$$chain" "" $(DEMO_ENV)

# BC-08: publishes PassportRegistry's source on Etherscan for the deployment in $(DEMO_ENV)
# (CONTRACT_ADDRESS, CHAIN_ID, constructor argument ISSUER_ADDRESS). Compiler settings come
# from foundry.toml, as for the deploy. ETHERSCAN_API_KEY is read from the environment by
# forge, never put on the command line or printed.
verify-contract:
	@test -f $(DEMO_ENV) || { echo "$(DEMO_ENV) not found" >&2; exit 1; }
	@set -a && . ./$(DEMO_ENV) && set +a && \
	test -n "$$ETHERSCAN_API_KEY" || { echo "ETHERSCAN_API_KEY is empty in $(DEMO_ENV)" >&2; exit 1; } && \
	unset RPC_URL && cd contracts && \
	forge verify-contract "$$CONTRACT_ADDRESS" src/PassportRegistry.sol:PassportRegistry \
		--chain "$$CHAIN_ID" --constructor-args "$$(cast abi-encode 'constructor(address)' "$$ISSUER_ADDRESS")" \
		--watch && \
	echo "https://sepolia.etherscan.io/address/$$CONTRACT_ADDRESS#code"

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
