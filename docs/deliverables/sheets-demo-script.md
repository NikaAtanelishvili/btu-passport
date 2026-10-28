# Google Sheets demo script

How adding a verified skill in Google Sheets updates a student's passport automatically, and
how wrong or unverified records are stopped. About 6 minutes. The rows to paste are in
[`seed/sheets/demo-rows.md`](../../seed/sheets/demo-rows.md). If that set was already pasted
and synced in a rehearsal, use the second set in
[`seed/sheets/demo-rows-live.md`](../../seed/sheets/demo-rows-live.md) (same steps, fresh IDs:
BTU-T-0031 and REC-0201 onward), or start over with `make demo-reset`.

## Before the demo

- The Sheet **BTU Passport — Test Data** has the hackathon data imported (tabs *Students*,
  *Skills Catalog*, *Verified Skills*), is shared with the service account as Editor, and
  `GOOGLE_SHEETS_ID` and `SHEET_WRITEBACK=true` are set.
- The app runs (`make dev`) and every seed passport is anchored (`make issue-pending`).
- Open three tabs: the Sheet, **/admin/sheets** signed in as an admin, and **/verify** in a
  private window.
- Run *Sync now* once: every seed record shows `DUPLICATE` ("Already on the passport") in the
  Sheet's `sync_status` column, students and skills `UNCHANGED`. Nothing in the system changes.

## 1. The university adds a new student (≈ 1 min)

1. In the Sheet's *Students* tab, paste the **Students** row (BTU-T-0030, Mariam Tsiklauri).
2. In *Verified Skills*, paste the seven **Verified Skills** rows below the last record.
3. Say: "BTU staff only type rows. They never open a passport or make a PDF."

## 2. The system picks the rows up (≈ 1 min)

1. On /admin/sheets press **Sync now** (or wait for the scheduled sync, every 60 seconds; the
   page shows the next one).
2. The run's summary appears: 2 processed, 1 waiting, 1 ignored, 2 errors, 1 duplicate.
3. Switch to the Sheet: the `sync_status` column now says next to each row:

| Row | sync_status | sync_message |
| --- | --- | --- |
| REC-0101 (new student, AI Literacy) | PROCESSED | Added to BTU-AI-000143 v1 (the new Passport ID) |
| REC-0102 (BTU-T-0001, AI Ethics) | PROCESSED | Added to BTU-AI-000125 v… |
| REC-0103 (PENDING) | WAITING | Waiting for confirmation |
| REC-0104 (REJECTED) | IGNORED | Rejected; not added |
| REC-0105 (BTU-T-9999) | ERROR | Unknown student BTU-T-9999 |
| REC-0106 (2030-01-15) | ERROR | Date earned is in the future |
| REC-0102 again | DUPLICATE | Same Record ID as row …; counted once |

Say: "Only CONFIRMED records reach a passport. A wrong Student ID changes nothing and is
logged. The same record twice is counted once."

## 3. The new student's passport (≈ 1 min) — *Adding a new student, Initial passport generation*

1. On /admin/sheets click **BTU-T-0030**: the next Passport ID (**BTU-AI-000143** on a freshly seeded database), version v1 with AI
   Literacy, status Anchored within a few seconds.
2. Download the PDF: cover, about page, the skill grid with the AI Literacy stamp, the detail
   table ("Earned through: AI Literacy Workshop"), the verification code and QR on every page.

## 4. The existing passport is updated (≈ 1 min) — *New verified skill, Reflecting a new skill, Passport update*

1. Open **BTU-T-0001** (Giorgi Kapanadze): a new version with five skills.
2. Put the previous and the new PDF side by side: same Passport ID BTU-AI-000125, same first
   issue date, the four earlier skills unchanged, AI Ethics & Responsible Use added.
3. Mailpit (dev) or the student's inbox: "Your AI Skills Passport was updated to version …".

## 5. Repeat and fix (≈ 1 min) — *Repeated data synchronization*

1. Press **Sync now** again without changing anything: no new versions; every outcome stays.
2. In the Sheet change REC-0103's status from PENDING to **CONFIRMED**, sync: it becomes
   PROCESSED and BTU-T-0002 gets a new version.
3. Optional: edit the date of the processed REC-0102 row and sync: **CHANGED_AFTER_PROCESSING**,
   "Edited after processing …; not applied". Processed skills are never changed by the Sheet.
   Set it back afterwards.

## 6. Verify (≈ 1 min) — *hand over to the blockchain demo*

1. In the private window, upload BTU-T-0001's new PDF on /verify: **Authentic**, latest
   version, issued by BTU; upload the previous version: **Outdated**.
2. Enter the verification code instead: **Record found**, with the note that a code confirms
   the record and the file check needs the PDF.

## If something goes wrong

- The page says *The last sync failed* with Google's reason (for example the Sheet isn't
  shared with the service account). Fix it and press Sync now; nothing was changed.
- A version stays *Pending* or *Anchoring*: the worker or the signer isn't running
  (`make dev` runs all of them).
