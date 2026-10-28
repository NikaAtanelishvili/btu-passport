"""Google Sheets sync API shapes (SH-05, SH-07)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SheetRunOut(BaseModel):
    run_id: int
    trigger: str
    status: str
    source: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    counts: dict[str, Any]  # {tab: {outcome: n}, "versions": n, "seconds": s}
    error: str | None


class SheetStatus(BaseModel):
    configured: bool  # GOOGLE_SHEETS_ID set: scheduled syncs run
    writeback: bool
    interval_seconds: int
    last_run: SheetRunOut | None
    last_success_at: datetime | None
    next_run_at: datetime | None
    active_run_id: int | None
    errors: int  # records whose last outcome is ERROR
    flags: int  # CHANGED_AFTER_PROCESSING, REVOKED_IN_SHEET, CONFLICT


class SyncRequested(BaseModel):
    run_id: int
    status: str
    already_running: bool  # a run was queued or running; its ID is returned


class SheetRecordRow(BaseModel):
    tab: str
    key: str
    row_number: int
    outcome: str
    message: str | None
    first_seen_at: datetime
    decided_at: datetime
    student_id: str | None  # for the link to the student page
    passport_id: str | None
    version_id: int | None
    version_no: int | None
