# BTU AI Skills Passport — Implementation Plan

Oct 22, 2026 · @Nikoloz Atanelishvili

## 1. How to use this plan

This plan is written for Claude Code to build the whole MVP in 11 milestones (M0–M10), each ending in something runnable and tested. It turns the three earlier documents — Requirements Analysis, System Design and Web App Design — into ordered tasks; when this plan and those documents disagree, this plan wins, because it records the decisions made since (Next.js + PostgreSQL confirmed, stock shadcn, trigger-based audit log).

**Reading order for the agent:** this tab completely → the tab for the milestone's area → the referenced section of the source documents only when a task points to it.

| Tab | What it holds |
| --- | --- |
| Overview (this tab) | Decisions, repo layout, config, milestones, working rules, CLAUDE.md, coverage |
| Backend | FastAPI app, database schema, auth, API contract, issuance services, worker, PDF |
| Blockchain and signer | Solidity contract, Foundry, Merkle spec, signer service, verification |
| Frontend | Next.js app, every page, its components and API calls |
| Infra and testing | Docker Compose, Keycloak realm, Makefile, acceptance tests, demo |

**How tasks are written.** Each task has an ID (`BE-07`, `FE-12`, `BC-03`, `IN-02`), the files it creates or changes, what to build, and a *Done when* line with the command or test that proves it. Requirement IDs (FR-xx, NFR-xx) and acceptance scenarios (A1–A16) refer to the Requirements Analysis document.

**Before M0:** export the four documents to Markdown and put them in the repo as `docs/requirements.md`, `docs/design.md`, `docs/webapp.md`, `docs/plan.md`, so every Claude Code session can read them.

## 2. Locked decisions

These are settled; the agent implements them and asks before changing any. Versions: pin the current stable release at scaffold time and record it in the lockfiles — never `latest` tags in Docker.

| Area | Decision |
| --- | --- |
| Frontend | Next.js (App Router) + TypeScript, Tailwind, **stock shadcn/ui components, no custom design work**, react-hook-form + zod, TanStack Query, `viem` + `@noble/hashes` for browser-side verification. Package manager: pnpm |
| Backend | Python 3.12, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2 (sync), Alembic, psycopg 3, Authlib. Package manager: uv |
| Database | PostgreSQL 16 — the only datastore for data, job queue and sessions |
| Files | MinIO (S3 API) via boto3; PDFs keyed by their SHA-256 |
| PDF | Jinja2 HTML/CSS → WeasyPrint; QR with `segno`; Noto Sans Georgian embedded |
| Login | Keycloak (OIDC authorization code + PKCE, TOTP for staff) in Docker for dev and demo |
| Roles | `SUPER_ADMIN`, `ADMIN` in `user_roles`; students identified by email match; no Auditor role |
| Chain | Solidity + Foundry + OpenZeppelin `Ownable2Step`; Anvil for dev, Sepolia for demo; `web3.py` in the signer |
| Merkle | Sorted-pair keccak256, double-hashed leaves (Blockchain tab, BC-04) — one tree and one transaction per batch |
| Signer | Separate process with the only copy of the issuer key; reached only by the worker over HTTP with an HMAC header |
| Dev routing | Next.js `rewrites` proxy `/api`, `/auth`, `/.well-known` to FastAPI, so the browser sees one origin. Caddy only in the `demo` Compose profile |
| Audit log | Append-only, enforced by a Postgres trigger that rejects UPDATE and DELETE (replaces the DB-role idea in the design) |
| Events | Main award path. One skill per event; QR token rotates every 30 s; Mark as done creates one award submission keyed by the event |
| Scope cuts | No mainnet, no HSM, no real BTU SSO, no award approval flow, no student-facing event browsing |

## 3. Repository layout

One monorepo, four code roots plus infra and docs. Paths below are the contract between tasks: a task that says "in `app/services/issuance.py`" means exactly that file.

