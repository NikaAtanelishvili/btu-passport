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
| Infra and testing | Docker Compose, Mailpit, Makefile, acceptance tests, demo |

**How tasks are written.** Each task has an ID (`BE-07`, `FE-12`, `BC-03`, `IN-02`), the files it creates or changes, what to build, and a *Done when* line with the command or test that proves it. Requirement IDs (FR-xx, NFR-xx) and acceptance scenarios (A1–A16) refer to the Requirements Analysis document.

**Before M0:** export the four documents to Markdown and put them in the repo as `docs/01-requirements.md`, `docs/02-system-design.md`, `docs/03-web-app-design.md` and `docs/plan/*.md` (one file per tab), so every Claude Code session can read them.

## 2. Locked decisions

These are settled; the agent implements them and asks before changing any. Versions: pin the current stable release at scaffold time and record it in the lockfiles — never `latest` tags in Docker.

| Area | Decision |
| --- | --- |
| Frontend | Next.js (App Router) + TypeScript, Tailwind, **stock shadcn/ui components, no custom design work**, react-hook-form + zod, TanStack Query, `viem` + `@noble/hashes` for browser-side verification. Package manager: pnpm |
| Backend | Python 3.12, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2 (sync), Alembic, psycopg 3. Package manager: uv |
| Database | PostgreSQL 16 — the only datastore for data, job queue and sessions |
| Files | MinIO (S3 API) via boto3; PDFs keyed by their SHA-256 |
| PDF | Jinja2 HTML/CSS → WeasyPrint; QR with `segno`; Noto Sans Georgian embedded |
| Login | Passwordless email codes built into FastAPI (hashed 6-digit code, 10-minute expiry, rate limits); SMTP to send, Mailpit in dev. No Keycloak, no OIDC, no staff MFA |
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
│   └── Caddyfile              # demo profile only
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
| `SMTP_HOST`, `SMTP_PORT` | api | `localhost`, `1025` | Mailpit in dev (its inbox UI is on port 8025); the demo uses a real SMTP account |
| `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | api | empty, empty, `passport@btu.test` | Demo: real credentials in .env only, never committed |
| `LOGIN_CODE_TTL_MINUTES`, `LOGIN_CODE_MAX_ATTEMPTS` | api | `10`, `5` | Email-code login (BE-10) |
| `LOGIN_RATE_PER_EMAIL_HOUR`, `LOGIN_RATE_PER_IP_HOUR` | api | `5`, `20` | Code requests allowed per hour; over the limit returns 429 |
| `DEV_LOG_LOGIN_CODES` | api | `true` | Also prints codes to the API log; the API refuses to start with it on unless ENV is dev or test |
| `ALLOWED_EMAIL_DOMAINS` | api | `btu.edu.ge,btu.test,example.org` | For sign-in, admin grants and student registration; checked on the server |
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
| `PASSPORT_TEMPLATE_DIR` | worker | `app/pdf/templates` | Swap in BTU's design without code changes |
| `DEPLOYER_PRIVATE_KEY, ETHERSCAN_API_KEY` | make chain-deploy only | Anvil account 0 key, empty | Never read by any service; Etherscan key only for Sepolia verification |

## 5. Milestones

Build in this order. M0–M5 is the thin end-to-end slice (sprint 1 in the requirements doc): an award made through the API becomes a PDF, gets anchored on Anvil, and verifies by upload in the browser. Add FE-24 (the direct award form) right after M5 so the slice is clickable. M6–M9 add the remaining features; M10 hardens and moves to Sepolia.

&#91;embedded content: milestone dependencies · 11 milestones\]

An arrow means "needs": M4 needs both the contract (M1) and sign-in (M3); M10 needs everything.

| # | Milestone | Tasks | Needs | Done when |
| --- | --- | --- | --- | --- |
| M0 | Scaffold and infra | IN-01 – IN-03, BE-01, FE-01 | — | `make infra-up` shows Postgres, MinIO, Mailpit, Anvil healthy; `make api` and `make web` run; `http://localhost:3000/api/healthz` returns `{"ok":true}` through the proxy |
| M1 | Contract and Merkle | BC-01 – BC-06 | M0 | `forge test` green; `make chain-deploy` writes `contracts/deployments/31337.json`; Python, Solidity and TS Merkle tests all pass the shared vectors |
| M2 | Schema and seed | BE-02 – BE-05 | M0 | `make migrate && make seed` loads 18 students, 18 passports, 16 skills, 3 categories, 60 awards, 8 LEGACY versions; running `make seed` again changes nothing |
| M3 | Authentication | IN-04, BE-10 – BE-14, FE-02 – FE-04 | M2 | Each seeded test user can sign in with a code read from Mailpit; `/api/session` returns the right role; a student gets 403 from `/api/admin/*` (A11) |
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
10. **Keep the plan current:** tick the task in the `docs/plan/` file that defines it when done; add a line under "Deviations" at the bottom of `docs/plan/00-overview.md` for anything built differently, with the reason.

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
- docs/plan/00-overview.md — implementation plan index; one file per area in docs/plan/.
  The plan wins over other docs.
