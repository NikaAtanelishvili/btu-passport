# BTU AI Skills Digital Passport — Architecture brief

One persistent passport per student, issued as a multi-page PDF on BTU's design, updated in
versions when the university verifies new skills, and verifiable by anyone on a public
blockchain without signing in.

## The parts

| Part | What it does |
| --- | --- |
| **Google Sheet** (BTU's official channel) | Three tabs kept by BTU staff: *Students*, *Skills Catalog*, *Verified Skills*. The system only reads them, plus three status columns it writes next to each skill record. |
| **Admin panel** (web app) | Staff see every passport, version and Sheet record; extras: register a student, a direct award, events with QR check-in. Both channels create the same records and go through the same checks. |
| **API** (FastAPI) | Admin panel, student portal, public verification. |
| **Worker** | Background jobs: Sheet sync, PDF rendering, blockchain anchoring, student emails. |
| **Signer** | A separate small service that holds BTU's issuer key and sends the anchoring transaction. Nothing else ever sees the key. |
| **PostgreSQL** | All data, the job queue and the audit log. Rules such as "one passport per student" and "one award per Sheet record" are database constraints, not just code. |
| **Object storage** (S3 / MinIO) | Each issued PDF, stored under its own SHA-256 fingerprint and never changed. |
| **Blockchain** (Ethereum Sepolia testnet for the demo) | A small registry contract owned by BTU's issuer address. It stores only Merkle roots: no names, no personal data. |

## From a Sheet row to a verified PDF

1. **Read.** Every 60 seconds (`SHEET_SYNC_INTERVAL_SECONDS`), or when an admin presses
   *Sync now*, the worker reads the three tabs in one Google Sheets API call, with a
   service account that BTU shares the Sheet with.
2. **Check.** Each row gets an outcome. Students: created, updated, unchanged, conflict or
   error. Skills: created, updated, unchanged or error. Verified Skills records:
   - only **CONFIRMED** records are processed; PENDING records wait and REJECTED ones are ignored;
   - a record whose student or skill is unknown, whose date is in the future, or that is
     incomplete is an **error**: it changes nothing and is shown to staff;
   - each record's *Record ID* can create at most one award (a database rule), so syncing
     again never adds a skill twice, and a skill the student already holds is a **duplicate**;
   - a record already processed is never changed by a later edit in the Sheet: the edit is
     **flagged** for an admin.
3. **Update the passport.** All new CONFIRMED records of one student in one sync go into
   one database transaction: the awards plus **one** new passport version. One student's
   problem never blocks another's. A new student gets a permanent Passport ID
   (`BTU-AI-000143`) and a first version at once.
4. **Render.** The worker freezes the version's content (holder name, Passport ID, first
   issue date, every skill with its stamp, date and description) and renders the PDF on
   BTU's design: cover, about page, a skill grid of 10 stamps a page, and a detail table
   that continues over as many pages as needed. The PDF carries the version's own
   *verification code* and a QR code to the verify page. Earlier skills, the Passport ID and
   the first issue date are copied unchanged into every new version.
5. **Anchor.** Every few seconds the worker collects the rendered PDFs' SHA-256 fingerprints,
   builds one Merkle tree and the signer writes its root to the registry in one transaction.
   Each version keeps its Merkle proof. Only then does the version become *anchored* and the
   student's latest valid version; if anything fails, the previous version stays the
   latest.
6. **Tell.** The Sheet's `sync_status`, `sync_message` and `synced_at` columns show each
   record's outcome next to the row; the admin page lists every row with links to the
   student and the version; the student gets an email with the new skills.

## Versions

A passport has one permanent **Passport ID** and many **versions** (v1, v2, …). Every version
has its own verification code, PDF fingerprint and blockchain proof, and is kept for good.
Only anchored versions can be downloaded or verified; the newest anchored one is the
*latest*, older ones verify as *authentic but outdated*.

## Verification and BTU's identity

- **By code** (`/v/<code>`, no sign-in): finds the official record of that version and says
  whether it is the latest and whether the issuer is BTU. The page says plainly that this
  confirms the *record*, not a file someone sent.
- **By file** (upload the PDF on `/verify`): the browser computes the file's SHA-256; it must
  match an issued version, and its Merkle proof must lead to a root that BTU's registry
  holds. A one-byte change gives a different fingerprint: *Not valid*. The browser also
  repeats the blockchain check itself, so the result doesn't depend on trusting our server.
- **Issuer.** BTU publishes an issuer file (`/.well-known/ai-passport-issuer.json`, on BTU's
  own domain in production) naming the chain, the registry contract and BTU's issuer
  address. A check passes only if the root is in *that* contract and the contract's owner is
  *that* address; a look-alike registry by someone else fails. For the hackathon the issuer is
  a test identity and the file is served by our verify site.
- **Without BTU.** With the PDF, its `proof.json` and any public blockchain node, anyone can
  check a passport even if BTU's servers are gone.

## Students and privacy

Students sign in with their BTU Google account or a one-time email code and see only their
own passport, versions and downloads. The public verify page shows only what the PDF itself
shows. The blockchain holds only Merkle roots.
