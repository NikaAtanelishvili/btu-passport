# Backend

## 1. Setup and package structure

One Python project (`backend/`, managed with uv) with three entry points — API, worker, signer — plus a CLI for seeding. Everything below uses synchronous SQLAlchemy; at this scale async adds complexity without benefit.

### BE-01 Scaffold (M0) ✅

**Dependencies:** `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `sqlalchemy>=2`, `alembic`, `psycopg[binary]`, `authlib`, `httpx`, `itsdangerous` (OAuth handshake cookie), `python-multipart`, `jinja2`, `weasyprint`, `segno`, `boto3`, `pycryptodome` (keccak), `web3` (read-only chain calls in the API; key use only in the signer). Dev group: `pytest`, `pytest-cov`, `time-machine`, `ruff`, `mypy`.

**Files:**

| Path | Contents |
| --- | --- |
| `app/main.py` | `create_app()`: routers, exception handlers, `SessionMiddleware` for the OAuth handshake only, `GET /api/healthz` → `{"ok": true}` |
| `app/config.py` | `Settings(BaseSettings)` with every variable from Overview §4; `get_settings()` cached |
| `app/db.py` | Engine, `SessionLocal`, dependency `get_db()`: one transaction per request — commit on success, rollback on exception |
| `app/errors.py` | `AppError(code, message, status=400, fields=None)` and handlers producing `{error, message, fields}`; Pydantic validation errors become 422 with `fields` keyed by field name |
| `app/models/` | One module per aggregate: `student.py` (Student, Passport), `catalog.py` (SkillCategory, Skill), `award.py` (AwardSubmission, SkillAward), `version.py` (PassportVersion, VersionAward, AnchorBatch), `job.py`, `user.py` (User, UserRole, Session), `audit.py`, `event.py` (Event, EventParticipant) |
| `app/schemas/` | Pydantic request/response models, mirrored by module; shared `Page[T]` = `{items, total, page, page_size}` |
| `app/routers/` | `auth.py`, `session.py`, `verify.py`, `wellknown.py`, `checkin.py`, `me.py`, `stamps.py`, `admin/` (`dashboard`, `students`, `awards`, `versions`, `events`, `skills`, `categories`, `roles`, `audit`) |
| `app/auth/` | `oidc.py`, `sessions.py`, `deps.py` (guards), `csrf.py` |
| `app/services/` | `codes.py`, `audit.py`, `storage.py`, `issuance.py`, `content.py`, `events.py`, `qr_tokens.py`, `merkle.py`, `chain.py` (read-only), `verification.py` |
| `app/pdf/` | `render.py`, `templates/passport.html.j2`, `templates/passport.css`, `fonts/NotoSansGeorgian-*.ttf` |
| `worker/__main__.py`, `worker/jobs.py`, `worker/ticks.py` | Job loop and handlers (§7) |
| `signer/` | Separate service (Blockchain tab, BC-07) |
| `cli/__main__.py` | `seed`, `bootstrap`, `issue-pending` commands |

**Conventions:** list endpoints take `page` (default 1) and `page_size` (default 25, max 100). Times are stored as `timestamptz` and returned in ISO 8601 UTC. Emails are stored lower-cased. IDs from the domain (Student ID, Passport ID, Skill ID) are the primary keys; internal tables use `bigserial` or UUID.

**Done when:** `make api` serves `GET /api/healthz`; `ruff`, `mypy` and an empty `pytest` run pass.

## 2. Data model

### BE-02 Models (M2)

Sixteen tables. Implement them as SQLAlchemy 2 models (`Mapped[...]` style) exactly as below; the SQL is the specification, not a file to run. Two refinements over the design doc: the passport's frozen fields are filled at **first issuance**, not at registration (so a typo can be fixed before anything is printed), and events are **soft-deleted** so students can still see "Event deleted".

```sql
-- People and passports ---------------------------------------------------
students(
  student_id       text PRIMARY KEY,                 -- 'BTU-T-0001'
  first_name       text NOT NULL, last_name text NOT NULL,
  email            text NOT NULL UNIQUE CHECK (email = lower(email)),
  program          text NOT NULL,
  education_level  text NOT NULL CHECK (education_level IN ('BACHELOR','MASTER','DOCTORAL')),
  status           text NOT NULL CHECK (status IN ('ACTIVE','GRADUATE')),
  created_at, updated_at timestamptz NOT NULL DEFAULT now())

passports(
  passport_id        text PRIMARY KEY,               -- 'BTU-AI-000125'
  student_id         text NOT NULL UNIQUE REFERENCES students,      -- FR-10
  holder_first_name  text NULL, holder_last_name text NULL,         -- set at first issue
  first_issued_on    date NULL,                                     -- set at first issue
  latest_version_id  bigint NULL REFERENCES passport_versions,
  created_at timestamptz NOT NULL DEFAULT now())
SEQUENCE passport_number_seq;      -- next Passport ID = 'BTU-AI-' || lpad(nextval, 6, '0')

-- Catalog ---------------------------------------------------------------
skill_categories(
  category_id   smallserial PRIMARY KEY,
  name          text NOT NULL UNIQUE,                -- 'AI Applied Skill'
  badge_code    text NOT NULL UNIQUE,                -- 'BDG-AI-002'
  stamp_sha256  text NULL, stamp_key text NULL, stamp_mime text NULL,
  archived_at   timestamptz NULL, created_at timestamptz NOT NULL DEFAULT now())

skills(
  skill_id     text PRIMARY KEY,                     -- 'SKL-001'
  name         text NOT NULL UNIQUE CHECK (length(name) <= 80),
  category_id  smallint NOT NULL REFERENCES skill_categories,
  description  text NOT NULL CHECK (length(description) <= 300),
  archived_at  timestamptz NULL, created_at, updated_at timestamptz NOT NULL DEFAULT now())

