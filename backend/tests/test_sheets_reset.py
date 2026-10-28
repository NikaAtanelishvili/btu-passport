"""make demo-reset's Sheet step (cli sheets-reset): rows below the seed are deleted, the
write-back columns of the seed rows emptied, nothing else touched; refuses on a reordered tab."""

from typing import Any

import pytest

from app.sheets import source as src
from app.sheets.source import COLUMNS, STUDENTS, SYSTEM_COLUMNS, VERIFIED, FileSource, Tab
from cli import export_sheets, sheets


class FakeSheet:
    """The three tabs as grids; clear and delete_rows act on them like the Sheets API."""

    def __init__(self) -> None:
        self.grids: dict[str, list[list[Any]]] = {}
        for name, tab in FileSource(export_sheets.OUT_DIR).read().items():
            head = [*COLUMNS[name][0], *COLUMNS[name][1]]
            head += list(SYSTEM_COLUMNS) if name == VERIFIED else []
            self.grids[name] = [head, *[[r.values.get(h, "") for h in head] for r in tab.rows]]
        self.calls: list[tuple[str, Any]] = []

    def read(self) -> dict[str, Tab]:
        return {n: src.build_tab(n, n, [list(r) for r in g]) for n, g in self.grids.items()}

    def clear(self, ranges: list[str]) -> None:
        self.calls.append(("clear", ranges))
        for a1 in ranges:
            title, cells = a1.rsplit("!", 1)
            start, end = cells.split(":")
            col = ord(start[0]) - ord("A")
            grid = self.grids[title.strip("'")]
            for row in range(int(start[1:]), int(end[1:]) + 1):
                grid[row - 1][col] = ""

    def delete_rows(self, title: str, first: int, last: int) -> None:
        self.calls.append(("delete", (title, first, last)))
        del self.grids[title][first - 1 : last]


def test_back_to_the_seed_rows() -> None:
    sheet = FakeSheet()
    seed = {n: [list(r) for r in g] for n, g in sheet.grids.items()}
    verified = sheet.grids[VERIFIED]
    for row in verified[1:]:
        row[-3:] = ["DUPLICATE", "Already on the passport", "2026-10-28 12:50 UTC"]
    verified.append(["REC-0101", "BTU-T-0030", "SKL-001", "2026-10-27", "CONFIRMED", "", *"XYZ"])
    verified.append(["", "", "", "", "", "", "ERROR", "orphaned write-back", ""])
    sheet.grids[STUDENTS].append(["BTU-T-0030", "M", "T", "m@x.org", "CS", "BACHELOR", "ACTIVE"])

    sheets.reset(sheet)

    assert sheet.grids == seed  # system columns empty again, every other cell as it was
    assert ("delete", (STUDENTS, 20, 20)) in sheet.calls
    assert ("delete", (VERIFIED, 62, 63)) in sheet.calls
    [(_, ranges)] = [c for c in sheet.calls if c[0] == "clear"]
    assert ranges == [f"'{VERIFIED}'!{x}2:{x}61" for x in "GHI"]
    assert len(SYSTEM_COLUMNS) == 3


def test_nothing_below_the_seed_deletes_nothing() -> None:
    sheet = FakeSheet()
    sheets.reset(sheet)
    assert [c for c in sheet.calls if c[0] == "delete"] == []


def test_refuses_when_the_seed_rows_moved(capsys: pytest.CaptureFixture[str]) -> None:
    sheet = FakeSheet()
    grid = sheet.grids[VERIFIED]
    grid[1], grid[2] = grid[2], grid[1]  # sorted by someone: row 62 might be seed data
    with pytest.raises(SystemExit):
        sheets.reset(sheet)
    assert sheet.calls == []
    assert "REFUSED" in capsys.readouterr().err
