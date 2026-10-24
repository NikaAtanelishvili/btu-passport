# Infra and testing

## 1. Docker Compose services and profiles

During development only the infrastructure runs in Docker; the API, worker, signer and web app run on the host with hot reload. The `app` and `demo` profiles containerise everything for the demo.

### IN-01 `infra/docker-compose.yml` (M0) ✅

| Service | Image (pin exact tags) | Ports | Profile | Notes |
| --- | --- | --- | --- | --- |
| `db` | `postgres:16` | 5432 | default | User, password and database `passport`; an init script also creates `passport_test`; volume `pgdata`; healthcheck `pg_isready` |
| `minio` | `minio/minio:<release tag>` | 9000, 9001 (console) | default | `server /data --console-address :9001`; volume `miniodata` |
| `minio-init` | `minio/mc:<release tag>` | — | default | One-shot: create the private bucket `passports` |
| `mailpit` | `axllent/mailpit:<tag>` | 8025 (UI), 1025 (SMTP) | default | Dev only: catches all outgoing email; inbox and REST API at `http://localhost:8025` |
| `anvil` | `ghcr.io/foundry-rs/foundry:<tag>` | 8545 | default | `anvil --host 0.0.0.0 --chain-id 31337 --state /data/anvil-state.json`; volume `anvildata` |
| `api` | built from `backend/Dockerfile` | internal 8000 | `app` | `uvicorn app.main:app` |
| `worker` | same image | — | `app` | `python -m worker` |
| `signer` | same image | internal 8100 | `app` | `uvicorn signer.main:app`; the **only** service with the `issuer_key` Docker secret mounted; on a separate network shared only with `worker` |
| `web` | built from `web/Dockerfile` | internal 3000 | `app` | `next build` with `output: "standalone"` |
| `caddy` | `caddy:2` | 80, 443 | `demo` | `infra/Caddyfile` (IN-05) |

Networks: `backend` (db, minio, mailpit, anvil, api, worker, web, caddy) and `signing` (worker, signer, anvil). Only the worker can reach the signer; the API reaches the chain only for read-only calls.

### IN-02 Environment files (M0) ✅

