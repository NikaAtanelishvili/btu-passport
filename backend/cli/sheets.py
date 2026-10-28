"""`python -m cli sheets-check` (SH-01): read the Sheet once and print what was found.
`python -m cli sheets-reset` (make demo-reset): the Sheet back to the seed data."""

import sys
from typing import Any

from app.sheets import source, writeback
from app.sheets.sync import KEY_COLUMNS
from cli import export_sheets


def check() -> None:
    try:
        tabs = source.GoogleSheetSource().read()
    except source.SourceError as exc:
        print(f"sheets-check: FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    for tab in tabs.values():
        missing = tab.missing()
        note = f", missing columns: {', '.join(missing)}" if missing else ""
        print(f"{tab.title}: {len(tab.rows)} rows{note}")


def reset(sheet: Any = None) -> None:
    """`python -m cli sheets-reset` (make demo-reset): put the Sheet back to the seed data.
    Students and Verified Skills rows below the seed rows are deleted, and the write-back
    columns of the seed rows in Verified Skills are emptied. No other cell changes. Refuses,
    changing nothing, unless the tabs start with exactly the seed rows in the seed order."""
    seed = source.FileSource(export_sheets.OUT_DIR).read()
    try:
        sheet = sheet or source.GoogleSheetSource(writeback=True)
        tabs = sheet.read()
        plans = []
        for name in (source.STUDENTS, source.VERIFIED):
            tab, key = tabs[name], KEY_COLUMNS[name]
            last = tab.header_row + len(seed[name].rows)
            found = [str(r.values.get(key, "")) for r in tab.rows if r.number <= last]
            if found != [str(r.values[key]) for r in seed[name].rows]:
                print(f"sheets-reset: REFUSED: {tab.title} rows {tab.header_row + 1}-{last} "
                      "are not the seed data in the seed order; nothing changed",
                      file=sys.stderr)  # fmt: skip
                raise SystemExit(1)
            extra = [r.number for r in tab.rows if r.number > last]
            plans.append((tab, last, max(extra, default=0)))
        for tab, last, end in plans:
            if tab.name == source.VERIFIED:
                letters = [writeback.column_letter(tab.columns[c])
                           for c in source.SYSTEM_COLUMNS if c in tab.columns]  # fmt: skip
                a1 = source.a1_tab(tab.title)
                sheet.clear([f"{a1}!{x}{tab.header_row + 1}:{x}{last}" for x in letters])
                print(f"{tab.title}: cleared {', '.join(letters) or 'no'} columns "
                      f"in rows {tab.header_row + 1}-{last}")  # fmt: skip
            if end:
                sheet.delete_rows(tab.title, last + 1, end)
            print(f"{tab.title}: deleted rows {last + 1}-{end}" if end
                  else f"{tab.title}: nothing below row {last}")  # fmt: skip
    except source.SourceError as exc:
        print(f"sheets-reset: FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