- docs/01-requirements.md, docs/02-system-design.md, docs/03-web-app-design.md — background and IDs.

## Stack (locked)
Next.js App Router + TS + Tailwind + stock shadcn/ui · FastAPI + Pydantic v2 +
SQLAlchemy 2 + Alembic · PostgreSQL 16 · MinIO · WeasyPrint · email-code login (no IdP) ·
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
- Commit per task: "<TASK-ID>: summary". Tick tasks in the docs/plan/ file that defines them.
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

Anything built differently from this plan, with the reason. Tasks are ticked ✅ in the `docs/plan/` file that defines them.

| Task | Deviation | Reason |
| --- | --- | --- |
| IN-01 | MinIO images are `cgr.dev/chainguard/minio` and `cgr.dev/chainguard/minio-client`, pinned by digest | MinIO stopped publishing official Docker images in Oct 2025 and archived the project in 2026; Chainguard's free images are rebuilt from MinIO's source. Still MinIO and the S3 API, so no code changes. Chainguard's free tier only tags `latest`, hence the digest pin |
| IN-01 | Anvil's command is `exec anvil …` and the container runs as root | The image's entrypoint is `/bin/sh -c`; without `exec`, anvil never receives SIGTERM and `--state` is never written. The named volume is root-owned |
| IN-01 | MinIO's healthcheck uses bash `/dev/tcp`; Mailpit's uses its built-in `/mailpit readyz` | The MinIO image ships neither curl nor grep |
| IN-01 | `signer` (profile `app`) reads `../.env` for now | Its own signer-only env file arrives with IN-05 |
| IN-02 | Secrets in `.env.example` are `change-me` placeholders (the `KC_*` variables added in M0 were removed with Keycloak) | Keeps real values out of git |
| BE-01 | No `SessionMiddleware` and no `SESSION_SECRET` (resolved 2026-10-24) | With email-code sign-in there is no OAuth handshake to sign (BE-10) |
| BE-01 | `web3` resolved to 8.0.0 | Current stable at scaffold time; BC-07 is written against the v7 API, so check it then. **Checked in M4 (BC-07): kept 8.0.0, no pin.** Everything the signer uses behaves as in v7 — `Account.from_key`, `sign_transaction(...).raw_transaction`, `send_raw_transaction`, `wait_for_transaction_receipt` / `TimeExhausted`, `get_logs` with topics, `contract.functions…build_transaction/estimate_gas/call`, `max_priority_fee`. Proven by `make test-chain` (signer + A1 on Anvil) and the live M4 runs; the only change was typing (`TxParams`) for strict mypy |
| FE-01 | shadcn `field` instead of `form`; the shadcn style is the current default (`base-nova`, Base UI primitives) | The registry has replaced `form` (FE-01 step 4) |
| IN-01, IN-02, BE-01 | **Superseded on 2026-10-24:** Keycloak (OIDC, staff MFA) is replaced by passwordless email-code sign-in built into FastAPI (BE-10, FE-04, IN-04); Mailpit catches dev mail. The Keycloak service, realm folder, `KC_*`/`OIDC_*`/MFA variables and `authlib`/`itsdangerous` are removed, and there is no `SESSION_SECRET` or `SessionMiddleware` | Product decision: simpler to run and demo, no IdP to configure. Accepted trade-off (IN-04): no second factor for staff — whoever controls an admin's inbox can sign in as that admin |
| docs | `docs/01-requirments.md` renamed to `docs/01-requirements.md` | Match the name CLAUDE.md and §7 use |
| IN-04 | Mailpit pinned to `v1.32.0` by digest and accepts any SMTP login (`MP_SMTP_AUTH_ACCEPT_ANY`, `MP_SMTP_AUTH_ALLOW_INSECURE`) | Lets a dev `.env` set `SMTP_USER`/`SMTP_PASSWORD` the way the demo does without breaking local mail |
| A1 (IN-06, requirements) | Reworded to "an additional award for BTU-T-0021 gives V1 of BTU-AI-000139 with both skills" (test `test_A1_additional_award`) | The seed already gives BTU-T-0021 passport BTU-AI-000139 and an unsynced award (REC-0049); the seed is the source of truth, so the scenario fits it rather than the other way round |
| FE-10 | Public verification page is `/verify`; `/` redirects to it | Matches Web App Design P1 (`/verify`, also the home page); decided 2026-10-24 |
| BE-25 | Plain, clean passport template; the hackathon PDF design (`docs/design/`) is not used and no design-fidelity work is done | Decided 2026-10-24; `PASSPORT_TEMPLATE_DIR` still allows swapping in BTU's design later |
| BC-01 | OpenZeppelin `v5.7.0` and forge-std `v1.17.0` are git submodules pinned to those tags (not vendored by `forge install --no-git`); solc pinned to `0.8.38`. A fresh clone needs `git submodule update --init --recursive` | Keeps library code out of the repo while pinning exact versions in git |
| BC-01, IN-03 | `make chain-abi` writes `shared/PassportRegistry.abi.json` and `web/lib/passport-registry-abi.ts` (the same ABI as a TS `as const` export) | viem infers call and return types only from a const ABI |
| BC-03 | `Deploy.s.sol` writes `chain_id`, `contract_address`, `issuer_address`; `contracts/script/post_deploy.py` (stdlib only) adds `deploy_tx`, `block_number`, `deployed_at` from the receipt and sets `CONTRACT_ADDRESS` in `.env`. `contracts/deployments/31337.json` is git-ignored (Sepolia's will be committed) | A forge script can't see its own mined transaction hash or block while it runs; the local Anvil address depends on local chain state |
| BC-02 | Extra forge test `test_ForeignRegistryRootIsNotInOurs` | Chain side of A7, which IN-06 lists as "+ forge test" |
| IN-03 | `make lint` / `make test` now also run `forge fmt --check` / `forge test`; `make merkle-vectors` and `make chain-deploy` added | Definition of done lists the contract checks; targets were due in M1 |
| BE-02 | The `sessions` model class is `UserSession` (table name unchanged); `LoginCode` lives in `app/models/user.py`; `passport_number_seq` is declared in the model metadata (created by the migration) | Avoids clashing with SQLAlchemy's `Session`; §2 lists no module for `login_codes` |
| BE-03 | `event_rules` also fires BEFORE DELETE: a COMPLETED event can't be hard-deleted in SQL either | Backstop for A16 ("the trigger also blocks it in SQL"); soft delete is already blocked as an UPDATE |
| BE-03 | Test fixture drops and recreates the `public` schema of `passport_test` once per session, then runs `alembic upgrade head`; integration tests use the MinIO bucket `passports-test` | Guarantees every run starts from the real migration; keeps test objects out of the dev bucket |
| BE-04, BE-05 | Minimal `app/services/storage.py` (put/get by key, bucket check) and `app/services/audit.py` (`record()`) exist from M2 | The seed uploads stamps and bootstrap writes an audit row; BE-22 and BE-21 extend these files in M4. `boto3-stubs[s3]` added as a dev dependency for strict mypy |
| BE-04 | Placeholder stamps `seed/stamps/BDG-AI-00{1,2,3}.svg` (plain ringed circles); stored as `stamps/<sha256>.svg`. All seed awards hang off one SEED submission with a fixed UUIDv5. The seed prints six counts; "pending versions created" comes from `issue-pending` (M4) | The hackathon provided no stamp images (decided 2026-10-24); a fixed id keeps re-runs idempotent |
| BE-05 | Bootstrap checks the email against `ALLOWED_EMAIL_DOMAINS` and writes an audit row only when a role is actually granted or changed | Re-running `make bootstrap` should change nothing, like the seed |
| docs | A root `README.md` exists from M2 (setup, chain reset) | Asked for on 2026-10-24; the full README is still IN-07/M10 work |
| BE-10 | Client IP = the **last** `X-Forwarded-For` hop, trusted only when the direct peer is in loopback / RFC 1918 / ULA ranges; `web/proxy.ts` strips client-sent `X-Forwarded-For`/`X-Real-IP` before the `/api` and `/auth` rewrites | Next.js rewrites pass a client's own `X-Forwarded-For` through untouched and add none, so trusting the first hop would let anyone choose the IP used for rate limits. Behind Caddy the last hop is the one Caddy wrote |
| BE-10 | No per-IP limit when the client IP is loopback (dev: everyone arrives via Next.js as 127.0.0.1); the per-email limit always applies | Otherwise the per-IP limit becomes one shared limit of 20 codes an hour for all users, which would break the same-Wi-Fi demo fallback. Real IPs arrive behind Caddy |
| BE-10 | Compose pins the `backend` network to `172.28.0.0/24` (inside the API's trusted-proxy ranges); `tests/integration/test_demo_proxy.py` reads the Compose file, checks Caddy is only on `backend` and the subnet is trusted, and shows the per-IP limit applies (429 on the 21st code) to clients forwarded by a peer from that subnet. Caveat in the Compose file: Caddy must see the real client address — IPv4 published ports keep it, but Docker's userland proxy (IPv6, hairpin) or a tunnel turns it into a gateway address shared by everyone; revisit in IN-05/IN-07 | Docker's auto-assigned subnet (172.18.0.0/16 here) was trusted only by luck of the daemon's default address pools; a host with other pools would make the API ignore X-Forwarded-For and see only Caddy |
| BE-10 | The `DEV_LOG_LOGIN_CODES` check is a `Settings` validator (so the worker and CLI refuse too) and `create_app()` loads settings eagerly; settings errors use `hide_input_in_errors` | Fail fast at startup. Without hiding, pydantic printed every value from `.env`, secrets included |
| BE-10 | Error bodies can carry extra top-level keys (`attempts_left` on `code_invalid`); SMTP failure returns 503 `email_unavailable`; port 465 uses implicit TLS (587 STARTTLS as specified) | FE-04 needs the tries left; the plan names no error for a failed send; common providers offer 465 |
| BE-12 | `GET /api/admin/students` exists from M3 as a read-only first cut of BE-35 (`q`, `program`, `status`, paging; `StudentRow` = profile fields + `passport_id`) | A11 is defined on this route; BE-35 completes it in M6 |
| BE-13 | CSRF check is an app-wide FastAPI dependency rather than ASGI middleware; requests without a live session skip it and reach the route's guard | Reuses the per-request principal and DB session; with no session there's nothing to forge |
| FE-02 | `make types` builds the OpenAPI schema from `app.main` directly instead of fetching it from the running API | Works without `make api` running; output is identical |
| FE-03, FE-04 | `/me` and `/admin` are placeholder pages behind `RequireRole`; the header's Verify link and "Continue as guest" point at `/` (**now `/verify`, since FE-10**) | Sign-in needs somewhere to land before FE-40 / FE-21; `/` becomes the `/verify` alias in FE-10 |
| BE-23 | FR-04's rule "date earned not before the first-issued date" is not checked | As the plan says: an event can happen before a student is registered |
| BE-23 | `create_versions(db, student_ids)` takes no submission argument; "latest version" for `issue-pending` means the highest `version_no` of any status | `passport_versions` has no submission column, so the argument had no use; counting PENDING/RENDERED versions keeps a second `issue-pending` run from duplicating versions that aren't anchored yet |
| BE-23, BE-24 | Validation errors (unknown or archived skill, unknown students, future date, reason length) are all returned at once as 422 `validation_error` with `fields`; `/awards/preview` runs the same validation | One error shape for the form (A9); the preview shows problems before submit |
| BE-25 | Noto Sans (Latin) is bundled next to Noto Sans Georgian (both OFL, in `app/pdf/fonts/` with their licences); the font stack is `"Noto Sans", "Noto Sans Georgian"` | Noto Sans Georgian has only Georgian glyphs — no Latin letters, digits or punctuation — so system fonts would have been used for most text, and the PDF bytes would depend on the machine |
| BE-25 | Rendering sets `SOURCE_DATE_EPOCH` to the version's `issued_at` (process env, restored after) and a content-derived PDF `/ID` | Without HarfBuzz-subset, WeasyPrint subsets fonts with fontTools, which writes the current second into each font's `head` table: two renders a second apart differed. The determinism test now sleeps across a second. The Docker image (IN-05) may have HarfBuzz-subset, so bytes can differ between host and container — each is deterministic, and stored bytes are the source of truth |
| BE-25 | `content_json.issuer` also carries `issuer_address`; the renderer finds a stamp by trying `stamps/<sha>.svg` then `.png` | The last page prints the issuer address; the content JSON has only `stamp_sha256`, and the renderer must not query the database |
| BE-25 | `pdffonts` shows the embedded font as `XXXXXX+Noto-Sans-Georgian` (WeasyPrint's naming); the test ignores dashes | Same font, embedded and subset |
| BE-28 | When retried versions rebuild exactly the leaves of a FAILED batch (same root, which is UNIQUE), that batch row is reset to SUBMITTING and reused; on the final failed attempt the job ends DONE (the failure is on the batch and its versions) instead of FAILED | Otherwise retrying a single-version batch would hit the unique `merkle_root`; the batch, not the job, is where the admin sees the failure |
| BE-26 | Job backoff is 1, 2, 4, 8 … minutes, i.e. `2^(attempts-1)` | The plan writes `2^attempts` but lists 1, 2, 4, 8; the list was followed |
| BE-26 | The loop lives in `worker/loop.py` (`run_once()`, `main()`); `worker/__main__.py` only calls it | Tests and the `run_jobs` fixture run one iteration without the process entry point |
| BE-26 | Stale RUNNING jobs (locked more than 5 minutes ago) are requeued every minute by the worker's timers, not only at start | A worker killed and restarted within 5 minutes would otherwise leave the dead worker's job RUNNING forever — and for ANCHOR_BATCH its dedupe key would block every later anchor job. Found while planning the M4 kill-the-worker check |
| BE-26 | Stale timeout is **60 s without a heartbeat** instead of 5 minutes: while a job runs, a worker thread refreshes its `locked_at` every 15 s (`jobs.heartbeat`), and the per-minute check requeues RUNNING jobs not refreshed for 60 s. A crashed worker's anchor job is back in the queue within ~1–2 minutes (asked for after M4 review, 2026-10-24) | Anchoring takes seconds, so 5 minutes was too slow to recover. A plain 60–90 s lock age would be shorter than the signer's 120 s receipt wait, so a slow but live anchor could be requeued while still running; the heartbeat makes the timeout independent of job length |
| BC-07 | Signer settings add `CONFIRMATIONS` (default 1, in `.env.example`) and `receipt_timeout_seconds` (120); it reads the ABI from `shared/` and starts its `Anchored` log search at `block_number` from `contracts/deployments/<chainId>.json` (0 if missing). Errors use the shared `{error, message, fields}` shape (401 `bad_signature`, 422, 502, 503 `insufficient_funds`) | The plan names `CONFIRMATIONS` without listing it in §4; searching logs from block 0 can hit provider range limits on Sepolia. The signer's Docker image must ship `shared/` and `contracts/deployments/` (IN-05) |
| BE-23, IN-03 | `make issue-pending` added; `make dev` uses honcho (dev dependency) with `Procfile.dev`; README first-time setup now writes `secrets/issuer_key` (Anvil's published key #0) and uses `make dev` | The signer refuses to start without the key file; IN-03 lists `dev` and `issue-pending` for M4 |
| BE-30 – BE-32 | The plan names BE-31 and BE-32 without describing them; built as BE-30 = verification service + chain reader, BE-31 = issuer file (FR-21), BE-32 = the public `/api/verify/*` routes and `/api/stamps/{sha256}` (FR-23, FR-24), following the coverage table in §8 | Keeps one commit per task with a clear scope |
| BE-30 | `NOT_ISSUED_BY_BTU` outranks `NOT_FOUND` (an untrusted registry proves nothing either way). The issuer check also requires the batch's `chain_id`/`contract_address` to equal the configured ones. `version` and `latest_version_no` are returned only when both checks pass (no personal data for a failed verdict); `chain` and `proof` are returned whenever a version was found, so the browser can re-check the failure. A positive `anchoredAt` is cached for good, everything else for 60 s. Chain unreachable → 503 `chain_unavailable` | The plan lists the verdicts but not their order or what a failure returns; there is no verdict for "can't read the chain" |
| BE-32 | `VerifyResult.version` adds `verification_code` | An upload result needs it for "Download the official copy" and `proof.json`, whose routes take the code |
| BE-32 | `/api/stamps/{sha256}` finds the image by storage key (`stamps/<sha>.svg` or `.png`), not through a category row; the loader moved from `app/pdf/render.py` to `storage.get_stamp`. Served with `Cache-Control: immutable` | A stamp an old version printed must still load after its category gets a new one; the API shouldn't import WeasyPrint |
| BE-32 | `build_proof_file()` lives in `app/routers/verify.py` for BE-47 to reuse | `/api/me/versions/{n}/proof.json` serves the same file (M8) |
| FE-12, FE-10 | **API-down fallback (NFR-09):** if `POST /api/verify/hash` fails with 5xx or no answer, `/verify` checks the uploaded file on the chain alone: with the PDF only (works when its batch held just that passport: the leaf is the root) or with the passport's `proof.json` added on the page (also read locally). The issuer file comes through the API, so when it can't be fetched the check falls back to BTU's issuer identity built into the page at build time (`NEXT_PUBLIC_BTU_ISSUER`, set in `next.config.ts` from `CHAIN_ID`, `CONTRACT_ADDRESS`, `ISSUER_ADDRESS`) and says so. The issuer file always wins when reachable | The plan's upload flow needs the API for the proof; the system design's "verify without BTU" needs proof.json. IN-05: the web image must get those three variables at build time |
| FE-12 | The browser reads BTU's registry as named in the issuer file (not the contract in the server's result), uses the hash it computed itself for uploads, and also checks `chainId()` and `revoked(leaf)`; a disagreement with the server's checks is shown | The independent check shouldn't take any of its inputs from the server it is checking |
| FE-11 | Shared `components/error-alert.tsx` (the `ErrorState` alert); `collapsible` added from the shadcn registry for the Proof section; dates show in UTC, as on the PDF | Stock components only |
| BC-06b | `verify_proof.py` is ~85 lines (plan: ~50); adds `--issuer-file <url or path>`; if the issuer file can't be fetched it warns and falls back to proof.json's issuer fields. It also checks the RPC's chain ID and `revoked(leaf)`. Documented in the README | Clear reasons in each NOT VALID line; the override lets tests and offline users point at a saved issuer file |
| BE-30 (tests) | `tests/chain/test_verify.py::test_A7_foreign_issuer` deploys a look-alike registry from Anvil account 1 on every run (extra contracts accumulate on the local chain; harmless). The `ANVIL_KEY_1` constant in `test_signer.py` was not Anvil account 1's key (it derived another address); corrected | A7 needs a real second registry; the old constant only had to be "not the issuer" |
| IN-03 | `make web` execs `next dev --port 3000` directly (no `pnpm dev`); `make stop` added | pnpm's shell wrapper forwards only SIGINT, so honcho's SIGTERM on Ctrl-C left next-server holding :3000 and `web/.next/dev/lock`; the port is pinned to match `PUBLIC_BASE_URL` |
| IN-03 | `api`, `worker` and `signer` recipes `exec` their server too; `make stop` also kills this checkout's stopped `make <dev target>` / `pnpm dev` parents | One rule for every dev target: the signal from Ctrl-C or honcho reaches the server. The leftovers in practice were servers suspended with Ctrl-Z (state T), which keep their port; Ctrl-C (checked through a pty for web → dev → api → web) leaves nothing behind |
| IN-03 | `web`, `api` and `signer` first check their port (`port-free` in the Makefile) and exit with the holder's PID, state and command if it is taken | Next.js silently moved to another port (5300 was seen) when a stale server held 3000, which breaks `PUBLIC_BASE_URL` links; uvicorn already fails on a taken port but doesn't say who holds it |
| BE-35 | `StudentRow` adds `latest_version_no` and `latest_status` (highest version of any status); the list also filters by `education_level`; `has_passport` means "a passport has been issued" (`first_issued_on` set) | FE-22 shows current version and status per row and a level filter, which the API didn't offer; every student has a passport row from registration, so the literal reading would always be true |
| BE-35 | `StudentDetail` shapes: `passport` adds `holder_first_name`/`holder_last_name`; `AwardRow` = skill, category, stamp, date earned, `source` (DIRECT/EVENT/SEED) with event name, legacy record ID, reason, `awarded_by` email; `ParticipationRow` = event, start, event status, deleted, check-in time and method, removed. `warnings` is always present (empty list) | The plan names these rows without fields; the holder names let the page show what was printed |
| BE-35 | Register/edit rules in `app/services/students.py`: Student ID `BTU-T-` + 4 or more digits (`# DEFAULT(Q16)`), names 1–60, email lower-cased and on `ALLOWED_EMAIL_DOMAINS`, program non-blank. 409 `duplicate_student_id` / `duplicate_email` carry `fields` so the message shows under the field; a concurrent duplicate (UNIQUE violation) gives the same 409. PATCH rejects unknown keys (`student_id` → 422); an edit that changes nothing writes no audit row; audit `before`/`after` hold only changed fields | Every form shows server errors under the field; the audit log should show what changed |
| BE-35 | Dashboard: `unregistered_checkins` counts live (not removed) check-ins without a student record in events that are neither deleted nor completed; `recent` = the last 10 ANCHORED versions by `issued_at` | The plan gives the counter names only |
| BE-35 | `GET /api/admin/skills` (read side of BE-50) built now, both admin roles; `SkillRow.category` is an object `{category_id, name, badge_code, stamp_sha256}`. BE-50 adds the writes in M9 | FE-24 needs active skills with their stamp (same approach as BE-12's early students list) |
| BE-35 | The `VersionRow` builder moved to `app/schemas/version.py` (`version_row`), shared by the versions router, student detail and dashboard | One mapping instead of three |
| FE-20 | Super admin group lists Events, Skills, Categories & stamps, Admins & roles, Audit log as "later" without links; the dashboard's Create event is disabled with a tooltip; the dashboard's event counters aren't links yet | Those pages arrive in M7/M9; links would 404 until then |
| FE-20 | `next.config.ts`: `experimental.instantInsights.validationLevel = "manual-warning"` | Every page is a client component fetching its own data (§2 of the Frontend tab), so Next's instant-navigation check logged "Could not validate … instant navigation" on each admin page load; now only segments with `export const instant` are checked (none) |
| FE-22, FE-23 | Program is a text `Input` with a `datalist` of existing programs | "Select with free entry"; stock shadcn has no creatable select |
| FE-23 | The "name differs from the issued passport" alert shows whenever the record's name differs from the printed holder name, not only right after a save; the page polls every 5 s while a version is in progress | The mismatch stays relevant after a reload |
| FE-24 | Confirm is also guarded by a ref (a second click before the re-render sends nothing) and disabled when every row would be skipped; the review step shows "first version (v1)" for a passport with no versions | Belt and braces next to the Idempotency-Key; nothing to issue means nothing to confirm |
| FE-24 | When every selected student already holds the skill, Review stays on the form and the Students field says "<Name> already holds this skill." (or "All selected students already hold this skill."); when only some do, the review step opens with an alert naming how many will be skipped (2026-10-25, after M7 review) | Previously the review opened with Confirm disabled and no reason given |
| FE-24 | "Today" for the date check is computed in Asia/Tbilisi in the browser (`todayInTbilisi`), mirroring the API's `TIMEZONE` default | The date must match the server's rule near midnight; the server still decides (A9) |
| IN-07 (part) | `make demo-users` / `python -m cli demo-users`: SUPER_ADMIN and ADMIN for `DEMO_SUPER_ADMIN_EMAIL` / `DEMO_ADMIN_EMAIL` and a registered student for `DEMO_STUDENT_EMAIL` (`DEMO_STUDENT_ID`, default BTU-T-0900), read from `.env.demo` on top of `.env`; refuses domains not in `ALLOWED_EMAIL_DOMAINS` (extended in `.env.demo` only); idempotent; audit rows with the system as actor. Documented in the README | Asked for on 2026-10-25: demo accounts must be real inboxes |
| BE-44, BE-45 | The plan names BE-44 and BE-45 without describing them; built as BE-44 = the `/api/admin/events` routes (list, create, detail, edit, delete, open/close/reopen, complete, participants) and BE-45 = the presenter QR route `GET .../qr` | One commit per task with a clear scope, as with BE-31/32 |
| BE-40 | Mark as done also has the blocker `DRAFT` (check-in never opened) and needs status CHECKIN_CLOSED; an impossible open/close/reopen is 409 `invalid_transition`. Closing before the window's start also moves `checkin_opens_at` to just before now (the CHECK needs closes > opens). Create/edit check name ≤ 120, description ≤ 500, active skill, end after start, close after open (422 with fields); times must carry a timezone. The tick's open/close are audited with the system as actor; edits audit only changed fields | The plan lists blockers for open check-in only; the table's rules need an error each |
| BE-40 | `EventDetail` adds `skill_locked` and `completed_at`; `counts.total` = live (not removed) participants. `ALREADY_HOLDS` ignores awards made by the event's own Mark as done, so a completed event still shows who was skipped; `CompleteOut.skipped` = participants who already held the skill | The page needs them; after completion every awarded student "holds" the skill |
| BE-42 | A POST that can't check in returns 409 (404 for NOT_FOUND) with `error` = the state in lower case and a top-level `state`; an event id that isn't a UUID gives NOT_FOUND, not 422. The GET also returns `unregistered` and `already_holds_skill`, and the event's description | The page shows the same card for GET and POST failures; the check-in page shows the description (A6) |
| BE-43 | Adding a removed participant restores the row; removing a removed row changes nothing; a linked participant is listed with the student's record name (not the sign-in name). Audit rows `participant.add`/`.remove` have entity `event` with the email in `before`/`after` | A registered newcomer should show their real name in the list and the Mark as done dialog |
| BE-46 | `/api/me/events` (in `app/routers/me.py`) matches rows by email or Student ID and adds `event_date` (the event's local date) and `version_no` | Manual adds use the student's email; dates show as the award's date earned |
| FE-30 | Tabs default to Draft (`?status=` picks one); the dashboard's Unregistered counter links to the Check-in closed tab. While the window fields haven't been touched, a new end time moves them (also on edit), and moved values are saved | The plan gives no default tab; an edit should save what the form shows |
| FE-31 | "Add participant" adds as soon as a student is picked in the `StudentPicker`; Confirm in the Mark as done dialog has a ref guard on top of server idempotency. After completion the page shows the completion block (awarded with new version numbers, skipped) and links to Issuance, not a per-participant issuance status | FE-31 describes the completion block; per-participant status is on Issuance and the student page |
| FE-32 | The presenter view stays under the admin layout but covers the screen (fixed, full size) | No separate layout needed for one page |
| FE-33 | ~~When the token has run out during sign-in (sign-in usually takes over a minute), the page shows "This code has expired. Scan the code on the screen again."~~ **Superseded on 2026-10-25 by the check-in pass below** | Tokens live 30–60 s by design (FR-28, A13); the student is signed in by then, so the next scan checks in |
| BE-42, FE-33 | **Check-in pass (asked for after M7 review, 2026-10-25; carried in a cookie since the M8 review, see the next row, so the `?p=` parts below are superseded).** A signed-out scan calls the new public route `POST /api/checkin/{event_id}/pass {t}`: the event and QR token are checked at scan time; an expired token, a closed/draft event or a missing one gets the usual 409/404 with `state` (the page shows that card without asking for sign-in). Otherwise it returns `{pass, expires_at}`: `<expiry>.<nonce>.<HMAC-SHA256(event qr_secret, "pass:{event_id}:{expiry}:{nonce}")>`, valid 10 minutes for that event only. The page goes to `/login?next=/checkin/{id}?p=<pass>`; check-in GET/POST accept `p` in place of `t`, and back from sign-in the page checks in by itself (no second scan, no second tap). Single use: the nonce is stored in the new column `event_participants.pass_nonce` (migration `0002`) with `UNIQUE (event_id, pass_nonce)`; a used, expired, tampered or other-event pass gives `TOKEN_EXPIRED`. The pass doesn't outlive check-in: a closed event still says `CLOSED`. The holder re-using their own pass gets the usual "already checked in" | Sign-in takes minutes, the token 30–60 s; validating at scan time keeps A13 (a photo of the QR shared a minute later still fails, since it can't get a pass), while the pass can't be bound to a user who isn't signed in yet. It can be forwarded within 10 minutes, but only one person can use it, the same as handing over one's phone |
| BE-42, FE-33 | **Check-in pass in a cookie (asked for after M8 review, 2026-10-25).** `POST /api/checkin/{id}/pass` now returns only `{expires_at}` and sets the pass as cookie `checkin_pass`: HttpOnly, SameSite=Lax, `Path=/api/checkin/{id}` (so it is only sent to that event's check-in API), `Max-Age=600`, Secure when `SESSION_SECURE`. The page then goes to `/login?next=/checkin/{id}` with no token or pass in the URL. GET/POST read the cookie instead of `p` (the `p` parameter is gone; a `?p=` is ignored); `CheckinView.from_pass` tells the page the CONFIRM came from this browser's pass, and the page checks in by itself. A successful POST clears the cookie. A signed-out visit without `t` goes straight to sign-in. Same browser completes after sign-in; another browser with the same link gets `TOKEN_EXPIRED` ("scan again"), checked in tests and live in two headless Chrome profiles | A pass in the URL travelled with any forwarded or shared link; a cookie scoped to the check-in path stays in the browser that scanned |
| FE-34 | The student portal nav shows My passport, My events and "History (later)" (**History linked since FE-41**) | History is FE-41 (M8) |
| IN-07 (part) | Phone test over the LAN: `allowedDevOrigins` in `next.config.ts` = `PUBLIC_BASE_URL`'s host, `make lan-url`, README steps. Checked by loading the app through the LAN IP in headless Chrome (sign-in, check-in, expired QR) | Next.js blocks its dev assets (HMR, chunks) for other origins, so a page opened on a phone never hydrated |
| BE-47 | Logic in a new `app/services/portal.py`, schemas in `app/schemas/me.py`. `VersionSummary.status` is the version status; `verification_code` only for ANCHORED; `added_skills` = skill names this version holds that version `n−1` didn't (all of them for the first version); `superseded` only for an ANCHORED version below the newest ANCHORED one. `SkillOnPassport` = `{name, category, badge_code, stamp_sha256, description, date_earned, source: EVENT/DIRECT/SEED, event_name}`. `skills` come from the current version's frozen `content_json`; with no ANCHORED version they come from the newest LEGACY version's awards; `holder_name` is the frozen holder name, else the student record's. `issuing` = the newest PENDING/RENDERED/ANCHORING version above the current one (FAILED isn't "issuing"). The skill-row query moved from `build_content` into `content.version_skills()` (same output), and the verify router's PDF response into `pdf_response()`, both reused | The plan names these shapes without fields. A legacy-only student would otherwise see "No passport yet" while holding skills; showing a code before anchoring would let a student share one that verifies as NOT_FOUND |
| BE-47 (A8) | `/api/me/*` takes no student, passport or version ID: everything starts from the signed-in student's passport, so another student's version number is just a 404 and IDs added to the query are ignored. Tested in `tests/integration/test_me.py` (`test_A8_scoping` uses the seed: BTU-T-0002 → BTU-AI-000126) | IDOR by construction rather than by an ownership check |
| FE-40 | `CodeDisplay` (`components/code-display.tsx`) is new; the current version card also shows the `/v/<code>` link as text. Copy falls back to an error toast where the clipboard API is unavailable (plain-http LAN address on a phone). A legacy-only passport shows its skills under an alert saying they become verifiable with the next issued version. The QR isn't shown (as planned; it's in the PDF) | The clipboard needs a secure context; S1 asks for the skills a student holds |
| FE-41, FE-34 | Students see their own badge labels (`StudentVersionBadge`): Current, Superseded, "Legacy, not verifiable", Issuing (PENDING/RENDERED/ANCHORING, refetched every 5 s) and Delayed (FAILED). `DataTable` gained an optional `mobileCard`: below `sm`, History and My events show one card per row | At 390 px the tables cut off Status and Download (seen in headless Chrome); admins retry FAILED versions, so a student isn't told "Failed" |
