"""`python -m cli bench` (SH-12): the measurements behind docs/deliverables/scaling-vision.md.

Runs only against a database whose name ends in `_bench` (it creates thousands of students):

    DATABASE_URL=postgresql+psycopg://passport:passport@localhost:5432/passport_bench \\
    S3_BUCKET=passports-bench uv run python -m cli bench

Measures: PDF render time and size (6 and 25 skills); one Sheet sync of N new students with
3 CONFIRMED records each (first run, then an unchanged repeat); the Merkle tree for a full batch.
"""

import csv
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal, get_engine
from app.models import PassportVersion
from app.pdf.render import render_passport
from app.services import content, issuance, merkle, storage
from app.sheets import sync
from app.sheets.source import CSV_FILES, SKILLS, STUDENTS, VERIFIED, FileSource
from cli import export_sheets, seed

STUDENTS_N = 5000
RECORDS_PER_STUDENT = 3
RENDERS = 10


def _pdf_times() -> dict[str, float]:
    with SessionLocal() as db, db.begin():
        [made] = issuance.create_versions(db, ["BTU-T-0007"])  # the seed student with 6 skills
        version = db.get_one(PassportVersion, made.version_id)
        c = content.build_content(
            db, version, verification_code="K7QM3XWP9D", issued_at=datetime.now(UTC)
        )
        db.rollback()
    out = {}
    for n in (6, 25):
        c = {**c, "skills": [{**c["skills"][i % 6], "name": f"Skill {i}"} for i in range(n)]}
        render_passport(c)  # warm-up: fonts and the BTU mark are loaded once per process
        times = []
        for _ in range(RENDERS):
            start = time.perf_counter()
            pdf = render_passport(c)
            times.append(time.perf_counter() - start)
        out[f"render_{n}_skills_median_s"] = round(statistics.median(times), 3)
        out[f"pdf_{n}_skills_kb"] = round(len(pdf) / 1024)
    return out


def _write_sheet(folder: Path) -> None:
    export_sheets.write_csvs(folder)
    skills = [f"SKL-{i:03d}" for i in range(1, 17)]
    with (folder / CSV_FILES[STUDENTS]).open("a", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        for i in range(STUDENTS_N):
            sid = f"BTU-T-{10000 + i}"
            w.writerow([sid, "Bench", f"Student {i}", f"{sid.lower()}@example.org", "IT",
                        "BACHELOR", "ACTIVE"])  # fmt: skip
    with (folder / CSV_FILES[VERIFIED]).open("a", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        n = 1000
        for i in range(STUDENTS_N):
            for k in range(RECORDS_PER_STUDENT):
                n += 1
                w.writerow([f"REC-{n:06d}", f"BTU-T-{10000 + i}", skills[(i + k) % 16],
                            "2026-10-20", "CONFIRMED", "Bench"])  # fmt: skip


def main() -> None:
    url = get_engine().url
    if not (url.database or "").endswith("_bench"):
        raise SystemExit(f"bench: refused: database {url.database!r} doesn't end in _bench")
    storage.ensure_bucket()
    with SessionLocal() as db, db.begin():
        seed.run(db)
    results: dict[str, object] = dict(_pdf_times())

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        _write_sheet(folder)
        source = FileSource(folder)
        tabs = source.read()
        results["sheet_rows"] = {name: len(tab.rows) for name, tab in tabs.items()}
        for label in ("first_sync", "repeat_sync"):
            start = time.perf_counter()
            result = sync.sync_now(source)
            results[f"{label}_s"] = round(time.perf_counter() - start, 1)
            results[f"{label}_versions"] = result.versions
            results[f"{label}_verified"] = result.counts.get(VERIFIED)
            results[f"{label}_students"] = result.counts.get(STUDENTS)
            results[f"{label}_skills"] = result.counts.get(SKILLS)
    with SessionLocal() as db:
        results["versions_pending"] = db.scalar(
            select(func.count()).where(PassportVersion.status == "PENDING")
        )

    leaves = [f"{i:064x}" for i in range(get_settings().batch_max_leaves)]
    start = time.perf_counter()
    merkle.build_tree(leaves)
    results["merkle_tree_full_batch_s"] = round(time.perf_counter() - start, 3)
    results["batch_max_leaves"] = len(leaves)
    for key, value in results.items():
        print(f"{key}: {value}")
