# Demo rows, second set (live demo after rehearsals)

The same eight scenarios as [`demo-rows.md`](demo-rows.md) with fresh IDs. Once the first set
has been pasted and synced (a rehearsal), its rows only show `DUPLICATE`; this set still shows
real `PROCESSED` results on a Sheet that holds the first set, or one that doesn't. To start
over with the first set instead, run `make demo-reset` (README).

Paste the same way: click the first empty cell in column A below the last row of the tab and
paste; Google Sheets puts each value in its own column. Leave `sync_status`, `sync_message`
and `synced_at` empty.

## Students tab: one new student

```tsv
BTU-T-0031	Tamar	Lomtadze	btu-t-0031@example.org	Computer Science and Artificial Intelligence	BACHELOR	ACTIVE
```

## Verified Skills tab: seven records

```tsv
REC-0201	BTU-T-0031	SKL-001	2026-10-27	CONFIRMED	AI Literacy Workshop
REC-0202	BTU-T-0001	SKL-002	2026-10-27	CONFIRMED	Prompt Engineering Lab
REC-0203	BTU-T-0002	SKL-006	2026-10-27	PENDING	AI Data Analysis Bootcamp
REC-0204	BTU-T-0003	SKL-014	2026-10-27	REJECTED	AI Systems Hackathon
REC-0205	BTU-T-9999	SKL-001	2026-10-27	CONFIRMED	AI Literacy Workshop
REC-0206	BTU-T-0005	SKL-004	2030-01-15	CONFIRMED	AI Productivity Clinic
REC-0202	BTU-T-0001	SKL-002	2026-10-27	CONFIRMED	Prompt Engineering Lab
```

## What each row shows

| Row | Record | Expected outcome after "Sync now" | Spec scenario |
| --- | --- | --- | --- |
| Students | BTU-T-0031 Tamar Lomtadze | `CREATED`: a new student with the next Passport ID; their V1 is issued in the same sync | Adding a new student · Initial passport generation |
| 1 | REC-0201, BTU-T-0031, SKL-001 AI Literacy | `PROCESSED`: AI Literacy is in the new student's V1 | New verified skill · Initial passport generation |
| 2 | REC-0202, BTU-T-0001, SKL-002 Prompt Engineering Fundamentals | `PROCESSED`: Giorgi Kapanadze's passport BTU-AI-000125 gets a new version with one more skill (Giorgi holds neither SKL-002 in the seed nor from the first set); Passport ID and first-issued date unchanged | New verified skill · Passport update |
| 3 | REC-0203, PENDING | `WAITING`: nothing changes; the row links to Mariam Beridze (BTU-T-0002); change the status to CONFIRMED and sync again to see it processed | Unverified records stay out |
| 4 | REC-0204, REJECTED | `IGNORED`: nothing changes | Unverified records stay out |
| 5 | REC-0205, BTU-T-9999 | `ERROR`: "Unknown student BTU-T-9999"; no passport changes | Invalid student identifier |
| 6 | REC-0206, date 2030-01-15 | `ERROR`: "Date earned is in the future"; no passport changes | Incomplete or flawed record |
| 7 | REC-0202 again (an exact repeat of row 2) | `DUPLICATE`: counted once; no second award, no extra version | Repeated data synchronization |

Press **Sync now** a second time without changing anything: no new versions, every outcome
stays the same.
