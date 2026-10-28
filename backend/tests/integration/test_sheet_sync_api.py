"""SH-05: the SHEET_SYNC job, its schedule and /api/admin/sheet-sync*."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import AuditLog, Job, SheetSyncRun
from app.sheets import service, sync
from app.sheets.source import VERIFIED
from tests.integration.test_sheet_sync import TableSource, record

pytestmark = pytest.mark.usefixtures("s3_bucket")
ClientAs = Callable[[str | None], TestClient]


@pytest.fixture
def sheet(seeded: Session, monkeypatch: pytest.MonkeyPatch) -> TableSource:
    """A configured Sheet whose content is the seed export plus the test's rows."""
    monkeypatch.setattr(get_settings(), "google_sheets_id", "test-sheet")
    table = TableSource()
    monkeypatch.setattr(service, "source_for_run", lambda: table)
    return table


def runs(db: Session) -> list[SheetSyncRun]:
    db.expire_all()
    return list(db.scalars(select(SheetSyncRun).order_by(SheetSyncRun.run_id)))


def test_manual_sync(
    seeded: Session, sheet: TableSource, client_as: ClientAs, run_jobs: Callable[[], int]
) -> None:
    sheet.add(VERIFIED, record("REC-0102", "BTU-T-0001", "SKL-003"))
    admin = client_as("admin")
    first = admin.post("/api/admin/sheet-sync")
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "QUEUED" and not first.json()["already_running"]
    # A second request while one waits returns the same run.
    second = admin.post("/api/admin/sheet-sync")
    assert second.json() == {**first.json(), "already_running": True}
    assert (
        admin.get("/api/admin/sheet-sync/status").json()["active_run_id"] == first.json()["run_id"]
    )

    run_jobs()
    [run] = runs(seeded)
    assert (run.run_id, run.trigger, run.status) == (first.json()["run_id"], "MANUAL", "DONE")
    assert run.counts[VERIFIED] == {"DUPLICATE": 60, "PROCESSED": 1}
    assert seeded.scalar(select(AuditLog).where(AuditLog.action == "sheet.sync.request"))

    status = admin.get("/api/admin/sheet-sync/status").json()
    assert status["configured"] is True and status["active_run_id"] is None
    assert status["last_run"]["status"] == "DONE"
    assert status["last_success_at"] is not None
    assert status["next_run_at"] is not None
    listed = admin.get("/api/admin/sheet-sync/runs").json()
    assert listed["total"] == 1 and listed["items"][0]["run_id"] == run.run_id


def test_while_running_the_running_run_is_returned(
    seeded: Session, sheet: TableSource, client_as: ClientAs
) -> None:
    admin = client_as("admin")
    run_id = admin.post("/api/admin/sheet-sync").json()["run_id"]
    seeded.execute(update(SheetSyncRun).values(status="RUNNING"))
    seeded.commit()
    again = admin.post("/api/admin/sheet-sync").json()
    assert again == {"run_id": run_id, "status": "RUNNING", "already_running": True}


def test_scheduled_sync(seeded: Session, sheet: TableSource, run_jobs: Callable[[], int]) -> None:
    first = service.tick(seeded)
    seeded.commit()
    assert first is not None
    assert service.tick(seeded) is None  # one queued already
    run_jobs()
    assert service.tick(seeded) is None  # not due: the interval counts from the last run
    interval = get_settings().sheet_sync_interval_seconds
    seeded.execute(
        update(SheetSyncRun).values(
            created_at=SheetSyncRun.created_at - timedelta(seconds=interval + 1)
        )
    )
    seeded.commit()
    second = service.tick(seeded)
    seeded.commit()
    assert second is not None and second != first
    run_jobs()
    assert [(r.trigger, r.status) for r in runs(seeded)] == [("SCHEDULE", "DONE")] * 2
    job = seeded.scalars(select(Job).where(Job.type == "SHEET_SYNC")).first()
    assert job is not None and job.dedupe_key == "sheet-sync" and job.max_attempts == 1


def test_disabled_without_a_sheet(seeded: Session, client_as: ClientAs) -> None:
    assert service.tick(seeded) is None
    response = client_as("admin").post("/api/admin/sheet-sync")
    assert response.status_code == 409
    assert response.json()["error"] == "sheets_not_configured"
    assert runs(seeded) == []