```text
btu-passport/
├── CLAUDE.md                  # agent rules (section 7)
├── Makefile                   # all dev commands (Infra tab)
├── .env.example               # every variable, with dev defaults
├── docs/                      # requirements, design, webapp, plan (Markdown)
├── infra/
│   ├── docker-compose.yml
│   ├── Caddyfile              # demo profile only
│   └── keycloak/btu-realm.json
├── seed/
│   ├── test-data.csv          # the hackathon CSV, unchanged
│   └── stamps/                # placeholder stamp SVGs for the 3 categories
├── contracts/                 # Foundry project
│   ├── src/PassportRegistry.sol
│   ├── test/PassportRegistry.t.sol
│   ├── script/Deploy.s.sol
│   └── deployments/           # <chainId>.json written by the deploy script
├── shared/
│   └── merkle-vectors.json    # test vectors used by Python, TS and Solidity tests
├── backend/                   # uv project, one package with three entry points
│   ├── pyproject.toml
│   ├── alembic.ini, migrations/
│   ├── app/                   # FastAPI API        → uvicorn app.main:app
│   │   ├── main.py, config.py, db.py, errors.py
│   │   ├── models/  schemas/  routers/  auth/  services/
│   │   └── pdf/templates/  pdf/fonts/
│   ├── worker/                # background jobs    → python -m worker
│   ├── signer/                # issuer-key service → uvicorn signer.main:app
│   ├── cli/                   # seed, bootstrap    → python -m cli <command>
│   └── tests/
└── web/                       # Next.js app
    ├── app/                   # routes (Frontend tab)
    ├── components/ui/         # shadcn, generated, never hand-edited
    ├── components/            # app components
    ├── lib/                   # api client, generated types, merkle, verify
    └── tests/
```

`signer/` imports nothing from `app/`: it receives a 32-byte root and returns a transaction receipt. It gets its own Docker image and its own env file so the issuer key never sits in the API or worker process.

## 4. Configuration

All settings come from environment variables, read in Python by one `pydantic-settings` class (`app/config.py`, `signer/config.py`) and in Next.js from `process.env`. `.env.example` lists every variable with the dev default below; real secrets go only in `.env` (git-ignored) and, for the issuer key, `secrets/issuer_key` (git-ignored).

| Variable | Used by | Dev default | Notes |
| --- | --- | --- | --- |
| `ENV` | api, worker, signer | `dev` | `dev` · `test` · `demo`; switches cookie security and log format |
| `DATABASE_URL` | api, worker, cli | `postgresql+psycopg://passport:passport@localhost:5432/passport` | Tests use database `passport_test` |
| `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` | api, worker | `http://localhost:9000`, `minio`, `minio-secret`, `passports` |  |
| `PUBLIC_BASE_URL` | api, worker | `http://localhost:3000` | Base of verify links and check-in QR URLs |
| `OIDC_ISSUER` | api | `http://localhost:8080/realms/btu` |  |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | api | `passport-web`, value from the realm file | Confidential client |
| `OIDC_REDIRECT_URI` | api | `http://localhost:3000/auth/callback` | Goes through the Next.js proxy |
| `REQUIRE_MFA_CLAIM` | api | `false` | `true` in demo: admin routes need the ACR level set by Keycloak's OTP step (BE-12) |
| `ALLOWED_EMAIL_DOMAINS` | api | `btu.edu.ge,btu.test,example.org` | For admin grants and student registration |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` | cli | `superadmin@btu.test` | First super admin, created by `cli bootstrap` |
| `SESSION_COOKIE_NAME`, `SESSION_SECURE` | api | `session`, `false` | Demo: `__Host-session`, `true` (needs HTTPS) |
| `SESSION_ABSOLUTE_HOURS`, `ADMIN_IDLE_MINUTES` | api | `8`, `30` | NFR-04 |
| `CHAIN_ID`, `RPC_URL`, `CONTRACT_ADDRESS`, `ISSUER_ADDRESS` | api, worker, signer | `31337`, `http://localhost:8545`, from `contracts/deployments/31337.json`, Anvil account 0 | Served in the issuer file |
| `SIGNER_URL`, `SIGNER_HMAC_SECRET` | worker, signer | `http://localhost:8100`, random 32 bytes | Shared secret, worker → signer only |
| `ISSUER_PRIVATE_KEY_FILE` | signer only | `secrets/issuer_key` | Dev: Anvil account 0's published test key. **Never** a real key in dev |
| `ANCHOR_INTERVAL_SECONDS`, `BATCH_MAX_LEAVES`, `ANCHOR_MAX_ATTEMPTS` | worker | `10`, `1024`, `5` | Production would use `600` |
| `API_ORIGIN` | web (server side) | `http://localhost:8000` | Target of the Next.js rewrites |
| `NEXT_PUBLIC_RPC_URL`, `NEXT_PUBLIC_EXPLORER_TX_URL` | web (browser) | `http://localhost:8545`, empty | Read-only chain access for the verify page; Sepolia uses a public or domain-restricted RPC URL |
| `TIMEZONE` | api, worker | `Asia/Tbilisi` | "Today" for date checks and an event's local date for date earned |
| `MFA_ACR_VALUE` | api | `2` | Only read when REQUIRE\_MFA\_CLAIM is true (IN-04) |
| `PASSPORT_TEMPLATE_DIR` | worker | `app/pdf/templates` | Swap in BTU's design without code changes |
| `DEPLOYER_PRIVATE_KEY, ETHERSCAN_API_KEY` | make chain-deploy only | Anvil account 0 key, empty | Never read by any service; Etherscan key only for Sepolia verification |

