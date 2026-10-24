# BTU AI Skills Passport — System Design

Oct 21, 2026 · @Nikoloz Atanelishvili

## 1. Design summary

The system is a modular monolith: one web frontend, one backend codebase run as an API and a background worker, one PostgreSQL database, and a separate signing service that alone holds BTU's blockchain key. Each issuance run hashes the new PDFs, builds a Merkle tree and anchors its root in one transaction on a registry contract that only BTU's address can write to.

Key decisions, each traced to the requirements doc:

| #   | Decision                                                                                                                                                                                                     | Driven by                    |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------- |
| D1  | Modular monolith, not microservices — 7 days and a small team; only the signer is split out, for security                                                                                                    | NFR-06                       |
| D2  | PostgreSQL is the single source of truth and also the job queue (no Redis)                                                                                                                                   | FR-14, FR-22, NFR-10         |
| D3  | PDFs rendered from an HTML/CSS version of BTU's design, stored by SHA-256 and never overwritten                                                                                                              | FR-16, NFR-08, NFR-13        |
| D4  | One Merkle root per issuance batch on a registry smart contract; only BTU's issuer address may write                                                                                                         | FR-19 – FR-21, NFR-01        |
| D5  | Passwordless email-code sign-in built into the API, roles in our own `user_roles` table                                                                                                                      | FR-01, FR-25, NFR-04, NFR-05 |
| D6  | Two roles plus student: Super admin, Admin; no Auditor (dropped 2026-10-21) — the audit log is read by the Super admin                                                                                       | FR-08, FR-09                 |
| D7  | Verification is public and works by code or by PDF upload; upload verification needs only chain data + the proof                                                                                             | FR-23, NFR-09                |
| D8  | Events are the main source of awards: QR check-in collects participants, Mark as done turns them into one award submission that goes through the same issuance pipeline as a direct award (added 2026-10-21) | FR-26 – FR-33                |

## 2. Architecture

All traffic enters through one proxy; the API is the only component that serves people, and the worker is the only one that talks to the signer.

&#91;embedded content: component architecture · 8 containers + chain\]

The dashed arrow is a reference, not a call: BTU's issuer file names the contract and its owner address, which is what the verify page checks. The verify page also reads the registry directly through a public RPC, so verification does not depend on our API.

## 3. Technology stack