def test_failures_end_the_run(
    seeded: Session,
    sheet: TableSource,
    monkeypatch: pytest.MonkeyPatch,
    run_jobs: Callable[[], int],
) -> None:
    sheet.fail = "No Sheet with this GOOGLE_SHEETS_ID"
    service.enqueue(seeded, "MANUAL")
    seeded.commit()
    run_jobs()
    assert [(r.status, r.error) for r in runs(seeded)] == [
        ("FAILED", "No Sheet with this GOOGLE_SHEETS_ID")
    ]

    # A crash outside the engine: the job gives up after its one attempt and fails the run.
    def boom(run_id: int, source: Any) -> None:
        raise RuntimeError("worker lost the database")

    monkeypatch.setattr(sync, "execute", boom)
    service.enqueue(seeded, "MANUAL")
    seeded.commit()
    run_jobs()
    last = runs(seeded)[-1]
    assert last.status == "FAILED"
    assert last.error == "The sync job failed: worker lost the database"


def test_records_listing(
    seeded: Session, sheet: TableSource, client_as: ClientAs, run_jobs: Callable[[], int]
) -> None:
    sheet.add(
        VERIFIED,
        record("REC-0102", "BTU-T-0001", "SKL-003"),
        record("REC-0105", "BTU-T-9999", "SKL-001"),
    )
    sync.sync_now(sheet)
    admin = client_as("admin")
    page = admin.get("/api/admin/sheet-sync/records", params={"page_size": 3}).json()
    assert page["total"] == 18 + 16 + 62
    first = page["items"][0]  # errors and flags first
    assert (first["key"], first["outcome"], first["message"]) == (
        "REC-0105",
        "ERROR",
        "Unknown student BTU-T-9999",
    )
    assert first["student_id"] is None
    processed = admin.get("/api/admin/sheet-sync/records", params={"outcome": "PROCESSED"}).json()
    [row] = processed["items"]
    assert (row["key"], row["row_number"], row["student_id"], row["passport_id"]) == (
        "REC-0102",
        62,
        "BTU-T-0001",
        "BTU-AI-000125",
    )
    assert row["version_no"] is not None and row["version_id"] is not None
    students = admin.get(
        "/api/admin/sheet-sync/records", params={"tab": "Students", "q": "0002"}
    ).json()
    assert [(r["key"], r["student_id"]) for r in students["items"]] == [
        ("BTU-T-0002", "BTU-T-0002")
    ]
    bad = admin.get("/api/admin/sheet-sync/records", params={"outcome": "SYNCED", "tab": "X"})
    assert bad.status_code == 422
    assert set(bad.json()["fields"]) == {"outcome", "tab"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/admin/sheet-sync"),
        ("get", "/api/admin/sheet-sync/status"),
        ("get", "/api/admin/sheet-sync/runs"),
        ("get", "/api/admin/sheet-sync/records"),
    ],
)
def test_students_get_403(client_as: ClientAs, method: str, path: str) -> None:
    assert getattr(client_as("student"), method)(path).status_code == 403
    assert getattr(client_as(None), method)(path).status_code == 401


def test_a_run_left_without_its_job_is_picked_up(
    seeded: Session, sheet: TableSource, run_jobs: Callable[[], int]
) -> None:
    """Seen live: a stale SHEET_SYNC job for a run that had already finished took the dedupe
    key, so the next run got no job and stayed QUEUED, blocking every later sync."""
    from app.services import jobs

    with SessionLocal() as db, db.begin():
        done = sync.create_run(db, "MANUAL", "Google Sheet")
    sync.execute(done, sheet)  # finished outside the worker; its job is still queued
    jobs.enqueue(seeded, "SHEET_SYNC", {"run_id": done}, dedupe_key="sheet-sync", max_attempts=1)
    seeded.commit()
    orphan = service.enqueue(seeded, "MANUAL").run_id  # the dedupe key is taken: no job
    seeded.commit()
    run_jobs()  # the stale job runs the active run instead of its finished one
    assert [(r.run_id, r.status) for r in runs(seeded)] == [(done, "DONE"), (orphan, "DONE")]

    # And a QUEUED run with no job at all gets one from the next tick.
    seeded.add(SheetSyncRun(trigger="SCHEDULE", status="QUEUED", source="Google Sheet"))
    seeded.commit()
    assert service.tick(seeded) is None
    seeded.commit()
    run_jobs()
    assert runs(seeded)[-1].status == "DONE"