`.env.example` (committed, every variable from Overview §4 with dev defaults), `.env` (git-ignored, copied from the example), `.env.demo` (git-ignored, demo values), `secrets/issuer_key` (git-ignored; in dev it holds Anvil account 0's published test key). `.gitignore` covers `.env`, `.env.demo`, `secrets/`, `infra/*state*.json`.

**Done when (M0):** `make infra-up` starts the default services: db, minio, mailpit and anvil report healthy and minio-init exits 0; MinIO's console shows the `passports` bucket; Mailpit's inbox loads at localhost:8025; `cast block-number --rpc-url http://localhost:8545` answers.

## 2. Sign-in email

### IN-04 Mailpit and SMTP (M3)

**Dev:** the `mailpit` service catches every email the API sends (SMTP on 1025, inbox UI and REST API on 8025), so nobody needs a real mailbox. Unit and integration tests use the `fake_mailer` fixture instead (BE-10); e2e tests read codes from Mailpit's REST API.

**Demo:** point `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` and `SMTP_FROM` at a real sender (BTU mail, a Gmail account with an app password, or a service such as Resend or Mailgun) and set `DEV_LOG_LOGIN_CODES=false`. Send yourself a code before the demo and check it doesn't land in spam.

**No second factor for staff:** whoever controls an admin's inbox can sign in as that admin. Record it under Deviations as an accepted trade-off.

**Test users** (no passwords; each signs in with a code read from Mailpit):

| Email | Name | Role after `cli bootstrap --dev-users` | Used for |
| --- | --- | --- | --- |
| `superadmin@btu.test` | Super Admin | SUPER\_ADMIN | Events, catalog, roles |
| `admin@btu.test` | Admin User | ADMIN | Students, direct awards |
| `btu-t-0002@example.org` | Mariam Beridze | student (seed) | A2, A6, A8 |
| `btu-t-0012@example.org` | Nikoloz Gelashvili | student (seed) | Check-in |
| `btu-t-0021@example.org` | Luka Japaridze | student (seed) | A1, first issued version |
| `newcomer@btu.test` | Nino Newcomer | none (no student record) | A14, Unregistered |

**Done when (M3):** every test user can sign in at `http://localhost:3000/login` with a code read from Mailpit and lands on the right page.

## 3. Makefile targets

### IN-03 `Makefile` (M0, extended as milestones add pieces) ✅ M0 – M2 targets

Every command a developer or the agent needs, so nobody has to remember flags. Targets load `.env` (`include .env` + `export`).

| Target | Runs | Added in |
| --- | --- | --- |
| `infra-up` / `infra-down` / `infra-reset` | `docker compose -f infra/docker-compose.yml up -d` / `down` / `down -v` (wipes data, asks for confirmation) | M0 |
| `api` | `cd backend && uv run uvicorn app.main:app --reload --port 8000` | M0 |
| `web` | `cd web && pnpm dev` | M0 |
| `worker` | `cd backend && uv run python -m worker` | M4 |
| `signer` | `cd backend && uv run uvicorn signer.main:app --port 8100` | M4 |
| `dev` | `api`, `worker`, `signer`, `web` together (e.g. with `honcho` and a `Procfile.dev`) | M4 |
| `migrate` / `migrate-test` | `alembic upgrade head` on `passport` / `passport_test` | M2 |
| `seed` | `python -m cli seed` | M2 |
| `bootstrap` | `python -m cli bootstrap --dev-users` | M2 |
| `issue-pending` | `python -m cli issue-pending` | M4 |
| `chain-deploy` | `forge script … --broadcast` + write `CONTRACT_ADDRESS` to `.env` | M1 |
| `chain-abi` | Export the ABI to `shared/` and `web/lib/` | M1 |
| `merkle-vectors` | `python -m cli merkle-vectors` | M1 |
| `types` | Regenerate `web/lib/api-types.ts` from the running API | M3 |
| `lint` | `ruff check`, `ruff format --check`, `mypy` · `pnpm lint`, `pnpm tsc --noEmit` · `forge fmt --check` | M0 |
| `test` | `pytest -m "not chain"` · `pnpm vitest run` · `forge test` | M0 |
| `test-chain` | `pytest -m chain` (needs `infra-up` and `chain-deploy`) | M4 |
| `e2e` | `pnpm playwright test` (needs `dev` running) | M10 |
| `acceptance` | `test`, `test-chain`, `e2e` in sequence | M10 |
| `demo-up` | `docker compose --profile app --profile demo --env-file .env.demo up -d --build` | M10 |

**First-time setup** (put in the README): `cp .env.example .env` → `make infra-up` → `make chain-deploy` → `make migrate seed bootstrap` → `make dev` → open `http://localhost:3000`.

## 4. Acceptance test matrix A1–A16

### IN-06 Acceptance suite (built up from M3, complete in M10)

Each scenario from the Requirements Analysis becomes at least one automated test, named after it, so `pytest -k A15` runs that scenario. Chain-dependent scenarios also have a fake-signer version that runs in plain `make test`.

| # | Scenario (short) | Test | Layer | Milestone |
| --- | --- | --- | --- | --- |
| A1 | An additional award for BTU-T-0021 (seed passport BTU-AI-000139, no issued version) gives V1 with both skills, one PDF, anchored | `tests/integration/test_issuance.py::test_A1_additional_award` (+ `tests/chain/` variant) | API + worker | M4 |
| A2 | BTU-T-0002 at legacy V1 with 2 pending awards → one new version, same Passport ID, skills in date order | `test_issuance.py::test_A2_issue_pending_one_version` | CLI + worker | M4 |
| A3 | Same Idempotency-Key twice → no duplicate award, version or transaction | `test_awards.py::test_A3_idempotent` | API | M4 |
| A4 | Unmodified PDF uploaded → VALID | `tests/chain/test_verify.py::test_A4_valid` + e2e flow 1 | full | M5 |
| A5 | One byte changed → NOT\_FOUND | `test_verify.py::test_A5_tampered` + e2e flow 1 | full | M5 |
| A6 | Old version's code → SUPERSEDED with the latest number | `test_verify.py::test_A6_superseded` | API | M5 |
| A7 | Root anchored on a second registry owned by Anvil account 1 → NOT\_ISSUED\_BY\_BTU | `tests/chain/test_verify.py::test_A7_foreign_issuer` + forge test | chain | M5 |
| A8 | Student sees only their passport; another's PDF URL → 404 | `test_me.py::test_A8_scoping` | API | M8 |
| A9 | Future date or missing reason → 422 with field errors, nothing saved | `test_awards.py::test_A9_validation` | API (UI checked by hand in M6) | M6 |
| A10 | A newly created skill awarded to all 18 seed students → 18 versions, one Merkle batch | `test_issuance.py::test_A10_bulk_one_batch` | API + worker | M4 |
| A11 | Student → 403 on admin UI and API | `test_auth.py::test_A11_student_forbidden` + e2e flow 3 | API + UI | M3 |
| A12 | Revoked admin's next request → 403, logged | `test_roles.py::test_A12_revocation` | API | M9 (session part in M3) |
| A13 | Token from two windows ago → TOKEN\_EXPIRED | `test_checkin.py::test_A13_expired_token` | API | M7 |
| A14 | Unregistered participant blocks Mark as done until registered or removed | `test_events.py::test_A14_unregistered_blocks` | API | M7 |
| A15 | 20 participants, 2 already hold the skill → 18 awards; second complete creates nothing | `test_events.py::test_A15_complete_idempotent` | API + worker | M7 |
| A16 | Delete a completed event → 409; the trigger also blocks it in SQL | `test_events.py::test_A16_no_delete_completed` | API + DB | M7 |

**Done when (M10):** `make acceptance` passes from a clean checkout following the README's first-time setup.

## 5. Demo preparation and demo script

### IN-05 Containers and Caddy (M10)

- `backend/Dockerfile`: `python:3.12-slim`, install Pango and HarfBuzz runtime libraries and fonts, copy the uv lockfile, `uv sync --frozen --no-dev`, run as a non-root user. One image; `api`, `worker` and `signer` differ only in command, and only `signer` mounts the key secret.
- `web/Dockerfile`: multi-stage Node build, `next build` with `output: "standalone"`, `API_ORIGIN=http://api:8000`.
- `infra/Caddyfile`:

```text
{$DEMO_DOMAIN} {
    handle /api/*         { reverse_proxy api:8000 }
    handle /auth/*        { reverse_proxy api:8000 }
    handle /.well-known/* { reverse_proxy api:8000 }
    handle                { reverse_proxy web:3000 }
}
```

Demo `.env.demo`: `ENV=demo`, `SESSION_COOKIE_NAME=__Host-session`, `SESSION_SECURE=true`, `PUBLIC_BASE_URL=https://<domain>`, `SMTP_* for the real sender, DEV_LOG_LOGIN_CODES=false`, Sepolia chain values (BC-08).

### IN-07 Hosting options for the demo (decide by day 5)

Phones must reach the app to scan the check-in QR, so it needs an address the jury's phones can open.

| Option | Setup | Trade-off |
| --- | --- | --- |
| Small VPS with a domain | `make demo-up` on the server; Caddy gets HTTPS certificates automatically | Most realistic; needs a domain and a server (\~1 hour) |
| Cloudflare named tunnel | Laptop runs `make demo-up`; a tunnel maps `<domain>` and `auth.<domain>` to Caddy | Needs a domain on Cloudflare; laptop must stay online |
| Same Wi-Fi, no HTTPS (fallback) | `make dev` on the laptop; use its LAN IP in `PUBLIC_BASE_URL`; `SESSION_SECURE=false` | Works with no domain; not HTTPS, so say so in the demo; venue Wi-Fi may isolate devices |

Whichever is chosen, record a 3-minute screen video of the full flow the day before as a backup.

### Demo script (about 8 minutes)

1. **Problem, 30 s:** one persistent passport per student, verifiable by anyone, tamper-proof.
2. **Event, 2 min:** as super admin, create "AI Data Analysis Workshop", open check-in, show the presenter QR on the projector. Two team phones scan: one seed student, one `newcomer@btu.test` (shows *Unregistered*).
3. **Review, 1 min:** register the newcomer from the participant list, then Mark as done; point at "skipped: already holds the skill" if present.
4. **Issuance, 1 min:** Issuance page goes PENDING → ANCHORED; open the transaction on Sepolia Etherscan; note that one transaction covers the whole batch and holds no personal data.
5. **Student, 1 min:** sign in as the student, show the new version and download the PDF.
6. **Employer, 1.5 min:** in a private window (no login), enter the verification code → Valid; upload the PDF → Valid, plus "checked directly on the blockchain from your browser".
7. **Attacks, 1 min:** upload a copy with an edited date → Not valid; enter an old version's code → Superseded; (pre-run) a root anchored on a look-alike contract → Not issued by BTU.
8. **Scale and security, 30 s:** batching (one transaction per batch, not per passport), 30-second rotating QR, passwordless email-code sign-in, issuer key isolated in the signer.

**Done when (M10):** the full script runs end to end twice in a row on the chosen hosting option without manual fixes.
