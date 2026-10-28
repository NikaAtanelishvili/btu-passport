# BTU AI Skills Passport — Addendum: Mandatory Gaps

Oct 28, 2026 · @Nikoloz Atanelishvili

The full hackathon spec makes Google Sheets the mandatory data source and lists demo scenarios the current build can't show; this addendum adds them as milestone M11 without changing the existing design documents, and M11 runs before M10 (hosting).

## 1. Gaps

Eight mandatory items are missing or partial; everything else in the spec is already met. Source: the hackathon's "Technical Assignment" (FR 1–10, MVP table, deliverables) and "Test Environment and Data Protection Terms".

| #   | Requirement (source)                                                                                                                                          | Current build                                             | Closed by           |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ------------------- |
| G1  | Google Sheets is the main data source; the system reads it, detects new or changed records and processes them automatically (FR 2, 4.1–4.2, Stage 4–5)        | One-time CSV seed import; manual entry in the admin panel | SH-01 – SH-07       |
| G2  | Three registers: Students, Skills Catalog, Verified Skills (Data terms)                                                                                       | One flattened CSV                                         | SH-02               |
| G3  | Only CONFIRMED records update a passport; PENDING and REJECTED never do (Data terms, 4.6)                                                                     | No status handling                                        | SH-04               |
| G4  | Each assignment has a Record ID; repeated sync never adds a skill twice (4.6, MVP "Repeated data synchronization")                                            | `legacy_record_id UNIQUE` exists for the seed only        | SH-04               |
| G5  | An invalid student identifier or incomplete record halts that record, changes nothing, and is logged as an error (4.3, 4.6, MVP "Invalid student identifier") | Not applicable today                                      | SH-04, SH-05        |
| G6  | It must be possible to tell whether a specific record was processed successfully (4.6)                                                                        | Audit log covers admin actions only                       | SH-05, SH-06, SH-07 |
| G7  | A new student gets a passport and an initial multi-page PDF (FR 1, Stage 1–3, MVP "Adding a new student", "Initial Passport generation")                      | First PDF only after the first award                      | SH-08               |
| G8  | Verification results clearly separate "an official record exists" from "this submitted file is authentic" (FR 7)                                              | Code lookup can read like a file check                    | SH-09               |

Deliverables that need writing, not code: a brief system architecture (deliverable 2), the Google Sheets demo (3) and the scaling vision for 5,000+ passports a year (5); see section 7. Optional items picked up cheaply: student notifications (SH-10) and Excel import (SH-11).

## 2. Decisions

The admin panel stays the primary way staff work; Google Sheets is added as a second, mandated intake channel that feeds the same pipeline. Both channels create the same records, run the same checks and produce versions through the same worker, so nothing downstream (PDF, anchoring, verify) changes.

| #   | Decision                                                                                                                                                                                 | Why                                                                                                                   |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| D1  | Sheets → system is one-way and mandatory. The system never deletes or rewrites staff data in the Sheet                                                                                   | Spec: the Sheet holds data the university already verified; the system processes it, it doesn't decide                |
| D2  | Optional write-back of processing status only (three system columns on the Verified Skills tab), behind `SHEET_WRITEBACK=true`                                                           | Staff see each row's result where they typed it (G6); off by default so read-only access also works                   |
| D3  | Identity keys: students by `student_id`, skills by `skill_code`, assignments by `record_id`. The system generates Passport ID, version and verification code; the Sheet never holds them | Data terms: these are system-managed                                                                                  |
| D4  | Admin panel and Sheet share one record space. A skill already awarded through the panel or an event makes the matching Sheet record a "duplicate", not a second award                    | One skill per student is already a database rule                                                                      |
| D5  | Every new student gets a passport and an initial version V1 at creation, through either channel, even with zero skills. Frozen fields are set at V1                                      | Spec FR 1 and MVP "Adding a new student". This reverses the earlier "first issue at first award" deviation; record it |
| D6  | Processed records are immutable. Edits to a processed row (date, skill, status) are flagged "changed after processing" and not applied                                                   | Spec 4.5: updates must never alter previously verified skills                                                         |
| D7  | A record that goes CONFIRMED → REJECTED after processing is flagged for an admin; no automatic revocation                                                                                | Revocation is out of scope; the flag keeps it visible                                                                 |
| D8  | All CONFIRMED records for one student in one sync produce one new version, not one per record                                                                                            | Fewer PDFs and leaves at scale (FR 10)                                                                                |
| D9  | Events and direct awards stay as admin-panel extras and are presented as such; the Sheet is presented as the university's official channel                                               | Spec scope; keeps your cleaner UX                                                                                     |
| D10 | A pluggable source: the Google Sheet in dev and demo, plus a file source (the same three tabs as an .xlsx or CSV folder) for tests and the optional Excel import                         | Tests run without network; Excel import comes almost free                                                             |