## 5. Milestones

Build in this order. M0–M5 is the thin end-to-end slice (sprint 1 in the requirements doc): an award made through the API becomes a PDF, gets anchored on Anvil, and verifies by upload in the browser. Add FE-24 (the direct award form) right after M5 so the slice is clickable. M6–M9 add the remaining features; M10 hardens and moves to Sepolia.

&#91;embedded content: milestone dependencies · 11 milestones\]

An arrow means "needs": M4 needs both the contract (M1) and sign-in (M3); M10 needs everything.

| # | Milestone | Tasks | Needs | Done when |
| --- | --- | --- | --- | --- |
| M0 | Scaffold and infra | IN-01 – IN-03, BE-01, FE-01 | — | `make infra-up` shows Postgres, MinIO, Keycloak, Anvil healthy; `make api` and `make web` run; `http://localhost:3000/api/healthz` returns `{"ok":true}` through the proxy |
| M1 | Contract and Merkle | BC-01 – BC-06 | M0 | `forge test` green; `make chain-deploy` writes `contracts/deployments/31337.json`; Python, Solidity and TS Merkle tests all pass the shared vectors |
| M2 | Schema and seed | BE-02 – BE-05 | M0 | `make migrate && make seed` loads 18 students, 18 passports, 16 skills, 3 categories, 60 awards, 8 LEGACY versions; running `make seed` again changes nothing |
| M3 | Authentication | IN-04, BE-10 – BE-14, FE-02, FE-03 | M2 | Each Keycloak test user can sign in; `/api/session` returns the right role; a student gets 403 from `/api/admin/*` (A11) |
| M4 | Issuance pipeline | BE-20 – BE-29, BC-07 | M1, M3 | A direct award posted to the API reaches ANCHORED on Anvil within 30 s, PDF in MinIO; A1, A2, A3 pass |
| M5 | Verification | BE-30 – BE-32, FE-10 – FE-12 | M4 | Uploading an issued PDF on `/verify` says Valid, an edited copy says Not valid; A4 – A7 pass |
| M6 | Admin core UI | BE-35, FE-20 – FE-25 | M5 | Register a student and award a skill entirely in the UI; failed issuance retried from the UI; A9 passes |
| M7 | Events | BE-40 – BE-46, FE-30 – FE-34 | M6 | A phone on the same network scans the presenter QR and checks in; Mark as done issues versions; A13 – A16 pass |
| M8 | Student portal | BE-47, FE-40, FE-41 | M5 | A student sees only their passport, history and downloads; A8 passes |
| M9 | Super admin | BE-50 – BE-53, FE-50 – FE-53 | M6 | Skills, categories with stamp upload, roles and audit log work; revocation takes effect on the next request (A12) |
| M10 | Hardening and demo | BE-60, BC-08, IN-05 – IN-07, FE-60 | all | All of A1 – A16 pass in the `demo` configuration on Sepolia behind Caddy; README and demo script written |

## 6. Working rules and definition of done

One milestone per session, tests before features for every invariant, and nothing marked done that wasn't run.

### Rules

