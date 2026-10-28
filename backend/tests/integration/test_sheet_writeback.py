"""SH-06: write-back of sync_status, sync_message, synced_at to the Verified Skills tab."""

import copy
import re
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SheetSyncRun
from app.sheets import service, source
from app.sheets.source import TABS, VERIFIED, FileSource, Tab
from app.sheets.writeback import column_letter
from cli import export_sheets
from tests.integration.test_sheet_sync import header, record

pytestmark = pytest.mark.usefixtures("s3_bucket", "fake_signer")
A1 = re.compile(r"^'(.+)'!([A-Z]+)(\d+)$")


def column_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - ord("A") + 1
    return n - 1


class GridSource:
    """The tabs as cell grids that write() changes, like the real Sheet."""

    label = "Google Sheet"

    def __init__(self, writeback: bool = True) -> None:
        tabs = FileSource(export_sheets.OUT_DIR).read()
        self.grids: dict[str, list[list[Any]]] = {}
        for name, tab in tabs.items():
            head = header(name)
            self.grids[name] = [head] + [[r.values[h] for h in head] for r in tab.rows]
        self.writeback = writeback
        self.writes: list[list[tuple[str, list[list[str]]]]] = []
        self.fail: str | None = None

    def read(self) -> dict[str, Tab]:
        return {n: source.build_tab(n, n, copy.deepcopy(self.grids[n])) for n in TABS}

    def write(self, data: list[tuple[str, list[list[str]]]]) -> int:
        if self.fail:
            raise source.SourceError(self.fail)
        self.writes.append(data)
        for a1, [[value]] in data:
            match = A1.match(a1)
            assert match, a1
            title, letters, number = match.groups()
            grid, row, col = self.grids[title], int(number) - 1, column_index(letters)
            while len(grid) <= row:
                grid.append([])
            grid[row].extend([""] * (col + 1 - len(grid[row])))
            grid[row][col] = value
        return len(data)

    def cells(self, row: int) -> list[Any]:
        return self.grids[VERIFIED][row - 1]


@pytest.fixture
def sheet(seeded: Session, monkeypatch: pytest.MonkeyPatch) -> GridSource:
    monkeypatch.setattr(get_settings(), "google_sheets_id", "test-sheet")
    grid = GridSource()
    monkeypatch.setattr(service, "source_for_run", lambda: grid)
    return grid


def sync_once(db: Session, run_jobs: Callable[[], int]) -> SheetSyncRun:
    run_id = service.enqueue(db, "MANUAL").run_id
    db.commit()
    run_jobs()
    db.expire_all()
    return db.get_one(SheetSyncRun, run_id)


def test_column_letters() -> None:
    assert [column_letter(i) for i in (0, 5, 25, 26, 27, 701, 702)] == [
        "A", "F", "Z", "AA", "AB", "ZZ", "AAA",
    ]  # fmt: skip


def test_outcomes_written_next_to_each_row(
    seeded: Session, sheet: GridSource, run_jobs: Callable[[], int]
) -> None:
    sheet.grids[VERIFIED].append(record("REC-0105", "BTU-T-9999", "SKL-001"))
    staff = [row[:6] for row in sheet.grids[VERIFIED]]
    run = sync_once(seeded, run_jobs)
    assert run.status == "DONE"
    head = sheet.cells(1)
    assert head[6:] == ["sync_status", "sync_message", "synced_at"]  # added after column F
    assert sheet.cells(2)[6:8] == ["DUPLICATE", "Already on the passport (seed import)"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d UTC", sheet.cells(2)[8])
    assert sheet.cells(62)[6:8] == ["ERROR", "Unknown student BTU-T-9999"]
    assert [row[:6] for row in sheet.grids[VERIFIED]] == staff  # nothing else touched
    assert len(sheet.writes) == 1  # one batchUpdate
    assert run.counts["writeback"] == {"cells": 3 + 61 * 3}

    # An unchanged run writes nothing.
    again = sync_once(seeded, run_jobs)
    assert again.counts["writeback"] == {"cells": 0}
    assert len(sheet.writes) == 1

    # Fixing the row changes only that row's cells.
    sheet.grids[VERIFIED][61][1] = "BTU-T-0001"
    sheet.grids[VERIFIED][61][2] = "SKL-003"
    sync_once(seeded, run_jobs)
    [last] = sheet.writes[1:]
    # synced_at has minute precision: it changes only when the minute does.
    assert {"G62", "H62"} <= {a1.split("!")[1] for a1, _ in last} <= {"G62", "H62", "I62"}
    assert sheet.cells(62)[6] == "PROCESSED"


def test_existing_system_columns_are_reused(
    seeded: Session, sheet: GridSource, run_jobs: Callable[[], int]
) -> None:
    grid = sheet.grids[VERIFIED]
    grid[0] += ["notes", "Sync_Status ", "sync_message", "synced_at"]
    for row in grid[1:]:
        row += ["keep me", "", "", ""]
    sync_once(seeded, run_jobs)
    assert sheet.cells(1)[6:] == ["notes", "Sync_Status ", "sync_message", "synced_at"]
    assert sheet.cells(5)[6:9] == ["keep me", "DUPLICATE", "Already on the passport (seed import)"]


def test_writeback_off_leaves_the_sheet_untouched(
    seeded: Session, sheet: GridSource, run_jobs: Callable[[], int]
) -> None:
    sheet.writeback = False
    before = copy.deepcopy(sheet.grids)
    run = sync_once(seeded, run_jobs)
    assert run.status == "DONE" and "writeback" not in run.counts
    assert sheet.writes == [] and sheet.grids == before


def test_write_failure_keeps_processing(
    seeded: Session, sheet: GridSource, run_jobs: Callable[[], int]
) -> None:
    sheet.grids[VERIFIED].append(record("REC-0102", "BTU-T-0001", "SKL-003"))
    sheet.fail = "The service account has no access to the Sheet"
    run = sync_once(seeded, run_jobs)
    assert run.status == "DONE"
    assert run.counts["writeback"] == {"error": "The service account has no access to the Sheet"}
    assert run.counts["Verified Skills"]["PROCESSED"] == 1