**Precedence when both channels touch the same student:** the Sheet may update a student's mutable fields (program, level, status). A different email or a different name after V1 is not applied; it is logged as a conflict for an admin, because the email is the login identity and the name is frozen on issued passports.

## 3. Your manual setup

About 20 minutes in total, in the Google Cloud project you already created (`btu-passport`). Do part A before handing this doc to Claude Code; do part B once SH-02 has produced the import files. The agent never needs to see the key.

**A. Before M11 starts**

- [ ] In Google Cloud, open **APIs & Services → Library**, search **Google Sheets API**, and click **Enable**.
- [ ] Open **IAM & Admin → Service Accounts → Create service account**. Name it `passport-sheets-sync`. Skip the optional role and user steps.
- [ ] Open the new account → **Keys → Add key → Create new key → JSON**. Save the downloaded file as `secrets/google-sheets-sa.json` in the repo. Check it is ignored: `git check-ignore secrets/google-sheets-sa.json` must print the path.
- [ ] Copy the service account's email (it ends in `.iam.gserviceaccount.com`).
- [ ] Add to `.env`: `GOOGLE_SHEETS_CREDENTIALS_FILE=secrets/google-sheets-sa.json`.

**B. After SH-02 (the agent creates `seed/sheets/students.csv`, `skills_catalog.csv`, `verified_skills.csv`)**

- [ ] If the organizers gave your team its own copy of the test Sheet, use that copy and tell the agent its tab names and header row; SH-01 adds a column-mapping file for it. Otherwise create a new Google Sheet named **BTU Passport — Test Data**.
- [ ] For a new Sheet: make three tabs named exactly `Students`, `Skills Catalog`, `Verified Skills`. In each tab, **File → Import → Upload** the matching CSV and choose **Replace current sheet**.
- [ ] Click **Share**, paste the service account's email, give it **Editor** (needed for write-back, D2; Viewer works if write-back stays off), untick "Notify people", and click **Share**.
- [ ] Copy the Sheet ID from its URL: the part between `/d/` and `/edit`.
- [ ] Add to `.env`: `GOOGLE_SHEETS_ID=<that ID>`, `SHEET_WRITEBACK=true`.
- [ ] Tell the agent "Sheet is ready".

**C. For the demo host (M10)**

- [ ] Railway can't hold a file, so put the JSON key's full content into a variable `GOOGLE_SHEETS_CREDENTIALS_JSON` instead of the file (SH-01 supports both). Add `GOOGLE_SHEETS_ID` and `SHEET_WRITEBACK` the same way.

## 4. Sheet structure

Three tabs with a header row in row 1; one record per row. Headers are matched case-insensitively after trimming; extra columns are ignored, a missing required column fails the whole tab with a clear error. Blank rows are skipped. A row that fails validation is an **error** for that row only; other rows still process.

**Students**

| Column            | Required | Rule                                                            | Maps to                    |
| ----------------- | -------- | --------------------------------------------------------------- | -------------------------- |
| `student_id`      | yes      | `BTU-T-` + 4 or more digits; unique in the tab                  | `students.student_id`      |
| `first_name`      | yes      | 1–80 characters, Georgian allowed                               | `students.first_name`      |
| `last_name`       | yes      | 1–80 characters                                                 | `students.last_name`       |
| `email`           | yes      | valid, lower-cased, domain in `ALLOWED_EMAIL_DOMAINS`, unique   | `students.email`           |
| `program`         | yes      | non-empty, at most 120 characters (same rule as the admin form) | `students.program`         |
| `education_level` | yes      | `BACHELOR`, `MASTER` or `DOCTORAL`                              | `students.education_level` |
| `status`          | yes      | `ACTIVE` or `GRADUATE`                                          | `students.status`          |