1. **Work one milestone at a time, in order.** Start by restating the milestone's tasks and their *Done when* lines; finish by running them.
2. **Invariants get a failing test first:** one passport per student, frozen fields, idempotent submissions and Mark as done, version numbering, Merkle proofs, role guards, QR token expiry. Write the test, watch it fail, then implement.
3. **Enforce rules in the database where the plan says so** (UNIQUE, CHECK, triggers), and also in code with a clear error message. Never rely on the frontend for any rule.
4. **Don't change locked decisions** (section 2), table or column names, or route paths without asking. If something in the plan is impossible or wrong, stop and explain, with a proposed fix.
5. **Open questions:** use the default written in the source documents (Q1 – Q18) and leave a `# DEFAULT(Qn)` comment where the choice lives.
6. **Secrets:** never commit `.env`, `secrets/`, or any private key. Only Anvil's published test keys may appear, and only in dev defaults, marked `# DEV ONLY`.
7. **API contract first:** backend schemas in `app/schemas/` are the source of truth; the frontend regenerates TypeScript types with `make types` after any change.
8. **UI:** stock shadcn/ui components and Tailwind defaults only. No custom styling beyond layout (spacing, grid). Every form shows server field errors under the field.
9. **Commits:** one commit per task, message `<task-id>: <summary>` (e.g. `BE-23: issuance service creates pending versions`).
10. **Keep the plan current:** tick the task in `docs/plan.md` when done; add a line under "Deviations" at the bottom of that file for anything built differently, with the reason.

### Definition of done (every task)

- [ ] The task's *Done when* command or test passes locally.
- [ ] `make lint` and `make test` pass (backend: ruff + mypy + pytest; web: eslint + tsc + vitest; contracts: forge fmt --check + forge test).
- [ ] New endpoints appear in the OpenAPI schema with request and response models; `make types` produces no diff.
- [ ] Errors use the shared shape `{ "error": code, "message": text, "fields": {name: message} }`.
- [ ] Every state-changing admin action writes an audit-log row in the same transaction.
- [ ] No TODOs left for behaviour the task promised.

## 7. CLAUDE.md (create in M0)

Copy this into the repo root as `CLAUDE.md`. It keeps every session aligned without re-reading the whole plan.

```markdown
# BTU AI Skills Digital Passport

Issues one persistent, versioned PDF passport per student, anchors each version's
SHA-256 in a Merkle root on an EVM chain, and lets anyone verify it without login.

## Read first
- docs/plan.md — implementation plan (tasks, order, rules). It wins over other docs.
- docs/requirements.md, docs/design.md, docs/webapp.md — background and IDs.

## Stack (locked)
Next.js App Router + TS + Tailwind + stock shadcn/ui · FastAPI + Pydantic v2 +
SQLAlchemy 2 + Alembic · PostgreSQL 16 · MinIO · WeasyPrint · Keycloak (OIDC) ·
Solidity + Foundry · Anvil (dev) / Sepolia (demo) · web3.py signer.

## Commands
make infra-up | infra-down | migrate | seed | bootstrap
make api | worker | signer | web       # dev servers, hot reload
make chain-deploy | types | lint | test

## Rules
- One milestone at a time; run its "Done when" before claiming done.
- Invariants: failing test first. Rules live in the DB (UNIQUE/CHECK/triggers) AND in code.
- Never change table names, route paths or locked decisions without asking.
- Version statuses: LEGACY, PENDING, RENDERED, ANCHORING, ANCHORED, FAILED.
  Only ANCHORED versions are downloadable or verifiable.
- Event statuses: DRAFT, CHECKIN_OPEN, CHECKIN_CLOSED, COMPLETED. No delete once COMPLETED.
- Issued content is frozen in passport_versions.content_json; PDFs are never re-rendered
  after issue and are stored by SHA-256.
- The issuer key lives only in the signer process. Never log it, never import it elsewhere.
- No personal data on-chain. Only Merkle roots.
- Stock shadcn components only; no custom visual design.
- Commit per task: "<TASK-ID>: summary". Tick tasks in docs/plan.md.
- Unclear spec: use the documented default and add a "# DEFAULT(Qn)" comment.
```

## 8. Requirement coverage

Every functional requirement has a task that builds it and a test that proves it.