-- Awards ----------------------------------------------------------------
award_submissions(
  submission_id    uuid PRIMARY KEY,
  kind             text NOT NULL CHECK (kind IN ('DIRECT','EVENT','SEED')),
  idempotency_key  text NULL UNIQUE,                 -- DIRECT: Idempotency-Key header
  event_id         uuid NULL UNIQUE REFERENCES events, -- EVENT: one submission per event (FR-32)
  reason           text NULL,
  submitted_by     uuid NULL REFERENCES users,       -- NULL for SEED
  response_json    jsonb NULL,                       -- replayed on a repeated request
  created_at timestamptz NOT NULL DEFAULT now())

skill_awards(
  award_id          bigserial PRIMARY KEY,
  student_id        text NOT NULL REFERENCES students,
  skill_id          text NOT NULL REFERENCES skills,
  date_earned       date NOT NULL,
  submission_id     uuid NOT NULL REFERENCES award_submissions,
  legacy_record_id  text NULL UNIQUE,                -- 'REC-0001' from the seed CSV
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (student_id, skill_id))

-- Versions and anchoring -----------------------------------------------
passport_versions(
  version_id         bigserial PRIMARY KEY,
  passport_id        text NOT NULL REFERENCES passports,
  version_no         int  NOT NULL CHECK (version_no >= 1),
  status             text NOT NULL CHECK (status IN
                       ('LEGACY','PENDING','RENDERED','ANCHORING','ANCHORED','FAILED')),
  content_json       jsonb NULL,                     -- frozen snapshot, set when RENDERED
  verification_code  text NULL UNIQUE,               -- 10 Crockford base32 chars, no dashes
  pdf_sha256         text NULL UNIQUE,               -- 64 lowercase hex
  pdf_key            text NULL,                      -- 'pdf/<sha256>.pdf'
  batch_id           bigint NULL REFERENCES anchor_batches,
  merkle_proof       jsonb NULL,                     -- ['0x…', …]
  issued_at          timestamptz NULL,
  error              text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (passport_id, version_no))

version_awards(version_id bigint REFERENCES passport_versions,
               award_id bigint REFERENCES skill_awards,
               PRIMARY KEY (version_id, award_id))

anchor_batches(
  batch_id          bigserial PRIMARY KEY,
  merkle_root       text NOT NULL UNIQUE,            -- '0x' + 64 hex
  leaf_count        int  NOT NULL,
  chain_id          bigint NOT NULL, contract_address text NOT NULL,
  status            text NOT NULL CHECK (status IN ('SUBMITTING','ANCHORED','FAILED')),
  attempts          int NOT NULL DEFAULT 0, last_error text NULL,
  tx_hash           text NULL, block_number bigint NULL, anchored_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now())

jobs(
  job_id      bigserial PRIMARY KEY,
  type        text NOT NULL CHECK (type IN ('ISSUE_VERSION','ANCHOR_BATCH')),
  payload     jsonb NOT NULL DEFAULT '{}',
  status      text NOT NULL CHECK (status IN ('QUEUED','RUNNING','DONE','FAILED')),
  attempts    int NOT NULL DEFAULT 0, max_attempts int NOT NULL DEFAULT 5,
  run_after   timestamptz NOT NULL DEFAULT now(), locked_at timestamptz NULL,
  last_error  text NULL, dedupe_key text NULL,
  created_at timestamptz NOT NULL DEFAULT now())
INDEX jobs_ready ON jobs (status, run_after);
UNIQUE INDEX jobs_dedupe ON jobs (dedupe_key) WHERE status IN ('QUEUED','RUNNING');

-- Users, roles, sessions, audit ------------------------------------------
users(user_id uuid PRIMARY KEY, oidc_subject text NOT NULL UNIQUE,
      email text NOT NULL UNIQUE CHECK (email = lower(email)), display_name text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), last_login_at timestamptz NULL)

user_roles(email text PRIMARY KEY CHECK (email = lower(email)),  -- grant before first sign-in
           role  text NOT NULL CHECK (role IN ('SUPER_ADMIN','ADMIN')),
           granted_by uuid NULL REFERENCES users, granted_at timestamptz NOT NULL DEFAULT now())

sessions(session_hash text PRIMARY KEY,           -- sha256 of the cookie token
         user_id uuid NOT NULL REFERENCES users ON DELETE CASCADE,
         csrf_token text NOT NULL, acr text NULL, id_token text NOT NULL,
         created_at, last_seen_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL)

audit_log(id bigserial PRIMARY KEY, at timestamptz NOT NULL DEFAULT now(),
          actor_user_id uuid NULL, actor_email text NULL,   -- NULL actor = system
          action text NOT NULL,                            -- 'student.create', 'event.complete'
          entity text NOT NULL, entity_id text NOT NULL,
          before jsonb NULL, after jsonb NULL)

-- Events -----------------------------------------------------------------
events(
  event_id           uuid PRIMARY KEY,
  name               text NOT NULL CHECK (length(name) <= 120),
  skill_id           text NOT NULL REFERENCES skills,
  description        text NULL CHECK (length(description) <= 500),
  starts_at, ends_at timestamptz NOT NULL CHECK (ends_at > starts_at),
  location           text NULL,
  checkin_opens_at, checkin_closes_at timestamptz NOT NULL
                     CHECK (checkin_closes_at > checkin_opens_at),
  status             text NOT NULL CHECK (status IN
                       ('DRAFT','CHECKIN_OPEN','CHECKIN_CLOSED','COMPLETED')),
  qr_secret          bytea NOT NULL,                 -- 32 random bytes
  created_by uuid NOT NULL REFERENCES users, completed_by uuid NULL REFERENCES users,
  completed_at timestamptz NULL, deleted_at timestamptz NULL,
  created_at, updated_at timestamptz NOT NULL DEFAULT now())

event_participants(
  id            bigserial PRIMARY KEY,
  event_id      uuid NOT NULL REFERENCES events,
  email         text NOT NULL CHECK (email = lower(email)),
  student_id    text NULL REFERENCES students,      -- NULL = Unregistered (FR-30)
  display_name  text NOT NULL,
  method        text NOT NULL CHECK (method IN ('QR','MANUAL')),
  checked_in_at timestamptz NOT NULL DEFAULT now(),
  added_by uuid NULL REFERENCES users,
  removed_at timestamptz NULL, removed_by uuid NULL REFERENCES users,
  UNIQUE (event_id, email))                         -- FR-29