**Skills Catalog**

| Column        | Required | Rule                                                                            | Maps to                                       |
| ------------- | -------- | ------------------------------------------------------------------------------- | --------------------------------------------- |
| `skill_code`  | yes      | `SKL-` + 3 or more digits; unique                                               | `skills.skill_id`                             |
| `name`        | yes      | at most 80 characters, unique                                                   | `skills.name`                                 |
| `category`    | yes      | an existing category name (`AI Skill`, `AI Applied Skill`, `AI Advanced Skill`) | `skills.category_id`                          |
| `description` | yes      | at most 300 characters                                                          | `skills.description`                          |
| `badge_code`  | no       | if present, must equal the category's badge code (`BDG-AI-001` … `003`)         | check only; the stamp comes from the category |

**Verified Skills**

| Column           | Required | Rule                                                         | Maps to                                           |
| ---------------- | -------- | ------------------------------------------------------------ | ------------------------------------------------- |
| `record_id`      | yes      | `REC-` + 4 or more digits; unique in the tab                 | idempotency key (`skill_awards.source_record_id`) |
| `student_id`     | yes      | must exist in the system (after this sync's Students step)   | the student and their passport                    |
| `skill_code`     | yes      | must exist and not be archived                               | the skill                                         |
| `date_earned`    | yes      | `YYYY-MM-DD` or `DD.MM.YYYY`; not in the future (`TIMEZONE`) | `skill_awards.date_earned`                        |
| `status`         | yes      | `CONFIRMED`, `PENDING` or `REJECTED`                         | only CONFIRMED is processed                       |
| `earned_through` | no       | at most 120 characters                                       | the PDF's "Earned through" column                 |
| `sync_status`    | system   | written by the system when write-back is on                  | see section 5                                     |
| `sync_message`   | system   | short reason, e.g. "Unknown student BTU-T-9999"              | see section 5                                     |
| `synced_at`      | system   | timestamp of the last decision                               | see section 5                                     |

Staff never type Passport IDs, versions or verification codes (D3). If the organizers' copy has a different layout, SH-01's mapping file translates their headers to these names; the rules stay the same.

## 5. Sync design

A sync run is one worker job, `SHEET_SYNC`, that reads the whole Sheet in one API call, decides an outcome for every row, and hands new awards to the existing issuance pipeline. It runs every `SHEET_SYNC_INTERVAL_SECONDS` (default 60) and on demand from a **Sync now** button; the job's `dedupe_key` (`sheet-sync`) guarantees at most one run at a time.

&#91;embedded content: one sync run · Sheet to passport\]

Only PROCESSED rows touch a passport, and they join the same pipeline as admin-panel awards; every other outcome stays in the sync log and, optionally, in the Sheet's status column.

**One run, in order**

1. Read the three tabs with one Sheets API `values.batchGet` (formatted values). If the read fails (network, permission, missing tab), the run is FAILED, nothing changes, and the next interval retries.
2. Hash each row's normalised values; a row whose hash matches its last decision is skipped (fast path for thousands of rows).
3. **Skills Catalog:** create new skills, update name and description of existing ones (affects future versions only, as today).
4. **Students:** create new students, each with a passport and a V1 issuance job (D5); update mutable fields; flag conflicts (section 2).
5. **Verified Skills:** decide each row's outcome (table below). Group this run's new CONFIRMED records by student; per student, one transaction creates a `SHEET` award submission, the awards and one new version (D8) through the existing `create_versions` service. One student's failure never affects another's.
6. If `SHEET_WRITEBACK=true`, write `sync_status`, `sync_message`, `synced_at` for every decided row in one `values.batchUpdate`. A write-back failure is logged; it never undoes processing.
7. Store the run summary (counts per outcome, duration, error).

**Record outcomes (Verified Skills)**

| Outcome                    | When                                                                                           | Passport changes         | Re-checked next sync        |
| -------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------ | --------------------------- |
| `PROCESSED`                | CONFIRMED, valid, new record and new skill for that student                                    | yes: award + new version | no                          |
| `DUPLICATE`                | record already processed, or the student already holds the skill (D4)                          | no                       | no                          |
| `WAITING`                  | status PENDING                                                                                 | no                       | yes                         |
| `IGNORED`                  | status REJECTED, never processed                                                               | no                       | yes (may become CONFIRMED)  |
| `ERROR`                    | validation failed: unknown student or skill, archived skill, bad or future date, missing field | no                       | yes, once the row is edited |
| `CHANGED_AFTER_PROCESSING` | a processed row was edited (D6)                                                                | no                       | flagged for an admin        |
| `REVOKED_IN_SHEET`         | a processed row changed to REJECTED (D7)                                                       | no                       | flagged for an admin        |

Students rows end as `CREATED`, `UPDATED`, `UNCHANGED`, `CONFLICT` or `ERROR`; Skills Catalog rows as `CREATED`, `UPDATED`, `UNCHANGED` or `ERROR`.

**Data model additions (migration `0003`, two new tables, so nineteen in total)**

- `sheet_sync_runs(run_id, trigger [SCHEDULE|MANUAL|UPLOAD], started_at, finished_at, status [RUNNING|DONE|FAILED], counts jsonb, error)`
- `sheet_records(tab, key, row_number, row_hash, outcome, message, award_id NULL, version_id NULL, first_seen_at, decided_at, run_id)` with primary key `(tab, key)`; `key` is the record ID, student ID or skill code.
- `skill_awards.legacy_record_id` renamed to `source_record_id` (still `UNIQUE`); seed records keep their `REC-` IDs, so a Sheet re-import of the seed data comes out as `DUPLICATE`.
- `award_submissions.kind` gains `SHEET`; audit actions `sheet.sync`, `sheet.student.create`, `sheet.award`.

## 6. Milestone M11 tasks

M11 runs after the UI polish and before M10 (hosting). Work in order; one commit per task; tests first for every rule marked as an invariant; record every deviation in `docs/plan/00-overview.md` and add M11 and these task rows there. Priority: SH-01 – SH-09 and SH-12 – SH-13 are **Must**, SH-10 **Should**, SH-11 **Could**.

### SH-01 Sheet source adapter — `backend/app/sheets/source.py` ✅

- A `SheetSource` interface returning the three tabs as lists of header-keyed rows with their row numbers.
- `GoogleSheetSource`: service account from `GOOGLE_SHEETS_CREDENTIALS_FILE` or `GOOGLE_SHEETS_CREDENTIALS_JSON`; one `values.batchGet`; scope read-only unless `SHEET_WRITEBACK=true`. Use `google-auth` plus `httpx` or a small well-known client; justify the choice in Deviations.
- `FileSource`: an `.xlsx` with the three tabs, or a folder of three CSVs; used by tests, by SH-02 and by SH-11.
- Optional `backend/app/data/sheet_mapping.json` mapping the organizers' headers and tab names to section 4's names.
- New env vars in `.env.example`: `GOOGLE_SHEETS_ID`, `GOOGLE_SHEETS_CREDENTIALS_FILE`, `GOOGLE_SHEETS_CREDENTIALS_JSON`, `SHEET_SYNC_INTERVAL_SECONDS=60`, `SHEET_WRITEBACK=false`. Never log credentials.
- **Done when:** unit tests read a fixture `.xlsx` and a CSV folder; with my `.env`, `python -m cli sheets-check` prints the three tab names and row counts from the real Sheet.

### SH-02 Sheet import files and demo rows — `seed/sheets/` ✅

- `python -m cli export-sheets` writes `students.csv`, `skills_catalog.csv`, `verified_skills.csv` from the current seed data in section 4's format, all records CONFIRMED with their `REC-` IDs.
- `seed/sheets/demo-rows.md`: the rows to paste live in the demo: one new student with one CONFIRMED skill, one new CONFIRMED skill for BTU-T-0001, one PENDING, one REJECTED, one with an unknown student ID, one with a future date, one exact repeat of a processed record.
- **Done when:** the three CSVs import into Google Sheets without edits, and a FileSource run on them against the seeded database produces only `UNCHANGED` / `DUPLICATE`.

### SH-03 Data model — migration `0003` (built as `0005`) ✅

- The tables and changes in section 5; downgrade works; `alembic check` clean.
- **Done when:** migration up and down on a copy of the dev database; seed and existing tests still pass.

### SH-04 Sync engine — `backend/app/sheets/sync.py` (invariants: tests first) ✅

- Pure decision logic plus the per-student transactions in section 5; uses the existing services for students, awards and versions; never touches a passport outside its own transaction.
- **Done when** tests cover every outcome in section 5 and these invariants: a repeated sync adds nothing; PENDING and REJECTED never create awards; an unknown student or skill changes nothing; one student's error doesn't block another's record; two new CONFIRMED records for one student give one version; a processed row edited later is flagged, not applied; Passport ID, first-issued date and earlier skills are unchanged after an update.

### SH-05 Scheduled job and API ✅

- Worker job type `SHEET_SYNC`, enqueued every `SHEET_SYNC_INTERVAL_SECONDS` with `dedupe_key='sheet-sync'`; disabled when `GOOGLE_SHEETS_ID` is empty.
- `POST /api/admin/sheet-sync` (Admin and Super admin): enqueue now, return the run ID; `GET /api/admin/sheet-sync/runs` and `GET /api/admin/sheet-sync/records?outcome=&tab=&q=` (paged).
- **Done when:** a manual sync and a scheduled sync both run; a second request while one runs returns the running run's ID; a student gets 403.

### SH-06 Write-back ✅

- With `SHEET_WRITEBACK=true`, after each run write `sync_status`, `sync_message`, `synced_at` for every row decided in that run, in one `values.batchUpdate`; create the three header cells if missing; never touch other columns.
- **Done when:** after a live sync the Verified Skills tab shows the outcome next to each row; turning write-back off leaves the Sheet untouched.

### SH-07 Admin "Google Sheets" page and dashboard card — `/admin/sheets`

- Last run (time, status, counts), next scheduled run, a **Sync now** button, and a records table filtered by outcome (errors and flags first) with the message, row number and links to the student and version.
- Dashboard: a "Google Sheets" card with last successful sync time and the number of errors and flags; it turns red if the last run failed.
- Built with the existing design tokens; works at 390 px.
- **Done when:** after the demo rows from SH-02, the page shows each outcome correctly and the links work.

### SH-08 Initial passport at student creation (D5) ✅

- Creating a student, through the admin form or the Sheet, creates the passport and enqueues V1, even with zero skills. Frozen fields are set at V1.
- The PDF template handles zero skills: empty grid boxes and a "No verified skills yet" line in the detail table.
- Existing seeded students without a version get their V1 on the next `issue-pending`. Update the A1 wording and record the reversal in Deviations.
- **Done when:** registering a student yields an ANCHORED V1 that verifies VALID; a zero-skill PDF looks right.

### SH-09 Verify wording: record versus file (G8)

- Verify by code shows "Official record found", the version, latest or outdated, issuer verified, and a clear line: "This confirms the record. To check a file, upload the PDF." It must not look like a file check.
- Verify by file keeps the authentic, outdated and not-valid results, labelled as file checks.
- **Done when:** screenshots of both paths at 1440 and 390 px; the A-tests for verify still pass.

### SH-10 Student notification email (Should)

- When a version reaches ANCHORED, email the student: "Your AI Skills Passport was updated to version N", with the new skills and a link to `/me`. Use the existing mailer (Resend in demo, Mailpit in dev). No email for V1 of seeded students.
- **Done when:** a Sheet-driven award produces exactly one email in Mailpit.

### SH-11 Excel import (Could)

- On `/admin/sheets`, upload an `.xlsx` with the same three tabs; it runs the same engine through `FileSource`, recorded as a run with trigger `UPLOAD`.
- **Done when:** uploading the SH-02 data as `.xlsx` gives only `UNCHANGED` / `DUPLICATE`.

### SH-12 Deliverable documents — `docs/deliverables/`

- `architecture-brief.md` (1–2 pages): data sources (Sheet and admin panel), processing, PDF generation, versions, blockchain anchoring and issuer check.
- `scaling-vision.md`: how 5,000+ passports a year work, with numbers from measurements (render time per PDF, worker count, batch size, transactions per batch, one Sheets read per interval, database indexes, chain cost options).
- `sheets-demo-script.md`: the live Sheets demo step by step, using SH-02's rows.
- **Done when:** each file is written in plain language and every number in it comes from a measurement or a setting.

### SH-13 Acceptance tests for the MVP table

- One automated test per MVP scenario (section 7) against a FileSource, plus a live smoke test against the real Sheet that runs only when `GOOGLE_SHEETS_ID` is set.
- **Done when:** `make test` covers every scenario, and the live smoke test passes on my machine.

## 7. Demo scenarios and deliverables

After M11 every scenario in the spec's MVP table can be shown live; the Sheet drives the first seven.

| MVP scenario                        | Expected result (spec)                                      | How we show it                                                                         | Built by          |
| ----------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------- | ----------------- |
| Adding a new student                | One passport with a permanent ID                            | Paste a new student row in the Sheet, Sync now; the student appears with a Passport ID | SH-04, SH-08      |
| Initial passport generation         | Multi-page PDF in BTU's design                              | That student's V1 reaches ANCHORED; open the PDF                                       | SH-08             |
| New verified skill in Google Sheets | Detected and processed automatically                        | Paste a CONFIRMED row for BTU-T-0001; wait for the scheduled sync or press Sync now    | SH-04, SH-05      |
| Reflecting a new skill              | The existing passport is updated                            | New version with the skill; Passport ID unchanged                                      | existing pipeline |
| Repeated data synchronization       | Not added a second time                                     | Sync again; the row shows `DUPLICATE`, no new version                                  | SH-04             |
| Invalid student identifier          | Processing of that entry halts                              | Row with `BTU-T-9999` shows `ERROR: Unknown student`; nothing else changes             | SH-04, SH-06      |
| Passport update                     | Passport ID, first-issued date and earlier skills preserved | Compare V1 and V2 PDFs side by side                                                    | existing          |
| Issuing a new version               | New PDF and verification record                             | Issuance page; Sepolia transaction link                                                | existing          |
| Verifying an unaltered PDF          | Passes                                                      | Upload the PDF on `/verify`                                                            | existing          |
| Verifying a modified PDF            | Discrepancy detected                                        | Upload the one-byte-changed copy                                                       | existing          |
| Verifying the issuer's identity     | BTU's test identity confirmed                               | The issuer check on the result, plus the issuer file on the domain                     | existing          |
| Verifying an older version          | Authentic but not latest                                    | Upload V1 after V2 exists                                                              | existing          |
| Student access                      | View and download own passport                              | Sign in as the student (BTU Google account or email code)                              | existing          |
| Public verification                 | No authorization needed                                     | A private browser window                                                               | existing          |

Also worth showing: PENDING and REJECTED rows staying out of the passport, and the write-back column filling in next to each row.

**Deliverables**

| #   | Deliverable                                | Where                                                                                |
| --- | ------------------------------------------ | ------------------------------------------------------------------------------------ |
| 1   | Working prototype                          | The app, on the demo host (M10) or locally on Sepolia                                |
| 2   | System architecture (brief)                | `docs/deliverables/architecture-brief.md` (SH-12) and the deck's architecture slides |
| 3   | Google Sheets integration demo             | `docs/deliverables/sheets-demo-script.md`, live in the demo                          |
| 4   | Blockchain verification demo               | Existing verify flows: valid, tampered, issuer, older version                        |
| 5   | Scaling vision for 5,000+ passports a year | `docs/deliverables/scaling-vision.md` (SH-12) and one slide                          |