Python on the backend (the team's strongest language), TypeScript only for the UI. Every choice has a fallback that keeps the rest of the design unchanged.

| Layer          | Choice                                                                                            | Why                                                                                                      | Fallback                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Frontend       | Next.js + TypeScript, Tailwind, shadcn/ui, react-hook-form + zod                                  | Polished admin forms with field-level errors fast; one app with three areas: `/admin`, `/me`, `/verify`  | FastAPI + Jinja + HTMX if nobody on the team knows React                              |
| Backend API    | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic                                             | Pydantic models re-validate every form server-side (FR-04); typed API docs for free                      | Django + DRF                                                                          |
| Worker         | Same codebase, separate process; claims jobs with `SELECT … FOR UPDATE SKIP LOCKED`               | No extra queue service; jobs are transactional with the data (FR-14)                                     | Celery + Redis                                                                        |
| Database       | PostgreSQL 16                                                                                     | Unique constraints enforce idempotency; JSONB for audit diffs                                            | —                                                                                     |
| File storage   | MinIO (S3 API), keys = PDF SHA-256                                                                | Immutable, content-addressed (NFR-08); same code works on S3 in production                               | Docker volume                                                                         |
| PDF            | Jinja2 HTML/CSS template → WeasyPrint; `segno` for QR                                             | Pure Python, paginates repeating skill blocks, embeds fonts (NFR-12)                                     | Playwright (Chromium) print-to-PDF                                                    |
| Font           | Noto Sans Georgian, or BTU's brand font if it covers Georgian                                     | Georgian names must render (NFR-12)                                                                      | —                                                                                     |
| Identity       | Email-code login in FastAPI (hashed 6-digit codes, rate limits); SMTP for sending, Mailpit in dev | No identity provider to run or configure; BTU SSO can be added later behind the same session layer (Q11) | Sign in with Google limited to btu.edu.ge (only if BTU mail runs on Google Workspace) |
| Smart contract | Solidity + Foundry, OpenZeppelin `Ownable`                                                        | Fast tests, scripted deploy                                                                              | Hardhat                                                                               |
| Chain          | Local Anvil for development; a public EVM testnet (e.g. Sepolia) for the demo                     | Free, public, verifiable by the jury on a block explorer                                                 | Polygon testnet                                                                       |
| Chain client   | web3.py inside the signing service                                                                | Same language as the backend                                                                             | ethers.js                                                                             |

## 4. Data model

Seventeen tables; the requirements are enforced by database constraints, not only by code, so a bug or a double-click cannot break them. Relationships: student 1–1 passport 1–n versions; student 1–n awards; version n–n awards; batch 1–n versions.

| Table               | Key columns                                                                                                                                                            | Constraints that matter                                                                              |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `students`          | `student_id` PK (BTU-T-0001), first/last name, `email`, program, level, status                                                                                         | `email` UNIQUE (FR-02)                                                                               |
| `passports`         | `passport_id` PK (BTU-AI-000125), `student_id`, frozen first/last name, `first_issued_on`, `latest_version_id`                                                         | `student_id` UNIQUE → one passport per student (FR-10); frozen columns never updated (FR-11)         |
| `skill_categories`  | `category` PK, `badge_code`, `stamp_image_key`                                                                                                                         | 3 rows; badge derived from here (FR-17)                                                              |
| `skills`            | `skill_id` PK (SKL-001), name, category, description                                                                                                                   | Catalog only — issued versions keep their own copy (FR-07)                                           |
| `award_submissions` | `submission_id` PK, `idempotency_key`, `submitted_by`, time                                                                                                            | `idempotency_key` UNIQUE → resubmits are no-ops (FR-14)                                              |
| `skill_awards`      | `award_id` PK, `student_id`, `skill_id`, `date_earned`, `submission_id`, `awarded_by`                                                                                  | UNIQUE (`student_id`, `skill_id`); CHECK `date_earned ≤ today` (FR-04)                               |
| `passport_versions` | `version_id` PK, `passport_id`, `version_no`, `status`, `content_json`, `verification_code`, `pdf_sha256`, `pdf_key`, `batch_id`, `merkle_proof`, `issued_at`, `error` | UNIQUE (`passport_id`, `version_no`), UNIQUE `verification_code`, UNIQUE `pdf_sha256` (FR-12, FR-18) |
| `version_awards`    | `version_id`, `award_id`                                                                                                                                               | Which awards each version contains                                                                   |
| `anchor_batches`    | `batch_id` PK, `merkle_root`, `leaf_count`, `chain_id`, `contract_address`, `tx_hash`, `block_number`, status                                                          | `merkle_root` UNIQUE (FR-19)                                                                         |
| `jobs`              | `job_id`, `type`, `payload`, `status`, `attempts`, `run_after`, `last_error`                                                                                           | Retry queue (FR-22)                                                                                  |
| `users`             | `user_id` PK, `email`                                                                                                                                                  | `email` UNIQUE                                                                                       |
| `user_roles`        | `user_id`, `role` ∈ {SUPER_ADMIN, ADMIN}                                                                                                                               | Allowlist for admin access (FR-01, FR-08)                                                            |
| `audit_log`         | `id`, `actor_user_id`, `action`, `entity`, `entity_id`, `before`, `after`, `at`                                                                                        | App's DB role has INSERT only, no UPDATE/DELETE (FR-09, NFR-10)                                      |
| `sessions`          | hashed session id, user_id, expires_at, last_seen_at                                                                                                                   | Server-side sessions; deleting a row logs the user out (NFR-04)                                      |
| `login_codes`       | code_id PK, email, code_hash, expires_at, attempts, used_at, requested_ip                                                                                              | Only the hash is stored; 10-minute expiry, single use, dead after 5 wrong tries (FR-01, NFR-07)      |

**Added for events (2026-10-21)**

| Table                | Key columns                                                                                                                                                                                        | Constraints that matter                                                                                                                                                        |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `events`             | `event_id` PK, `name`, `skill_id`, `description`, `starts_at`, `ends_at`, `location`, `checkin_opens_at`, `checkin_closes_at`, `status`, `qr_secret`, `created_by`, `completed_by`, `completed_at` | CHECK `ends_at > starts_at` and `checkin_closes_at > checkin_opens_at`; `skill_id` can't change once a participant exists (FR-26); no DELETE when `status = COMPLETED` (FR-27) |
| `event_participants` | `event_id`, `email`, `student_id` (null = Unregistered), `checked_in_at`, `method` (QR / MANUAL), `added_by`, `removed_at`                                                                         | UNIQUE (`event_id`, `email`) → one check-in per person (FR-29); removal is a timestamp, not a delete, so the history stays (FR-31)                                             |

Two columns change elsewhere: `award_submissions.event_id` (nullable, UNIQUE) makes Mark as done idempotent (FR-32), and `skills` and `skill_categories` get `archived_at` so used items are archived, not deleted (FR-35).

**`content_json` is the passport.** It is a frozen snapshot of everything printed — names, Passport ID, first-issued date, each skill's name, description, badge and date, version number, verification code. The PDF is rendered from it, so later catalog or student edits can never change an issued version.

**Seed import.** Sheet columns A–I fill `students` and `passports`, J–P fill `skills` and `skill_awards`, Q–T map to `passport_versions`. The seed's SYNCED V1 rows become version 1 with status `LEGACY`: shown in history, never verifiable (requirements Q2 default).

## 5. Issuance flow and version lifecycle

The admin's request only records intent and returns immediately; rendering and anchoring happen in the worker, so a slow chain never blocks the form and a failure never loses an award.

### Flow (UC-01)

1. **API, one DB transaction** — check the admin role; re-validate with Pydantic; insert `award_submissions` (idempotency key from the form, FR-14); insert `skill_awards`; lock each affected `passports` row (`SELECT … FOR UPDATE`) and insert one `passport_versions` row per student with `version_no = latest + 1`, status `PENDING` (FR-13), and record in `version_awards` every award the student holds at that moment; enqueue one `ISSUE_VERSION` job per version; write `audit_log`. Return `202 Accepted` with the version IDs.
2. **Worker: build** — snapshot the version's `version_awards` (not "all awards now", so two quick submissions can't bleed into each other) into `content_json`, sorted by `date_earned` then `award_id` (back-dated awards land in the right place); generate the verification code.
3. **Worker: render** — template → PDF, SHA-256 of the final bytes, upload to storage under that hash; status `RENDERED`.
4. **Worker: batch** — an `ANCHOR_BATCH` job takes every `RENDERED` version (up to 1,024), builds the Merkle tree, creates an `anchor_batches` row; versions go to `ANCHORING`.
5. **Signer: anchor** — submits the root to the registry contract and waits for confirmation; returns tx hash and block number.
6. **Worker: publish** — stores each version's Merkle proof, marks versions `ANCHORED`, moves `passports.latest_version_id` forward (only if the new `version_no` is higher). The admin panel now shows "Issued vN".

