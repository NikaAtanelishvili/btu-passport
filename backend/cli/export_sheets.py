"""`python -m cli export-sheets [--xlsx FILE]` (SH-02): the seed CSV as the three registers of the
addendum's §4, ready for File → Import in Google Sheets. Every record is CONFIRMED and keeps its
REC- ID, so syncing the files against the seeded database changes nothing."""

import csv
from pathlib import Path

from app.config import REPO_ROOT
from app.sheets.source import COLUMNS, CSV_FILES, SKILLS, STUDENTS, TABS, VERIFIED
from cli.seed import SEED_CSV, SeedRow, parse_csv

OUT_DIR = REPO_ROOT / "seed" / "sheets"


def headers(tab: str) -> list[str]:
    required, optional = COLUMNS[tab]
    return [*required, *optional]


def tables(rows: list[SeedRow]) -> dict[str, list[list[str]]]:
    students = {r.student_id: r for r in rows}
    skills = {r.skill_id: r for r in rows}
    return {
        STUDENTS: [
            [
                s.student_id,
                s.first_name,
                s.last_name,
                s.email,
                s.program,
                s.education_level,
                s.status,
            ]
            for s in sorted(students.values(), key=lambda s: s.student_id)
        ],
        SKILLS: [
            [k.skill_id, k.skill_name, k.category, k.skill_description, k.badge_code]
            for k in sorted(skills.values(), key=lambda k: k.skill_id)
        ],
        VERIFIED: [
            [r.record_id, r.student_id, r.skill_id, r.date_earned.isoformat(), "CONFIRMED", ""]
            for r in sorted(rows, key=lambda r: r.record_id)
        ],
    }


def write_csvs(out_dir: Path = OUT_DIR) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for tab, body in tables(parse_csv(SEED_CSV)).items():
        with (out_dir / CSV_FILES[tab]).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(headers(tab))
            writer.writerows(body)
        counts[tab] = len(body)
    return counts


def write_xlsx(path: Path) -> None:
    """The same three tabs as one workbook, for the Excel import (SH-11)."""
    from openpyxl import Workbook

    book = Workbook()
    assert book.active is not None
    book.remove(book.active)
    data = tables(parse_csv(SEED_CSV))
    for tab in TABS:
        sheet = book.create_sheet(tab)
        sheet.append(headers(tab))
        for row in data[tab]:
            sheet.append(row)
    book.save(path)


def main(xlsx: str | None = None) -> None:
    counts = write_csvs()
    summary = ", ".join(f"{CSV_FILES[t]} {n} rows" for t, n in counts.items())
    print(f"export-sheets: {OUT_DIR.relative_to(REPO_ROOT)}/: {summary}")
    if xlsx:
        write_xlsx(Path(xlsx))
        print(f"export-sheets: {xlsx}")
