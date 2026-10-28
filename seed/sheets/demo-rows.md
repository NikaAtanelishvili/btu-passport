# Demo rows for the live Google Sheets demo (SH-02)

Paste these into the Sheet during the demo (`docs/deliverables/sheets-demo-script.md` has the
full script). The blocks are tab-separated: click the first empty cell in column A of the tab
and paste, and Google Sheets puts each value in its own column. Dates may turn into date cells;
the sync reads them either way.

## Students tab: one new student

Paste below the last student (row 20 after the import).

```tsv
BTU-T-0030	Mariam	Tsiklauri	btu-t-0030@example.org	Computer Science and Artificial Intelligence	BACHELOR	ACTIVE
```

## Verified Skills tab: seven records

Paste below the last record (row 62 after the import). Leave the `sync_status`,
`sync_message` and `synced_at` columns empty; the system fills them when write-back is on.

```tsv
REC-0101	BTU-T-0030	SKL-001	2026-10-27	CONFIRMED	AI Literacy Workshop
REC-0102	BTU-T-0001	SKL-003	2026-10-27	CONFIRMED	AI Ethics Masterclass
REC-0103	BTU-T-0002	SKL-005	2026-10-27	PENDING	AI Research Bootcamp
REC-0104	BTU-T-0003	SKL-013	2026-10-27	REJECTED	NLP Hackathon
REC-0105	BTU-T-9999	SKL-001	2026-10-27	CONFIRMED	AI Literacy Workshop
REC-0106	BTU-T-0004	SKL-005	2030-01-15	CONFIRMED	AI Research Bootcamp
REC-0102	BTU-T-0001	SKL-003	2026-10-27	CONFIRMED	AI Ethics Masterclass
```

## What each row shows

| Row | Record | Expected outcome after "Sync now" | Spec scenario |
| --- | --- | --- | --- |
| Students | BTU-T-0030 Mariam Tsiklauri | `CREATED`: a new student with the next Passport ID; their first version V1 is issued in the same sync (without row 1 it would hold no skills) | Adding a new student · Initial passport generation |
| 1 | REC-0101, BTU-T-0030, SKL-001 AI Literacy | `PROCESSED`: AI Literacy is in the new student's V1 (one version per student per sync) | New verified skill · Initial passport generation |
| 2 | REC-0102, BTU-T-0001, SKL-003 AI Ethics & Responsible Use | `PROCESSED`: Giorgi Kapanadze's passport BTU-AI-000125 gets a new version with five skills; Passport ID and first-issued date unchanged | New verified skill · Passport update |
| 3 | REC-0103, PENDING | `WAITING`: nothing changes; change the status to CONFIRMED and sync again to see it processed | Unverified records stay out |
| 4 | REC-0104, REJECTED | `IGNORED`: nothing changes | Unverified records stay out |
| 5 | REC-0105, BTU-T-9999 | `ERROR`: "Unknown student BTU-T-9999"; no passport changes | Invalid student identifier |
| 6 | REC-0106, date 2030-01-15 | `ERROR`: "Date earned is in the future"; no passport changes | Incomplete or flawed record |
| 7 | REC-0102 again (an exact repeat of row 2) | `DUPLICATE`: counted once; no second award, no extra version | Repeated data synchronization |

Press **Sync now** a second time without changing anything: no new versions, every outcome
stays the same.