**Batch timing.** For the demo, the batch job runs as soon as a submission's PDFs are rendered (one transaction per submission). In production it runs every 10 minutes, so 500 students awarded in a day may share a handful of transactions (NFR-01, NFR-02).

**Failures.** Render error → `FAILED` with the message. Chain error → versions return to `RENDERED`, the job retries with backoff (1, 2, 4, 8, 16 min); after 5 attempts → `FAILED`. The admin's Retry button re-queues a failed version (FR-06, FR-22). Only `ANCHORED` versions can be downloaded or verified.

**Statuses:** `LEGACY` (seed V1, never verifiable) · `PENDING` · `RENDERED` · `ANCHORING` · `ANCHORED` · `FAILED`. "Superseded" is not stored — it is computed as `version_no < latest`.

&#91;embedded content: passport version lifecycle · 5 states\]

`LEGACY` (the seed's V1) sits outside this flow: imported for history, never rendered, anchored or verifiable.

### Events feed the same pipeline

An event adds two steps in front of the flow above; everything from "Worker: build" on is unchanged.

- **QR token.** `token = base32(HMAC-SHA256(qr_secret, event_id ‖ floor(now / 30 s)))`, first 16 characters. The presenter view fetches the current token from the server every 30 s, so the secret never reaches a browser. Check-in accepts the current and the previous window (FR-28).
- **Check-in.** Inserts into `event_participants`, matching the signed-in email to `students`; no match → `student_id` null (Unregistered, FR-30). A repeat scan hits the UNIQUE constraint and returns the existing row.
- **Mark as done.** One DB transaction: check status Check-in closed and no Unregistered rows; insert an `award_submissions` row with `event_id`; insert `skill_awards` for participants who don't hold the skill (date earned = event date); create the `PENDING` versions and jobs exactly as in step 1 above; set the event to `COMPLETED`. A second call fails the UNIQUE on `event_id` and returns the first result (FR-32).

## 6. Blockchain design

One small contract, written to only by BTU's address, stores Merkle roots; the PDF's SHA-256 is a leaf under one of them. A verifier needs three things: the file, its Merkle proof, and BTU's published contract address — no personal data ever touches the chain (NFR-03).

### Registry contract

```solidity
contract PassportRegistry is Ownable2Step {          // owner = BTU issuer address
    mapping(bytes32 => uint256) public anchoredAt;    // Merkle root => block timestamp
    mapping(bytes32 => bool)    public revoked;       // leaf => revoked (Could)

    event Anchored(bytes32 indexed root, uint32 leafCount);
    event Revoked(bytes32 indexed leaf);

    function anchor(bytes32 root, uint32 leafCount) external onlyOwner {
        require(anchoredAt[root] == 0, "already anchored");
        anchoredAt[root] = block.timestamp;
        emit Anchored(root, leafCount);
    }

    function revoke(bytes32 leaf) external onlyOwner {
        revoked[leaf] = true;
        emit Revoked(leaf);
    }
}
```

Because only the owner can call `anchor`, "this root is in the contract" already means "BTU's key wrote it". `Ownable2Step` lets BTU rotate the key without redeploying. One anchor costs a fixed amount of gas whatever the batch size, so 1 or 1,000 passports cost the same.

### Merkle tree

- Leaf = `keccak256(keccak256(abi.encode(pdf_sha256)))` — the OpenZeppelin `StandardMerkleTree` format; double hashing blocks second-preimage tricks.
- Pairs sorted before hashing, so a proof is just a list of sibling hashes, no left/right flags.
- Built in Python by the worker; the verify page checks proofs in the browser. Shared test vectors keep the two implementations identical.
- A batch of one: root = leaf, empty proof.

### Issuer identity (FR-21)

BTU publishes `https://btu.edu.ge/.well-known/ai-passport-issuer.json` = `{ chainId, contractAddress, issuerAddress }`. The issuer check passes only if the anchor is in that contract _and_ `owner()` equals that address. Publishing on BTU's own domain is what ties the key to BTU rather than to "some wallet". For the demo, our verify site serves the file and we state that production moves it to BTU's domain.

### Verification algorithm

1. **Find the version.** By code: `GET /api/verify/{code}`. By file: the browser computes the SHA-256 _locally_ and sends only the hash — the PDF never leaves the verifier's machine.
2. **Document check.** Recompute the leaf from the hash, fold the proof up to the root, call `anchoredAt(root)` on the contract through a public RPC; non-zero = anchored.
3. **Issuer check.** Contract address and `owner()` match BTU's published file.
4. **Status.** `revoked(leaf)` false; `version_no` = latest → **Valid**, else **Authentic, superseded by vN**.

| Outcome                                               | Verdict shown                                                |
| ----------------------------------------------------- | ------------------------------------------------------------ |
| All checks pass, latest version                       | Valid — issued by BTU, vN, date                              |
| All pass, newer version exists                        | Authentic, superseded by vN (link to latest)                 |
| Hash not found / proof doesn't reach an anchored root | Not valid — this file does not match any passport BTU issued |
| Code not found                                        | Unknown code                                                 |
| Anchor not in BTU's contract                          | Not issued by BTU                                            |
| Leaf revoked                                          | Revoked by BTU                                               |

**Without BTU's server (NFR-09).** Each version also has a downloadable `proof.json` (hash, proof, root, tx hash, contract, chain). With the PDF, that file and a public RPC, a 50-line open-source script checks steps 2–3 independently. Only "is it the latest?" needs our server.

## 7. API design

REST over JSON, four route groups with one guard each (the fourth, `/api/checkin/*`, is described under the event endpoints), so authorization is decided by where a route lives: `/api/admin/*` needs an admin role, `/api/me/*` needs a signed-in student and is scoped to them, `/api/verify/*` is public and rate-limited.

| Method           | Path                                      | Who         | Purpose                                                                               | FR                         |
| ---------------- | ----------------------------------------- | ----------- | ------------------------------------------------------------------------------------- | -------------------------- |
| POST             | `/auth/request-code`, `/auth/verify-code` | anyone      | Emails a 6-digit code; checks it and creates the server session                       | FR-01, FR-25               |
| POST             | `/auth/logout`                            | signed in   | Deletes session                                                                       | —                          |
| GET              | `/api/admin/students?q=`                  | Admin       | Search students with passport status                                                  | FR-06                      |
| POST             | `/api/admin/students`                     | Admin       | Register student + create passport                                                    | FR-02, FR-10               |
| PATCH            | `/api/admin/students/{id}`                | Admin       | Edit record; frozen fields flagged, never reissued                                    | FR-11                      |
| GET              | `/api/admin/skills`                       | Admin       | Catalog for the award form                                                            | FR-03                      |
| POST, PATCH      | `/api/admin/skills`                       | Super admin | Edit catalog                                                                          | FR-07                      |
| POST             | `/api/admin/awards/preview`               | Admin       | Validate only; returns resulting version per student                                  | FR-04                      |
| POST             | `/api/admin/awards`                       | Admin       | Save awards, create versions, queue jobs; needs `Idempotency-Key` header; returns 202 | FR-03, FR-05, FR-13, FR-14 |
| GET              | `/api/admin/versions?status=FAILED`       | Admin       | Issuance status list                                                                  | FR-06                      |
| POST             | `/api/admin/versions/{id}/retry`          | Admin       | Re-queue a failed version                                                             | FR-22                      |
| GET, PUT, DELETE | `/api/admin/roles`                        | Super admin | List, grant, revoke Admin                                                             | FR-08                      |
| GET              | `/api/admin/audit-log`                    | Super admin | Read-only log                                                                         | FR-09                      |
| GET              | `/api/me/passport`                        | Student     | Own passport + version list                                                           | FR-15, FR-25               |
| GET              | `/api/me/versions/{n}/pdf`, `/proof.json` | Student     | Download own PDF and proof                                                            | FR-25                      |
| GET              | `/api/verify/{code}`                      | public      | Official data + verdict                                                               | FR-23, FR-24               |
| POST             | `/api/verify/hash`                        | public      | Body `{sha256}`; verdict for an uploaded file                                         | FR-20, FR-23               |
| GET              | `/api/verify/{code}/pdf`                  | public      | Official PDF to compare against                                                       | FR-23                      |
| GET              | `/.well-known/ai-passport-issuer.json`    | public      | Issuer identity file                                                                  | FR-21                      |

**Event and catalog endpoints (added 2026-10-21)**

| Method                   | Path                                               | Who                       | Purpose                                              | FR           |
| ------------------------ | -------------------------------------------------- | ------------------------- | ---------------------------------------------------- | ------------ |
| GET                      | `/api/admin/events`, `/api/admin/events/{id}`      | Admin (view), Super admin | List and detail                                      | FR-26        |
| POST, PATCH, DELETE      | `/api/admin/events[/{id}]`                         | Super admin               | Create, edit, delete (409 once completed)            | FR-26, FR-27 |
| POST                     | `/api/admin/events/{id}/open`, `/close`, `/reopen` | Super admin               | Check-in window overrides                            | FR-27        |
| GET                      | `/api/admin/events/{id}/qr`                        | Super admin               | Current QR token for presenter view                  | FR-28        |
| GET                      | `/api/admin/events/{id}/participants`              | Admin (view), Super admin | Live list, polled every 3 s                          | FR-31        |
| POST, DELETE             | `/api/admin/events/{id}/participants[/{email}]`    | Super admin               | Manual add, remove                                   | FR-31        |
| POST                     | `/api/admin/events/{id}/complete`                  | Super admin               | Mark as done; returns the awards created and skipped | FR-32        |
| GET                      | `/api/checkin/{event_id}?t=`                       | Signed-in user            | Event summary for the confirm screen                 | FR-29        |
| POST                     | `/api/checkin/{event_id}`                          | Signed-in user            | Body `{t}`; record check-in                          | FR-29, FR-30 |
| GET                      | `/api/me/events`                                   | Student                   | Own check-ins with status                            | FR-33        |
| GET, POST, PATCH, DELETE | `/api/admin/categories[/{id}]`                     | Admin (view), Super admin | Categories; delete only if unused, else archive      | FR-34, FR-35 |
| POST                     | `/api/admin/categories/{id}/stamp`                 | Super admin               | Upload stamp image to MinIO                          | FR-34        |

`/api/checkin/*` is a fourth route group: any signed-in BTU user, so Unregistered students can still be recorded.

Errors use one shape, `{ "error": code, "fields": { name: message } }`, so the form can show field-level messages. A wrong ID under `/api/me/*` returns 404, not 403, so it doesn't confirm the passport exists.

## 8. Security design

Three boundaries: who you are (a one-time code sent to your BTU email), what you may do (our role table, checked on every request), and who can touch BTU's key (only the signer, on a private network). Each row below is a control we build, mapped to the threat it stops.

### Sign-in flow

1. The login page posts the email to `/auth/request-code`. The API checks the domain against `ALLOWED_EMAIL_DOMAINS`, applies rate limits (per email and per IP), stores a hash of a random 6-digit code in `login_codes` with a 10-minute expiry, and emails the code over SMTP.
2. The user types the code; the page posts it to `/auth/verify-code`. A wrong code increments `attempts`; the fifth wrong try or the expiry kills it.
3. On a match, the API marks the code used, upserts `users` by email, creates a row in `sessions`, and sets the cookie.
4. Each request: session → user → role from `user_roles` (cached ≤ 60 s); a student is matched to `students` by email.
5. Admins have no second factor (accepted trade-off): whoever controls an admin's inbox can sign in as that admin. Revoking the role deletes their sessions, which locks them out at once.

### Controls

| Threat                                | Control                                                                                                                                                                                                 | Req            |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| Non-admin reaches admin features      | Router-level guard on `/api/admin/*`; UI hiding is extra, not the defence                                                                                                                               | FR-01, NFR-05  |
| Student reads another passport (IDOR) | `/api/me/*` queries filter by the session's `student_id`; IDs in the URL are never trusted                                                                                                              | NFR-05         |
| Revoked admin keeps access            | Role re-read within 60 s; revocation also deletes their `sessions` rows                                                                                                                                 | FR-08          |
| Session theft via script              | `__Host-` cookie, HttpOnly, Secure, SameSite=Lax; 8 h absolute, 30 min idle for admins                                                                                                                  | NFR-04, NFR-07 |
| Guessing or flooding login codes      | Codes stored hashed; 10-minute expiry, single use, 5 attempts; rate limits per email and per IP on code requests; email domain checked on the server                                                    | FR-01, NFR-07  |
| Cross-site form submission            | CSRF token required in a header on every POST/PUT/PATCH/DELETE                                                                                                                                          | NFR-07         |
| Bypassing the form                    | Same Pydantic schema validates every request on the server                                                                                                                                              | FR-04          |
| Issuer key theft                      | Signer runs in its own container, no public port, reads the key from a Docker secret, and exposes only `anchor`/`revoke` to the worker (authenticated with a shared HMAC secret). Admins never reach it | NFR-06         |
| Scraping passports by guessing codes  | Codes = 10 random Crockford base32 characters (50 bits), rate limit 30 verify requests/min per IP                                                                                                       | NFR-07         |
| Tampering with the audit trail        | App DB role has INSERT only on `audit_log`                                                                                                                                                              | NFR-10         |
| Personal data leaking via verify      | Response lists only name, Passport ID, version, date, skills; PDFs hashed in the browser, never uploaded                                                                                                | NFR-03         |
| CORS mistakes                         | Frontend and API on one origin behind a reverse proxy (`/api` → FastAPI), so no CORS is configured at all                                                                                               | NFR-07         |
| QR photo shared with absent students  | 30 s rotating HMAC token generated on the server; only the current and previous accepted; super admin reviews the list before Mark as done                                                              | FR-28, FR-31   |

## 9. PDF generation

BTU's design is rebuilt once as an HTML/CSS template; WeasyPrint turns `content_json` into the PDF, and the stored bytes — never a re-render — are what gets hashed and verified.

### Page structure (final layout follows BTU's design, requirements Q7)

| Page                    | Content                                                                                                | Changes between versions? |
| ----------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------- |
| Cover                   | BTU branding, holder name, Passport ID, first-issued date                                              | No (frozen, FR-11)        |
| Version page            | Version number, issue date, verification code, QR, verify URL                                          | Yes                       |
| Skill pages (1 or more) | Repeating block: badge stamp, skill name, date earned, description; flows onto new pages automatically | Yes (FR-17)               |
| Last page               | How to verify, issuer address and contract                                                             | No                        |

Every page footer: Passport ID · vN · verification code · page x of y — so a single printed page still points to its passport.

### Details

- **Pagination:** skill blocks use `break-inside: avoid`; 1 to 16 skills just produce more pages, no fixed coordinates.
- **Verification code:** 10 random Crockford base32 characters shown as `K7QM-3XWP-9D` (no I, L, O, U, so it's easy to type); generated before rendering, never derived from the hash.
- **QR:** encodes `https://<verify-host>/v/<code>`.
- **Badges:** three stamp images from BTU, chosen by the skill's category.
- **Fonts:** embedded Georgian-capable font; UTF-8 throughout.
- **Determinism (NFR-13):** PDF metadata dates set from `issued_at` in `content_json`, no random IDs, WeasyPrint version pinned. A test renders the same version twice and compares SHA-256.
- **Throughput:** measure render time on day 2; if 500 PDFs per run (NFR-02) is too slow for one worker, run more worker processes — the job queue already allows it.

## 10. Deployment and environments

Everything runs from one `docker compose up`: seven containers on one machine for the demo (plus Mailpit in development), each of which can later move to its own host without code changes.

| Service   | Image / runtime                      | Exposed                    | Notes                                                                            |
| --------- | ------------------------------------ | -------------------------- | -------------------------------------------------------------------------------- |
| `proxy`   | Caddy                                | 443 (public)               | TLS; routes `/api`, `/auth`, `/.well-known` → api, everything else → web         |
| `web`     | Next.js                              | internal                   | Admin panel, student portal, verify page                                         |
| `api`     | FastAPI (Uvicorn)                    | internal                   | Same image as worker                                                             |
| `worker`  | FastAPI codebase, `python -m worker` | none                       | Scale with `--scale worker=N`                                                    |
| `signer`  | Python + web3.py                     | private network only       | Key from a Docker secret; only talks to worker and chain RPC                     |
| `db`      | PostgreSQL 16                        | internal                   | Volume + nightly `pg_dump`                                                       |
| `storage` | MinIO                                | internal                   | Bucket `passports`, versioning on                                                |
| `mail`    | Mailpit (dev only)                   | 8025, dev only (web inbox) | Catches every outgoing email; the demo sends through a real SMTP account instead |

| Environment         | Chain                                                       | Identity                                   | Data                                |
| ------------------- | ----------------------------------------------------------- | ------------------------------------------ | ----------------------------------- |
| Local dev           | Anvil (local, instant blocks)                               | Email codes, caught by Mailpit             | Seed import of the 18 test students |
| Demo                | Public EVM testnet; contract verified on the block explorer | Email codes over a real SMTP account       | Seed + live awards during the demo  |
| Production (future) | Mainnet or a low-fee L2 — BTU decision                      | Email codes via BTU mail, or BTU SSO later | Real data, HSM/KMS for the key      |

**Repository layout:** `web/` (Next.js) · `backend/` (api, worker, signer as packages) · `contracts/` (Foundry) · `templates/` (passport HTML/CSS, stamps, fonts) · `infra/` (compose, Caddyfile) · `seed/` (importer + the test CSV).

## 11. Traceability and design risks

Every functional requirement lands in a named part of this design and is proven by an acceptance scenario from the requirements doc (A1–A12).

| Requirements        | Where in the design                                                                                       | Proven by                                   |
| ------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| FR-01, FR-08        | `/api/admin/*` guard, `user_roles`, email-code login (§7, §8)                                             | A11, A12                                    |
| FR-02, FR-10, FR-11 | `students`, `passports` (UNIQUE `student_id`, frozen columns) (§4)                                        | A1                                          |
| FR-03 – FR-05       | Award form, `/awards/preview`, `/awards` (§7)                                                             | A2, A9, A10                                 |
| FR-06, FR-22        | Version statuses, `jobs`, retry endpoint (§5)                                                             | Failed-anchor demo (stop the signer, retry) |
| FR-07, FR-09        | `skills` endpoints, append-only `audit_log` (§4, §7)                                                      | A12 (log entry)                             |
| FR-12 – FR-15       | `passport_versions`, `version_awards`, idempotency key, `latest_version_id` (§4, §5)                      | A2, A3, A6                                  |
| FR-16 – FR-18       | Template + WeasyPrint, code generator (§9)                                                                | A1                                          |
| FR-19 – FR-21       | Registry contract, signer, Merkle tree, issuer file (§6)                                                  | A4, A5, A7                                  |
| FR-23, FR-24        | Verify page, `/api/verify/*` (§6, §7)                                                                     | A4 – A6                                     |
| FR-25               | `/api/me/*` scoped by session (§7, §8)                                                                    | A8                                          |
| FR-26 – FR-35       | events, event_participants, QR token, Mark as done transaction, event and category endpoints (§4, §5, §7) | A13 – A16                                   |

| Risk                                                 | Mitigation                                                                                                                     |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Testnet RPC or faucet fails on demo day              | Get test funds on day 1; record a backup demo video; Anvil as last resort                                                      |
| BTU's design is hard to reproduce in HTML/CSS        | Start the template on day 2 in parallel; static pages can be exported from the design and only the dynamic pages generated     |
| Python and browser Merkle code disagree              | Shared test vectors run in both test suites                                                                                    |
| Login emails don't arrive (spam filter, SMTP limits) | Test with Mailpit first; for the demo use a sender you control and check spam folders; in dev only, the API also logs the code |
| A genuine PDF re-saved by a viewer shows "Not valid" | Verdict text points to the official copy via the code lookup                                                                   |
| Could-haves crowd out Musts                          | Start Could items only after A1–A12 pass                                                                                       |

**Next SDLC step:** implementation, starting with sprint 1's thin slice — admin login → award form → one PDF → anchored on Anvil → verified by upload.
