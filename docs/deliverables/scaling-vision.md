# Scaling to 5,000+ passports a year

The prototype already works the way a production system would: Google Sheets is read in one
call per interval, records are decided in memory and written in one transaction per student,
PDFs are rendered by background workers, and many versions share one blockchain transaction.
Every number below is either **measured** on the development machine (a laptop, PostgreSQL 16
in Docker, `python -m cli bench`, 2026-10-28) or a **setting** of the system.

## Measurements

| What | Result | Source |
| --- | --- | --- |
| One Sheet sync of **5,000 new students with 15,000 CONFIRMED records** (plus the 18 seed students and 60 seed records) | **61 s**: 5,000 students and passports created, 15,000 awards, **5,000 new versions** (one per student, not one per record) | measured (`cli bench`) |
| The same Sheet synced again, unchanged | **2.0 s**, no new award or version | measured |
| One Sheet sync of the hackathon data (18 students, 16 skills, 60 records), read from Google Sheets | 1.6 s including the Google API call | measured live |
| Render one passport PDF, 6 skills / 25 skills | **0.71 s** / **1.04 s** (median of 10) | measured |
| PDF size, 6 / 25 skills | 286 KB / 308 KB | measured |
| Merkle tree for a full batch of 1,024 versions | 0.022 s | measured |
| Blockchain transaction per batch | **48,194 gas**, the same for a batch of 1 and of 18 versions | measured on Anvil |
| Versions per blockchain transaction | up to 1,024 | setting `BATCH_MAX_LEAVES` |
| Anchoring interval | 10 s in development; 600 s planned for production | setting `ANCHOR_INTERVAL_SECONDS` |
| Google Sheets reads | one `values.batchGet` per 60 s, i.e. 1,440 a day, whatever the number of rows | setting `SHEET_SYNC_INTERVAL_SECONDS` |

## What 5,000 passports a year means for each part

**Sheet intake.** 5,000 students and 15,000 records were decided and stored in about a
minute, and an unchanged Sheet of that size is checked in 2 seconds. A sync reads the whole
Sheet at once, so the cost per interval does not grow with the number of changes. Rows that
have not changed since their last decision are skipped, and only changed status cells are
written back. At most one sync runs at a time (a database rule plus the job's dedupe key).

**PDF generation** is the slowest step, so it runs in the background and in parallel. From
the measured 0.71–1.04 s per PDF, 5,000 new versions take about 60–87 minutes on one worker
process, or about 15–22 minutes on four. Workers take jobs with `FOR UPDATE SKIP LOCKED`, so
more worker processes (or machines) simply share the queue; nothing else changes. A version
becomes the latest only after it is rendered and anchored, so a backlog never shows a
student a half-finished passport.

**Blockchain.** Versions are anchored in batches: one Merkle root per batch of up to 1,024
PDFs, at 48,194 gas whatever the batch size. 5,000 versions fit in 5 transactions
(5 × 48,194 = 240,970 gas) instead of 5,000 (241 million gas). With the planned 600-second
interval there are at most 144 anchoring transactions a day, however many passports change.
Cost options, cheapest first in practice:

- keep the public testnet for pilots (free test currency);
- an Ethereum layer-2 network for production: the same contract and code, lower fees per
  transaction;
- a longer interval (for example one root a day: 365 transactions a year) if minutes of
  delay before a new version verifies are acceptable.

The verification side does not touch the blockchain write path at all: it reads the stored
proof and asks any node whether the root exists, so 5,000 or 50,000 verifications cost BTU
nothing on-chain.

**Storage.** At about 300 KB per PDF, 5,000 versions are about 1.5 GB. Each PDF is stored
once under its own fingerprint and never rewritten.

**Database.** The lookups on every sync and verification are indexed: `sheet_records`
primary key `(tab, key)` and an index on `outcome`; unique `skill_awards.source_record_id`
(one award per Record ID) and `(student_id, skill_id)` (one award per skill); unique
`passport_versions (passport_id, version_no)`, `verification_code` and `pdf_sha256`; the job
queue's `(status, run_after)` index and its unique dedupe key for running jobs. Saving a
sync's decisions reads the stored rows per tab in chunks of 1,000 keys (the benchmark found
that one query for 15,000 keys was too large).

## Less work for staff

- Staff only type rows in the Sheet. They never open a passport, fill a template or make a PDF.
- Each record's result appears next to it in the Sheet (`sync_status`, `sync_message`,
  `synced_at`), so staff see at a glance what to fix: "Unknown student BTU-T-9999".
- The admin page puts errors and flags first; everything else needs no attention.
- Students are emailed when their passport changes.

## Growing further

- More workers for rendering (the only step that grows linearly with volume).
- Several Sheets (for example one per faculty): each becomes another source of the same
  engine; the Record ID rule keeps them from awarding the same record twice.
- An Excel file with the same three tabs can already be imported through the same checks.