```

**Database triggers (written by hand in the migration, BE-03):**

1. `audit_log_append_only` — BEFORE UPDATE OR DELETE on `audit_log` → `RAISE EXCEPTION 'audit_log is append-only'` (FR-09).
2. `passport_frozen_fields` — BEFORE UPDATE on `passports`: `passport_id` and `student_id` may never change; `holder_first_name`, `holder_last_name`, `first_issued_on` may change only from NULL to a value (FR-11).
3. `event_rules` — BEFORE UPDATE on `events`: reject a change of `skill_id` if any `event_participants` row exists for the event (FR-26); once the old row has `status = 'COMPLETED'`, reject every update, including setting `deleted_at` (FR-27: completed events are read-only and can't be deleted).
4. `skill_awards_no_delete` — BEFORE DELETE on `skill_awards` → raise: issued passports reference awards, so they are never deleted.

**Done when:** models import cleanly; `alembic revision --autogenerate` against an empty database produces only the expected tables.

## 3. Migrations and seed import

### BE-03 Initial migration (M2)

- `migrations/versions/0001_initial.py`: autogenerate from the models, then review by hand. Add the four triggers from §2 as `op.execute()` SQL, plus `CREATE SEQUENCE passport_number_seq START 1`.
- `make migrate` = `alembic upgrade head`; `make migrate-test` does the same on `passport_test`.
- Tests: an UPDATE or DELETE on `audit_log` raises; changing `passports.holder_first_name` after it is set raises; changing an event's `skill_id` with a participant raises; any update to a COMPLETED event raises; deleting a `skill_awards` row raises.

**Done when:** `make migrate` on an empty database succeeds and the trigger tests pass.

### BE-04 Seed import: `python -m cli seed` (M2)

Reads `seed/test-data.csv` (the hackathon file, unchanged). Idempotent: every insert is "insert if the natural key doesn't exist", so running twice changes nothing.

1. **Parse.** Skip the first 3 lines; line 4 is the header; read data rows until the first row whose `Record ID` is empty (the notes block follows). Expect 60 rows.
2. **Normalise.** Education level: `Bachelor's` → `BACHELOR`, `Master's` → `MASTER`. Status: `Active` → `ACTIVE`, `Graduate` → `GRADUATE`. Emails lower-cased.
3. **Categories (3).** From distinct (`Skill Category`, `Badge/Stamp Code`). Upload `seed/stamps/<badge_code>.svg` to MinIO and set the stamp columns.
4. **Skills (16).** From distinct `Skill ID` with name, category and description.
5. **Students (18) and passports (18).** Passport ID from the CSV. `first_issued_on` from `First Issued (Existing)` and holder names from the student — the seed is the one place these are set without an issued version. Then `setval('passport_number_seq', <highest seed number>)`, so the next new passport is `BTU-AI-000143`.
6. **Awards (60).** One `award_submissions` row of kind `SEED`; one `skill_awards` row per CSV row with `legacy_record_id` = Record ID.
7. **Legacy versions (8).** For each student with SYNCED rows: one `passport_versions` row, `version_no = 1`, status `LEGACY`, `issued_at` = `Synced At`, no PDF or code; `version_awards` = that student's SYNCED awards. Set `passports.latest_version_id` to it. (Requirements Q2 default.)
8. **Separate command `python -m cli issue-pending`** (M4, needs BE-23). For every student whose awards aren't all in their latest version, call `issuance.create_versions()` (§6) with kind `SEED`. That gives v2 for the 8 legacy students and v1 for the other 10.
9. Print counts: students, passports, categories, skills, awards, legacy versions, pending versions created.

**Done when:** a fresh seed prints 18 / 18 / 3 / 16 / 60 / 8; a second run prints all zeros; in M4, `issue-pending` creates 18 PENDING versions.

### BE-05 Bootstrap: `python -m cli bootstrap [--dev-users]` (M2)

Upserts `user_roles` for `BOOTSTRAP_SUPER_ADMIN_EMAIL` as `SUPER_ADMIN`. With `--dev-users` also grants `admin@btu.test` the `ADMIN` role, matching the Keycloak test users (Infra tab, IN-04). Writes an audit row with a NULL actor.

**Done when:** after bootstrap, signing in as `superadmin@btu.test` (M3) gives the super admin role.

## 4. Authentication and authorization

Keycloak proves who the user is; our `sessions` table keeps them signed in; `user_roles` and the `students` email match decide what they may do. All checks are FastAPI dependencies, applied per router.

### BE-10 OIDC sign-in (M3) — `app/auth/oidc.py`, `app/routers/auth.py`

Authlib's Starlette client, configured from `OIDC_ISSUER/.well-known/openid-configuration`, scope `openid email profile`, PKCE `S256`. The short-lived state, nonce and PKCE verifier live in Starlette's signed `SessionMiddleware` cookie (handshake only, 10-minute max age).

| Route | Behaviour |
| --- | --- |
| `GET /auth/login?next=/path` | Accept `next` only if it is a relative path starting with `/`; store it; redirect to Keycloak |
| `GET /auth/callback` | Exchange the code; Authlib validates the ID token (signature via JWKS, `iss`, `aud`, `exp`, nonce). Require `email_verified = true` and an email domain in `ALLOWED_EMAIL_DOMAINS`, else 403 page. Upsert `users` by `sub`. Create a session (BE-11), set cookies, redirect to `next`, else by role: admin → `/admin`, student → `/me`, otherwise `/` |
| `POST /auth/logout` | Delete the session row, clear both cookies, return `{redirect: <Keycloak end_session_endpoint>?id_token_hint=…&post_logout_redirect_uri=PUBLIC_BASE_URL}`; the frontend navigates there so the Keycloak session ends too (needed to switch test users in the demo) |

### BE-11 Sessions (M3) — `app/auth/sessions.py`

- Token = `secrets.token_urlsafe(32)`; store only its SHA-256 in `sessions.session_hash`. Cookie: name `SESSION_COOKIE_NAME`, HttpOnly, `SameSite=Lax`, `Secure` when `SESSION_SECURE`, path `/`.
- `expires_at` = now + `SESSION_ABSOLUTE_HOURS`. For users with a role, also expire when `last_seen_at` is older than `ADMIN_IDLE_MINUTES`.
- Update `last_seen_at` at most once a minute per session.
- `revoke_user_sessions(email)` deletes all sessions for that email; called when a role is revoked or changed (FR-08).

### BE-12 Guards (M3) — `app/auth/deps.py`

| Dependency | Passes when | Otherwise |
| --- | --- | --- |
| `current_user_optional` | Always; returns `Principal(user, role, student)` or `None` | — |
| `require_user` | Signed in | 401 `unauthenticated` |
| `require_student` | Signed in and `students.email = user.email` | 403 `not_a_student` |
| `require_admin` | Role is `ADMIN` or `SUPER_ADMIN` and the MFA check passes | 403 `forbidden` |
| `require_super_admin` | Role is `SUPER_ADMIN` and the MFA check passes | 403 `forbidden` |

The role is read from `user_roles` on **every request** (one indexed lookup), so revocation is immediate. MFA check: when `REQUIRE_MFA_CLAIM` is true, the session's stored `acr` must equal `MFA_ACR_VALUE` (default `"2"`, the level Keycloak assigns after the OTP step; see IN-04). Apply guards at router level: `admin/*` routers depend on `require_admin`, and super-admin endpoints add `require_super_admin`.

### BE-13 CSRF (M3) — `app/auth/csrf.py`

Double-submit: at session creation set a readable cookie `csrf_token` equal to `sessions.csrf_token`. Middleware: for POST, PUT, PATCH, DELETE under `/api/` and `/auth/logout`, require header `X-CSRF-Token` equal to the session's token, else 403 `csrf_failed`. Exempt `/api/verify/*` (public, no session).

### BE-14 Session endpoint (M3) — `GET /api/session`

```json
{ "authenticated": true,
  "user": { "email": "btu-t-0002@example.org", "name": "Mariam Beridze" },
  "role": null,                      // "SUPER_ADMIN" | "ADMIN" | null
  "student": { "student_id": "BTU-T-0002", "passport_id": "BTU-AI-000126" } }
```

Unauthenticated: `{"authenticated": false}` with status 200.

**Done when (M3):** integration tests sign in through a fake OIDC provider fixture (no Keycloak needed in tests) as a super admin, an admin, a student and an unknown BTU user; each gets the right `/api/session`; a student gets 403 on `GET /api/admin/students` (A11); a POST without the CSRF header gets 403; a revoked admin's next request gets 403 (A12).

## 5. API endpoints

The complete contract, grouped by router. Shapes are written as Pydantic field lists; `?` means optional. Every list returns `Page[T]`. Error codes used everywhere: `validation_error` (422), `unauthenticated` (401), `forbidden` / `csrf_failed` (403), `not_found` (404), `conflict` (409, with a specific `error` such as `duplicate_email`), `rate_limited` (429).

### Public: verify, issuer file, stamps (BE-30 – BE-32, M5)

| Method, path | Request | Response | Notes |
| --- | --- | --- | --- |
| `GET /api/verify/{code}` | code, any case, dashes optional | `VerifyResult` | `UNKNOWN_CODE` if no ANCHORED version has it |
| `POST /api/verify/hash` | `{sha256}` (64 hex) | `VerifyResult` | `NOT_FOUND` if no ANCHORED version has that hash |
| `GET /api/verify/{code}/pdf` | — | `application/pdf` | Only ANCHORED versions |
| `GET /api/verify/{code}/proof.json` | — | Proof file (Blockchain tab, BC-06) | Only ANCHORED versions |
| `GET /.well-known/ai-passport-issuer.json` | — | `{issuer_name, chain_id, contract_address, issuer_address}` | From config |
| `GET /api/stamps/{sha256}` | — | Stamp image | Public; used by check-in and verify pages |

`VerifyResult` = `{verdict, checks: {document: bool, issuer: bool}, version?: {passport_id, version_no, issued_at, holder_name, skills: [{name, category, badge_code, stamp_sha256, date_earned}]}, latest_version_no?, chain?: {chain_id, contract_address, issuer_address, merkle_root, tx_hash, block_number, anchored_at}, proof?: {pdf_sha256, leaf, proof}}`. `verdict` ∈ `VALID`, `SUPERSEDED`, `NOT_FOUND`, `UNKNOWN_CODE`, `NOT_ISSUED_BY_BTU`, `REVOKED`. The server computes the verdict by reading the chain (`app/services/chain.py`); the browser re-checks independently (Frontend tab, FE-12).

### Session and student portal (BE-14, BE-46, BE-47)

| Method, path | Guard | Response |
| --- | --- | --- |
| `GET /api/session` | none | See BE-14 |
| `GET /api/me/passport` | student | `{passport_id, holder_name, first_issued_on?, current?: VersionSummary, issuing?: {version_no}, skills: [SkillOnPassport]}`; `current` = the latest ANCHORED version; `issuing` when a newer PENDING/RENDERED/ANCHORING one exists |
| `GET /api/me/versions` | student | `[VersionSummary]`, newest first, including LEGACY |
| `GET /api/me/versions/{version_no}/pdf`, `/proof.json` | student | Own ANCHORED versions only, else 404 |
| `GET /api/me/events` | student | `[{event_id, name, starts_at, skill_name, status}]`, `status` ∈ `WAITING`, `AWARDED` (+ `version_no`), `ALREADY_HELD`, `NOT_CONFIRMED`, `EVENT_DELETED` |

`VersionSummary` = `{version_no, status, issued_at?, verification_code?, skill_count, added_skills: [name], superseded: bool}`.

### Check-in (BE-42, M7) — guard: signed in (any BTU user)

| Method, path | Request | Response |
| --- | --- | --- |
| `GET /api/checkin/{event_id}?t=` | token in query | `{event: {name, starts_at, location?, skill: {name, category, stamp_sha256}}, state}`; `state` ∈ `CONFIRM`, `CHECKED_IN`, `TOKEN_EXPIRED`, `NOT_OPEN`, `CLOSED`, REMOVED, `NOT_FOUND` |
| `POST /api/checkin/{event_id}` | `{t}` | `{state: "CHECKED_IN", unregistered: bool, already_holds_skill: bool}`; a repeat returns the same body |

### Admin, both roles (BE-24, BE-29, BE-35)

| Method, path | Request | Response | Notes |
| --- | --- | --- | --- |
| `GET /api/admin/dashboard` | — | `{checkin_open, awaiting_completion, unregistered_checkins, failed_versions, recent: [VersionRow]}` | Counters for A1 |
| `GET /api/admin/students` | `q?, program?, status?, has_passport?` | `Page[StudentRow]` | `q` matches name, Student ID, email |
| `POST /api/admin/students` | `StudentCreate{student_id, first_name, last_name, email, program, education_level, status}` | 201 `StudentDetail` | Creates the passport with the next Passport ID; 409 `duplicate_student_id` / `duplicate_email` |
| `GET /api/admin/students/{id}` | — | `StudentDetail{profile, passport{passport_id, first_issued_on?, frozen: bool, versions: [VersionRow]}, awards: [AwardRow], events: [ParticipationRow]}` |  |
| `PATCH /api/admin/students/{id}` | any `StudentCreate` field except `student_id` | `StudentDetail` + `warnings` | `warnings: ["printed_name_differs"]` when names change after first issue; the passport is untouched |
| `GET /api/admin/programs` | — | `[string]` | Distinct programs in `students`, for the select |
| `POST /api/admin/awards/preview` | `{student_ids, skill_id, date_earned, reason}` | `{rows: [{student_id, name, result: "NEW_VERSION" \| "SKIP_ALREADY_HELD", from_version?, to_version?}]}` | No writes |
| `POST /api/admin/awards` | same body + header `Idempotency-Key` (UUID) | 202 `{submission_id, versions: [{student_id, version_id, version_no}], skipped: [student_id]}` | Same key again → the stored response |
| `GET /api/admin/versions` | `status? (comma-separated list), passport_id?` | `Page[VersionRow]` | For the issuance page |
| `POST /api/admin/versions/{id}/retry` | — | 202 `VersionRow` | 409 unless FAILED |
| `POST /api/admin/versions/retry-failed` | — | `{count}` |  |
| `GET /api/admin/versions/{id}/pdf` | — | PDF | Any ANCHORED version |
| `GET /api/admin/events`, `/{id}`, `/{id}/participants` | — | read-only for ADMIN | See below |

`VersionRow` = `{version_id, passport_id, student_id, student_name, version_no, status, error?, issued_at?, created_at}`.

### Events (BE-40 – BE-45, M7) — writes need super admin

| Method, path | Request | Response | Notes |
| --- | --- | --- | --- |
| `GET /api/admin/events` | `status?` | `Page[EventRow{event_id, name, skill_name, starts_at, participant_count, status}]` | Excludes deleted |
| `POST /api/admin/events` | `EventCreate{name, skill_id, description?, starts_at, ends_at, location?, checkin_opens_at?, checkin_closes_at?}` | 201 `EventDetail` | Window defaults: opens = ends − 15 min, closes = ends + 30 min |
| `GET /api/admin/events/{id}` | — | `EventDetail{...EventCreate, event_id, status, skill, counts{total, unregistered, already_held}, can_complete, complete_blockers: [code], completion?: {awarded, skipped}}` | Blockers: `CHECKIN_OPEN`, `UNREGISTERED_PRESENT`, `NO_PARTICIPANTS` |
| `PATCH /api/admin/events/{id}` | any `EventCreate` field | `EventDetail` | 409 `skill_locked`, 409 `event_completed` |
| `DELETE /api/admin/events/{id}` | — | 204 | Soft delete; 409 `event_completed` |
| `POST /api/admin/events/{id}/open` \| `/close` \| `/reopen` | — | `EventDetail` | See BE-40 for the time rules |
| `GET /api/admin/events/{id}/qr` | — | `{url, svg, refresh_in_seconds, participant_count, status}` | Super admin only; `svg` from segno |
| `GET /api/admin/events/{id}/participants` | `include_removed?` | `[{email, student_id?, name, checked_in_at, method, flags: ["UNREGISTERED" \| "ALREADY_HOLDS"], removed_at?}]` | Polled every 3 s by the UI |
| `POST /api/admin/events/{id}/participants` | `{student_id}` | `Participant` | Manual add; 409 if present |
| `DELETE /api/admin/events/{id}/participants/{email}` | — | 204 | Sets `removed_at` |
| `POST /api/admin/events/{id}/complete` | — | `{submission_id, awarded: [{student_id, version_no}], skipped: [student_id]}` | 409 `cannot_complete` + blockers; repeat → stored response |

### Super admin: catalog, roles, audit (BE-50 – BE-53, M9)

| Method, path | Request | Response | Notes |
| --- | --- | --- | --- |
| `GET /api/admin/skills` | `include_archived?` | `[SkillRow{skill_id, name, category, description, times_awarded, archived}]` | Admins may read |
| `POST /api/admin/skills` | `{name, category_id, description}` | 201 `SkillRow` | `skill_id` generated: next `SKL-nnn` |
| `PATCH /api/admin/skills/{id}` | `{name?, category_id?, description?}` | `SkillRow` |  |
| `POST /api/admin/skills/{id}/archive` \| `/unarchive` | — | `SkillRow` |  |
| `DELETE /api/admin/skills/{id}` | — | 204 | 409 `in_use` if awarded or used by an event |
| `GET /api/admin/categories` | — | `[CategoryRow{category_id, name, badge_code, stamp_sha256?, skill_count, archived}]` | Admins may read |
| `POST /api/admin/categories` | `{name}` | 201 `CategoryRow` | `badge_code` generated: next `BDG-AI-nnn` |
| `PATCH /api/admin/categories/{id}`, `POST .../archive`, `DELETE ...` | as skills |  | 409 `in_use` if any skill uses it |
| `POST /api/admin/categories/{id}/stamp` | multipart `file` | `CategoryRow` | PNG or SVG, ≤ 1 MB, PNG ≥ 600×600 and square; stored by SHA-256 |
| `GET /api/admin/roles` | — | `[{email, role, name?, granted_by_email?, granted_at, last_login_at?}]` |  |
| `PUT /api/admin/roles/{email}` | `{role}` | Role row | Domain check; revokes the person's sessions on change |
| `DELETE /api/admin/roles/{email}` | — | 204 | 409 `last_super_admin` |
| `GET /api/admin/audit` | `actor?, action?, from?, to?` | `Page[AuditRow]` | Newest first |

## 6. Services

Routers stay thin: they validate input, call one service function inside the request transaction, and map `AppError`s. All business rules live here.

### BE-20 Codes and IDs (M4) — `app/services/codes.py`

- `new_verification_code()`: 10 characters from Crockford base32 `0123456789ABCDEFGHJKMNPQRSTVWXYZ` via `secrets.choice` (50 bits). Stored without dashes; on a unique-violation, generate again.
- `format_code("K7QM3XWP9D")` → `"K7QM-3XWP-9D"`. `normalize_code(text)`: upper-case, drop dashes and spaces, map `O` → `0` and `I`, `L` → `1`; reject anything else outside the alphabet.
- `next_passport_id(db)` → `BTU-AI-` + 6-digit `nextval('passport_number_seq')`. `next_skill_id`, `next_badge_code`: highest existing number + 1, zero-padded to 3.

### BE-21 Audit (M4) — `app/services/audit.py`

`record(db, actor, action, entity, entity_id, before=None, after=None)` inserts in the caller's transaction. `actor` is the request `Principal` or `None` for the system. Action names: `student.create`, `student.update`, `award.direct`, `version.retry`, `event.create`, `event.update`, `event.open`, `event.close`, `event.reopen`, `event.delete`, `event.complete`, `participant.add`, `participant.remove`, `skill.*`, `category.*`, `role.grant`, `role.revoke`, `bootstrap`.

### BE-22 Storage (M4) — `app/services/storage.py`

`put(key, data, content_type)` (skips the upload if the key already exists — keys are content hashes), `get(key) -> bytes`, `ensure_bucket()` at API start in dev. Keys: `pdf/<sha256>.pdf`, `stamps/<sha256>.<ext>`. Files are always streamed through the API; MinIO is never exposed to browsers.

### BE-23 Issuance (M4) — `app/services/issuance.py`

- `preview_award(db, student_ids, skill_id)` → one row per student: `SKIP_ALREADY_HELD` if a `skill_awards` row exists, else `NEW_VERSION` with `from_version` / `to_version`.
- `create_direct_award(db, actor, body, idempotency_key)`:
  1. If a submission with that key exists, return its `response_json`.
  2. Validate: skill exists and isn't archived; every student exists; `date_earned` is not after today (in `TIMEZONE`, default `Asia/Tbilisi`); `reason` is 1–300 characters.
  3. Insert the submission (kind `DIRECT`), then the awards for students who don't hold the skill.
  4. `create_versions(...)` for those students; store and return the response; audit `award.direct`.
- `create_versions(db, student_ids, submission)` — the one place versions are made (direct awards, events, seed):
  1. Process students sorted by ID (consistent lock order, no deadlocks).
  2. `SELECT … FROM passports WHERE student_id = :id FOR UPDATE`.
  3. `version_no` = highest existing + 1; insert a `PENDING` version.
  4. Insert `version_awards` for **all** of the student's awards at this moment.
  5. Enqueue an `ISSUE_VERSION` job `{version_id}`.
- **Deviation from FR-04:** the rule "date earned not before the first-issued date" is dropped, because an event can happen before a student is registered. Record this in the Deviations list.

### BE-25 Content snapshot — `app/services/content.py`

`build_content(db, version)` returns the JSON that is both stored in `content_json` and rendered into the PDF:

```json
{ "schema": "btu-ai-passport/1",
  "passport_id": "BTU-AI-000126", "version_no": 2,
  "holder": { "first_name": "Mariam", "last_name": "Beridze" },
  "first_issued_on": "2026-09-15", "issued_at": "2026-10-22T15:40:12Z",
  "verification_code": "K7QM3XWP9D", "verify_url": "https://…/v/K7QM3XWP9D",
  "skills": [ { "skill_id": "SKL-002", "name": "Prompt Engineering Fundamentals",
                "category": "AI Skill", "badge_code": "BDG-AI-001",
                "stamp_sha256": "…", "description": "…", "date_earned": "2026-09-21",
                "source": { "type": "event", "event_name": "…" } } ],
  "issuer": { "name": "Business and Technology University",
              "chain_id": 31337, "contract_address": "0x…" } }
```

Skills are sorted by `date_earned`, then `award_id`. If the passport has no `first_issued_on` yet, set it (today) and copy the holder names from the student, in the same transaction; the trigger then freezes them.

### BE-40 Events (M7) — `app/services/events.py`

| Function | Allowed from | Effect |
| --- | --- | --- |
| `create` | — | Status `DRAFT`; fill window defaults; `qr_secret` = 32 random bytes |
| `update` | not COMPLETED | Skill change rejected once a participant exists (`skill_locked`) |
| `open(now)` | DRAFT, CHECKIN\_CLOSED | → CHECKIN\_OPEN; `checkin_opens_at` = min(current, now); if `checkin_closes_at` ≤ now, set it to now + 30 min |
| `close(now)` | CHECKIN\_OPEN | → CHECKIN\_CLOSED; `checkin_closes_at` = now |
| `reopen(now)` | CHECKIN\_CLOSED | → CHECKIN\_OPEN; `checkin_closes_at` = now + 30 min |
| `tick(now)` | worker, every 15 s | DRAFT with opens ≤ now < closes → OPEN; OPEN with now ≥ closes → CLOSED |
| `delete` | not COMPLETED | Set `deleted_at` (soft) |
| `complete(actor)` | CHECKIN\_CLOSED, no blockers | See below |

`complete`: if a submission with this `event_id` exists, return its stored response. Otherwise create a submission (kind `EVENT`, `event_id`); for each participant with `removed_at IS NULL` and a `student_id`, skip those who hold the skill, else insert an award dated the event's start date in `TIMEZONE`; call `create_versions`; set COMPLETED, `completed_by`, `completed_at`; store the response; audit `event.complete`. All in one transaction.

**Linking Unregistered check-ins:** when a student is created (or an email changes), set `event_participants.student_id` on rows with that email and a NULL `student_id`.

### BE-41 QR tokens (M7) — `app/services/qr_tokens.py`

- `window(now) = floor(unix_seconds / 30)`.
- `token(secret, event_id, w)` = first 16 characters of `base32(HMAC-SHA256(secret, f"{event_id}:{w}"))`, no padding.
- `is_valid(secret, event_id, t, now)`: constant-time compare against windows `w` and `w − 1` — a token lives 30–60 s (FR-28).
- `checkin_url` = `PUBLIC_BASE_URL/checkin/{event_id}?t={token}`; `refresh_in_seconds` = 30 − (unix\_seconds mod 30).

### BE-42 Check-in logic (M7)

In order: event missing or deleted → `NOT_FOUND`; the caller's row exists and is removed → `REMOVED`; the caller's row exists → `CHECKED_IN` (no token needed); status DRAFT → `NOT_OPEN`; CLOSED or COMPLETED → `CLOSED`; token invalid → `TOKEN_EXPIRED`; else GET returns `CONFIRM` and POST inserts the row (`ON CONFLICT (event_id, email) DO NOTHING`), with `student_id` from the email match, `display_name` from the user, method `QR`.

### BE-43 Participants (M7)

Manual add takes a `student_id`, uses that student's email, method `MANUAL`; if a removed row exists, clear `removed_at`. Remove sets `removed_at`, `removed_by`. Flags: `UNREGISTERED` when `student_id` is NULL; `ALREADY_HOLDS` when an award exists for (student, event skill). Both actions are audited.

### BE-30 Verification (M5) — `app/services/verification.py`, `app/services/chain.py`

`chain.py` holds a read-only web3 client with three calls: `anchored_at(root)`, `owner()`, `is_revoked(leaf)`; results cached in-process for 60 s. `verify(version)`: issuer check = config contract address and `owner() == ISSUER_ADDRESS`; document check = recompute the root from `pdf_sha256` + `merkle_proof` (BC-04) and `anchored_at(root) > 0`; then `REVOKED`, else `SUPERSEDED` if `version_no` < the passport's latest ANCHORED `version_no`, else `VALID`. Verification never trusts `status` alone (dataset rule: use the chain proof).

### BE-46 My events status (M7)

Per participant row: removed → `NOT_CONFIRMED`; event deleted → `EVENT_DELETED`; event completed and an award exists from that event's submission → `AWARDED` with the first version containing it; completed without such an award → `ALREADY_HELD`; otherwise `WAITING`.

## 7. Worker and jobs

One process (`python -m worker`) that loops forever: claim a job, run it in its own transaction, repeat; plus two timers. Several worker processes can run safely because claiming uses `SKIP LOCKED`.

### BE-26 Job loop (M4) — `worker/__main__.py`

```sql
UPDATE jobs SET status = 'RUNNING', locked_at = now(), attempts = attempts + 1
WHERE job_id = (SELECT job_id FROM jobs
                WHERE status = 'QUEUED' AND run_after <= now()
                ORDER BY job_id FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING *;
```

- No job → sleep 1 s. Success → `DONE`. Exception → if `attempts < max_attempts`: back to `QUEUED` with `run_after = now() + 2^attempts minutes` (1, 2, 4, 8 …) and `last_error`; else `FAILED`.
- On start, put `RUNNING` jobs whose `locked_at` is older than 5 minutes back to `QUEUED` (a crashed worker).
- Handle SIGTERM: finish the current job, then exit.
- `enqueue(db, type, payload, dedupe_key=None)` in `app/services/jobs.py` is used by the API; a duplicate `dedupe_key` among QUEUED/RUNNING jobs is silently ignored.

**Timers** (`worker/ticks.py`, checked every loop):

| Timer | Every | Does |
| --- | --- | --- |
| Anchor tick | `ANCHOR_INTERVAL_SECONDS` | If any version is `RENDERED` or a batch is `SUBMITTING`, enqueue `ANCHOR_BATCH` with `dedupe_key = 'anchor'` |
| Event tick | 15 s | `events.tick(now)` (BE-40) |

### BE-27 `ISSUE_VERSION {version_id}` (M4) — `worker/jobs.py`

1. Load the version; continue only if `PENDING` (a repeat run is a no-op).
2. `build_content()` (BE-25), new verification code, `issued_at = now()`.
3. Render the PDF (§8); `sha256` of the bytes; `storage.put("pdf/<sha>.pdf")`.
4. Update the version: `content_json`, `verification_code`, `pdf_sha256`, `pdf_key`, `issued_at`, status `RENDERED`. Commit.
5. On a render error after the last attempt: status `FAILED`, `error` = the message.

### BE-28 `ANCHOR_BATCH` (M4)

1. **Pick the batch.** If a batch with status `SUBMITTING` exists, reuse it (a retry keeps the same root). Otherwise lock up to `BATCH_MAX_LEAVES` `RENDERED` versions (`FOR UPDATE SKIP LOCKED`, oldest first); none → done. Build the tree from their `pdf_sha256` (BC-04); insert the batch (`SUBMITTING`); set each version to `ANCHORING` with `batch_id` and its `merkle_proof`. **Commit** before calling the signer, so a crash can't lose the batch.
2. **Anchor.** `POST {SIGNER_URL}/anchor` with `{root, leaf_count}` and the HMAC header (BC-07), timeout 120 s.
3. **Success** → batch `ANCHORED` with `tx_hash`, `block_number`, `anchored_at`. Versions → `ANCHORED`. For each passport, set `latest_version_id` to the version if its `version_no` is higher than the current latest's. Commit.
4. **Failure** → batch `attempts += 1`, `last_error`; raise so the job loop backs off and retries the same batch. When `attempts` reaches `ANCHOR_MAX_ATTEMPTS`: batch `FAILED`; its versions → `FAILED` with `error = "anchoring failed: …"`.

### Retry (BE-29)

`POST /api/admin/versions/{id}/retry` on a `FAILED` version: if it has a `pdf_sha256` → back to `RENDERED`, clear `batch_id`, `merkle_proof`, `error` (the next anchor tick re-batches it); otherwise → `PENDING` and enqueue `ISSUE_VERSION`. Audit `version.retry`.

**Done when (M4):** with infra, Anvil, the signer and the worker running, a direct award for BTU-T-0021 reaches `ANCHORED` within 30 s and its PDF is in MinIO; stopping the signer leaves the version in `ANCHORING` and restarting it completes the same batch (same `merkle_root`); 3 awards posted together share one batch.

## 8. PDF rendering

### BE-25 (continued) Renderer and template (M4) — `app/pdf/`

`render_passport(content: dict) -> bytes` renders only from `content_json`; it never queries the database, so the same content always gives the same PDF.

- **Template:** `templates/passport.html.j2` with `passport.css`, Jinja2 with autoescape on. Build a plain placeholder layout now; BTU's design replaces the template later without code changes (`PASSPORT_TEMPLATE_DIR` setting, default `app/pdf/templates`).
- **Pages** (Web App Design, PDF section of the System Design): cover (BTU name, holder name, Passport ID, first issued) → version page (version, issue date, verification code formatted `XXXX-XXXX-XX`, QR, verify URL) → skill blocks, one per skill, `break-inside: avoid` so they flow onto as many pages as needed → last page (how to verify, chain ID, contract address, issuer address).
- **Footer on every page:** `@page { @bottom-center { content: "<Passport ID> · v<n> · <code> · page " counter(page) " of " counter(pages) } }`, A4, 18 mm margins.
- **QR:** `segno.make(verify_url, error="m").svg_data_uri(scale=4)` embedded as an `<img>`.
- **Stamps:** fetch each `stamp_sha256` from storage into a temporary directory and pass it as WeasyPrint's `base_url`; the template refers to `stamps/<sha>.<ext>`.
- **Font:** `@font-face` pointing at the bundled Noto Sans Georgian files (OFL licence; commit them under `app/pdf/fonts/`), used for all text, so Georgian names render (NFR-12).
- **Determinism (NFR-13):** set `<meta name="dcterms.created">` and `dcterms.modified` from `issued_at`; no random values in the template. Test: render the same content twice and compare SHA-256. If the bytes still differ, find the varying field (usually metadata dates or the PDF `/ID`) and pin it using WeasyPrint's options; if that turns out to be impossible, record it under Deviations — the stored bytes are the source of truth either way.

**Done when:** a test renders the seed student with 6 skills (BTU-T-0007) into a multi-page PDF; a Georgian test name (ნიკოლოზ გელაშვილი) renders correctly: `pdffonts` lists Noto Sans Georgian as embedded and `pdftotext` returns the name; the determinism test passes.

## 9. Backend tests

pytest against a real PostgreSQL (`passport_test`), because the triggers, constraints and `SKIP LOCKED` are part of the behaviour. Chain tests need Anvil and are marked so they can be skipped.

| Folder | What | Needs |
| --- | --- | --- |
| `tests/unit/` | codes, QR tokens (with `time-machine`), Merkle vs shared vectors, content builder, event transitions, verdict logic | nothing |
| `tests/integration/` | Every router through FastAPI's `TestClient`; triggers; seed import; worker handlers called directly (not the loop) | Postgres, MinIO |
| `tests/chain/` (`@pytest.mark.chain`) | Signer against Anvil, end-to-end anchoring, `chain.py` reads | + Anvil with the contract deployed |

**Fixtures (`tests/conftest.py`):**

- `db` — runs migrations once per session; truncates all tables between tests (faster and simpler than nested transactions with triggers).
- `client_as(role)` — a `TestClient` with a real session row and CSRF cookie for `"super_admin" | "admin" | "student" | "unregistered" | None`; bypasses Keycloak by inserting the session directly.
- `fake_oidc` — stubs Authlib's token exchange to return chosen claims, for BE-10 tests.
- `seeded` — runs the seed importer on the real CSV.
- `fake_signer` — an in-process stand-in that records roots and returns a fake receipt, or fails on demand; used everywhere except `tests/chain/`.
- `run_jobs()` — drains the job queue by calling the handlers until it's empty.

**Must-have tests** (each maps to an acceptance scenario, Infra tab §4): A1, A2 (one version for two awards, date order, unchanged Passport ID), A3 (same Idempotency-Key twice), A6, A8, A9, A11, A12, A13 (token from 2 windows ago rejected), A14, A15 (complete twice), A16 (delete completed → 409), plus the trigger tests from BE-03.

### BE-60 Hardening (M10)

- Rate limits, in-process token bucket keyed by client IP (behind Caddy use `X-Forwarded-For` from the trusted proxy only): `/api/verify/*` 30 per minute, `/auth/login` 10 per minute, `POST /api/checkin/*` 20 per minute. Return 429 `rate_limited`.
- Security headers on API responses: `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`.
- Structured JSON logs in `demo`; never log cookies, tokens, `id_token`, or the HMAC secret.
- Test: the 31st verify request in a minute gets 429.
