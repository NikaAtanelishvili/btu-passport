"""SH-11: Excel import runs the same engine through FileSource, as a run with trigger UPLOAD."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AuditLog, PassportVersion, SheetSyncRun, SkillAward
from app.sheets import sync
from cli import export_sheets

pytestmark = pytest.mark.usefixtures("s3_bucket")
ClientAs = Callable[[str | None], TestClient]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def upload(client: TestClient, data: bytes, name: str = "passports.xlsx") -> Any:
    return client.post("/api/admin/sheet-sync/upload", files={"file": (name, data, XLSX)})


def test_seed_workbook_changes_nothing(
    seeded: Session, client_as: ClientAs, tmp_path: Path
) -> None:
    export_sheets.write_xlsx(tmp_path / "seed.xlsx")
    before = (
        seeded.scalar(select(func.count()).select_from(SkillAward)),
        seeded.scalar(select(func.count()).select_from(PassportVersion)),
    )
    r = upload(client_as("admin"), (tmp_path / "seed.xlsx").read_bytes())
    assert r.status_code == 201, r.text
    run = r.json()
    assert (run["trigger"], run["status"], run["source"]) == (
        "UPLOAD",
        "DONE",
        "upload passports.xlsx",
    )
    assert run["counts"]["Students"] == {"UNCHANGED": 18}
    assert run["counts"]["Skills Catalog"] == {"UNCHANGED": 16}
    assert run["counts"]["Verified Skills"] == {"DUPLICATE": 60}
    seeded.expire_all()
    after = (
        seeded.scalar(select(func.count()).select_from(SkillAward)),
        seeded.scalar(select(func.count()).select_from(PassportVersion)),
    )
    assert after == before
    assert seeded.scalar(select(AuditLog).where(AuditLog.action == "sheet.sync.upload"))


def test_new_row_in_the_workbook_is_processed(
    seeded: Session, client_as: ClientAs, tmp_path: Path
) -> None:
    path = tmp_path / "seed.xlsx"
    export_sheets.write_xlsx(path)
    book = load_workbook(path)
    book["Verified Skills"].append(
        ["REC-0102", "BTU-T-0001", "SKL-003", "2026-10-27", "CONFIRMED", ""]
    )
    book.save(path)
    run = upload(client_as("admin"), path.read_bytes()).json()
    assert run["counts"]["Verified Skills"] == {"DUPLICATE": 60, "PROCESSED": 1}
    assert run["counts"]["versions"] == 1


def test_bad_files_and_busy(seeded: Session, client_as: ClientAs, tmp_path: Path) -> None:
    admin = client_as("admin")
    bad = upload(admin, b"not a workbook")
    assert bad.status_code == 422
    assert bad.json()["fields"]["file"] == "Not a readable .xlsx file (BadZipFile)"
    wrong = upload(admin, b"x", name="data.csv")
    assert wrong.json()["fields"]["file"] == "Upload an .xlsx file."
    huge = upload(admin, b"x" * (5 * 1024 * 1024 + 1))
    assert huge.json()["fields"]["file"] == "The file is larger than 5 MB."
    assert seeded.scalar(select(func.count()).select_from(SheetSyncRun)) == 1  # the unreadable one
    with SessionLocal() as db, db.begin():
        sync.create_run(db, "SCHEDULE", "Google Sheet")
    export_sheets.write_xlsx(tmp_path / "seed.xlsx")
    busy = upload(admin, (tmp_path / "seed.xlsx").read_bytes())
    assert busy.status_code == 409
    assert busy.json()["error"] == "sync_running"


def test_students_get_403(client_as: ClientAs) -> None:
    assert upload(client_as("student"), b"x").status_code == 403
