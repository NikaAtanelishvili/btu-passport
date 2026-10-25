"""Audit log (BE-53, FR-09): super admin only, newest first. Dates are BTU's calendar days
(TIMEZONE), both ends included."""

from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import SuperAdminUser
from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.models import AuditLog
from app.schemas.audit import AuditRow
from app.schemas.common import Page

router = APIRouter(tags=["admin: audit"])
DB = Annotated[Session, Depends(get_db)]


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time(), ZoneInfo(get_settings().timezone))


@router.get("/audit", response_model=Page[AuditRow])
def list_audit(
    principal: SuperAdminUser,
    db: DB,
    actor: Annotated[str | None, Query(description="Part of the person's email")] = None,
    action: str | None = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[AuditRow]:
    if from_ and to and to < from_:
        raise AppError(
            "validation_error", "Some fields are invalid.", 422, {"to": "Must not be before From."}
        )
    stmt = select(AuditLog)
    if actor and actor.strip():
        stmt = stmt.where(AuditLog.actor_email.ilike(f"%{actor.strip()}%"))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if from_:
        stmt = stmt.where(AuditLog.at >= _day_start(from_))
    if to:
        stmt = stmt.where(AuditLog.at < _day_start(to + timedelta(days=1)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AuditLog.at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(
        items=[AuditRow.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/audit/actions", response_model=list[str])
def audit_actions(principal: SuperAdminUser, db: DB) -> list[str]:
    """Every action name in the log, for the page's action filter."""
    return list(db.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)))
