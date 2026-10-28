"""Google Sheets sync (SH-05): Sync now, status, runs and per-row records. Both admin roles."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import AdminUser
from app.db import get_db
from app.errors import AppError
from app.models.base import SHEET_OUTCOMES, SHEET_TABS
from app.schemas.common import Page
from app.schemas.sheets import SheetRecordRow, SheetRunOut, SheetStatus, SyncRequested
from app.sheets import service

router = APIRouter(tags=["admin: google sheets"])
DB = Annotated[Session, Depends(get_db)]


@router.post("/sheet-sync", status_code=202, response_model=SyncRequested)
def sync_now(principal: AdminUser, db: DB) -> SyncRequested:
    """Queue a sync now; while one is queued or running, its run ID is returned instead."""
    if not service.configured():
        raise AppError(
            "sheets_not_configured", "No Google Sheet is configured (GOOGLE_SHEETS_ID).", 409
        )
    return service.enqueue(db, "MANUAL", principal)


@router.get("/sheet-sync/status", response_model=SheetStatus)
def sync_status(db: DB) -> SheetStatus:
    return service.status(db)


@router.get("/sheet-sync/runs", response_model=Page[SheetRunOut])
def list_runs(
    db: DB,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[SheetRunOut]:
    return service.list_runs(db, page, page_size)


@router.get("/sheet-sync/records", response_model=Page[SheetRecordRow])
def list_records(
    db: DB,
    outcome: Annotated[str | None, Query(description="Comma-separated outcomes")] = None,
    tab: str | None = None,
    q: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[SheetRecordRow]:
    fields = {}
    if outcome and (bad := {o.strip().upper() for o in outcome.split(",")} - set(SHEET_OUTCOMES)):
        fields["outcome"] = f"Unknown outcome: {', '.join(sorted(bad))}."
    if tab and tab not in SHEET_TABS:
        fields["tab"] = f"Use one of: {', '.join(SHEET_TABS)}."
    if fields:
        raise AppError("validation_error", "Some filters are invalid.", 422, fields)
    return service.list_records(db, outcome=outcome, tab=tab, q=q, page=page, page_size=page_size)
