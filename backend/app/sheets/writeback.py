"""Write-back (SH-06): each Verified Skills row's decision into the tab's three system columns
`sync_status`, `sync_message`, `synced_at`, with one values.batchUpdate after a run.

Only cells whose current text differs are written, so an unchanged run writes nothing; the
header cells are added after the last used column when missing. No other cell is touched (D1).
"""

import logging
from dataclasses import dataclass
from datetime import UTC
from typing import Protocol, runtime_checkable

from sqlalchemy import select

from app.db import SessionLocal
from app.models import SheetRecord, SheetSyncRun
from app.sheets.source import SYSTEM_COLUMNS, VERIFIED, SourceError, Tab, a1_tab
from app.sheets.sync import SyncResult, text_of

log = logging.getLogger("sheets")


@runtime_checkable
class WritableSource(Protocol):
    writeback: bool

    def write(self, data: list[tuple[str, list[list[str]]]]) -> int: ...


@dataclass(frozen=True)
class CellWrite:
    row: int  # 1-based
    column: int  # 0-based
    value: str


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def plan(tab: Tab, decided: dict[int, tuple[str, str, str]]) -> list[CellWrite]:
    """Cells to write: missing headers, then each decided row's system cells that differ.
    `decided` maps a row number to (sync_status, sync_message, synced_at)."""
    columns = dict(tab.columns)
    cells = []
    next_free = max(columns.values(), default=-1) + 1
    for name in SYSTEM_COLUMNS:
        if name not in columns:
            columns[name] = next_free
            cells.append(CellWrite(tab.header_row, next_free, name))
            next_free += 1
    rows = {r.number: r for r in tab.rows}
    for number, values in sorted(decided.items()):
        row = rows.get(number)
        for name, value in zip(SYSTEM_COLUMNS, values, strict=True):
            current = text_of(row.values.get(name, "")) if row else ""
            if current != value:
                cells.append(CellWrite(number, columns[name], value))
    return cells


def _decided(result: SyncResult) -> dict[int, tuple[str, str, str]]:
    """Each Verified Skills row decided in this run, with its stored decision time."""
    keys = [d.key for d in result.decisions if d.tab == VERIFIED]
    with SessionLocal() as db:
        stored = {
            r.key: r
            for r in db.scalars(
                select(SheetRecord).where(SheetRecord.tab == VERIFIED, SheetRecord.key.in_(keys))
            )
        }
    out = {}
    for d in result.decisions:
        if d.tab != VERIFIED or (r := stored.get(d.key)) is None:
            continue
        synced_at = r.decided_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
        out[d.row] = (r.outcome, r.message or "", synced_at)
    return out


def write_back(result: SyncResult, source: WritableSource) -> int | None:
    """Write this run's decisions to the Sheet; returns cells written, None when off. A failure
    is logged and noted on the run; processing is never undone."""
    if not source.writeback or result.verified is None or not result.decisions:
        return None
    tab = result.verified
    cells = plan(tab, _decided(result))
    data = [(f"{a1_tab(tab.title)}!{column_letter(c.column)}{c.row}", [[c.value]]) for c in cells]
    note: dict[str, object]
    try:
        written = source.write(data) if data else 0
        note = {"cells": written}
    except SourceError as exc:
        log.warning("sheet sync run %s: write-back failed: %s", result.run_id, exc)
        written, note = 0, {"error": str(exc)}
    with SessionLocal() as db, db.begin():
        run = db.get_one(SheetSyncRun, result.run_id, with_for_update=True)
        run.counts = {**run.counts, "writeback": note}
    return written