| Requirements | Built by | Milestone | Proven by |
| --- | --- | --- | --- |
| FR-01, FR-08 (admin access, roles) | BE-12, BE-52, FE-03, FE-52 | M3, M9 | A11, A12 |
| FR-02, FR-10, FR-11 (students, one passport, frozen fields) | BE-02, BE-20, BE-35, FE-22, FE-23 | M2, M6 | A1, unit tests in BE-35 |
| FR-03, FR-04, FR-05 (direct award, validation, bulk) | BE-23, BE-24, FE-24 | M4, M6 | A2, A9 |
| FR-06, FR-22 (status, retry queue) | BE-26 – BE-29, FE-25 | M4, M6 | Signer-down test in BE-28 |
| FR-07, FR-34, FR-35 (catalog, categories, archive) | BE-50, BE-51, FE-50, FE-51 | M9 | Tests in BE-50, BE-51 |
| FR-09 (audit log) | BE-03 trigger, BE-21, BE-53, FE-53 | M2, M4, M9 | A12, trigger test in BE-03 |
| FR-12 – FR-15 (versions, idempotency, latest) | BE-23, BE-27, BE-28 | M4 | A2, A3, A6 |
| FR-16 – FR-18 (PDF, badges, code + QR) | BE-20, BE-25 | M4 | A1, determinism test in BE-25 |
| FR-19 – FR-21 (anchoring, tamper, issuer) | BC-01 – BC-07, BE-28, BE-31 | M1, M4, M5 | A4, A5, A7 |
| FR-23, FR-24 (public verify, superseded) | BE-30, BE-32, FE-10 – FE-12 | M5 | A4 – A6 |
| FR-25 (student access) | BE-47, FE-40, FE-41 | M8 | A8 |
| FR-26 – FR-33 (events, QR, check-in, mark done, my events) | BE-40 – BE-46, FE-30 – FE-34 | M7 | A13 – A16 |
| NFR-01, NFR-02 (batching, bulk) | BE-28 | M4 | Bulk test in IN-06 (A10) |
| NFR-03 – NFR-07 (privacy, security) | BE-10 – BE-14, BE-60, BC-07 | M3, M10 | A11, A12, rate-limit test in BE-60 |
| NFR-12, NFR-13 (Georgian font, determinism) | BE-25 | M4 | Tests in BE-25 |

## Deviations

Anything built differently from this plan, with the reason. (The plan lives in `docs/plan/*.md`, not a single `docs/plan.md`; tasks are ticked ✅ in the tab that defines them.)

| Task | Deviation | Reason |
| --- | --- | --- |
| IN-01 | MinIO images are `cgr.dev/chainguard/minio` and `cgr.dev/chainguard/minio-client`, pinned by digest | MinIO stopped publishing official Docker images in Oct 2025 and archived the project in 2026; Chainguard's free images are rebuilt from MinIO's source. Still MinIO and the S3 API, so no code changes. Chainguard's free tier only tags `latest`, hence the digest pin |
| IN-01 | Anvil's command is `exec anvil …` and the container runs as root | The image's entrypoint is `/bin/sh -c`; without `exec`, anvil never receives SIGTERM and `--state` is never written. The named volume is root-owned |
| IN-01 | Healthchecks for MinIO and Keycloak use bash `/dev/tcp`; Keycloak runs with `KC_HEALTH_ENABLED=true` | Neither image ships curl (MinIO doesn't ship grep either) |
| IN-01 | `signer` (profile `app`) reads `../.env` for now | Its own signer-only env file arrives with IN-05 |
| IN-02 | `.env.example` also has `KC_BOOTSTRAP_ADMIN_USERNAME` / `KC_BOOTSTRAP_ADMIN_PASSWORD`; secrets are `change-me` placeholders | Keycloak needs an admin login; IN-01 names these variables |
| BE-01 | `SessionMiddleware` is not mounted yet | It needs a signing secret that no variable in §4 provides; it gets added with BE-10 (M3) once that variable is decided |
| BE-01 | `web3` resolved to 8.0.0 | Current stable at scaffold time; BC-07 is written against the v7 API, so check it then |
| FE-01 | shadcn `field` instead of `form`; the shadcn style is the current default (`base-nova`, Base UI primitives) | The registry has replaced `form` (FE-01 step 4) |
