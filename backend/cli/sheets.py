"""`python -m cli sheets-check` (SH-01): read the Sheet once and print what was found."""

import sys

from app.sheets import source


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
