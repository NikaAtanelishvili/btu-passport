"""Admin dashboard counters and recent activity (BE-35, page A1). Both admin roles."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Event, EventParticipant, Passport, PassportVersion, Student
from app.schemas.dashboard import Dashboard
from app.schemas.version import version_row

router = APIRouter(tags=["admin: dashboard"])


@router.get("/dashboard", response_model=Dashboard)
def dashboard(db: Annotated[Session, Depends(get_db)]) -> Dashboard:
    def events_in(*statuses: str) -> int:
        stmt = select(func.count()).where(Event.status.in_(statuses), Event.deleted_at.is_(None))
        return db.scalar(stmt) or 0

    unregistered = (
        select(func.count())
        .select_from(EventParticipant)
        .join(Event, Event.event_id == EventParticipant.event_id)
        .where(
            EventParticipant.student_id.is_(None),
            EventParticipant.removed_at.is_(None),
            Event.deleted_at.is_(None),
            Event.status != "COMPLETED",
        )
    )
    failed = select(func.count()).where(PassportVersion.status == "FAILED")
    recent = db.execute(
        select(PassportVersion, Student)
        .join(Passport, Passport.passport_id == PassportVersion.passport_id)
        .join(Student, Student.student_id == Passport.student_id)
        .where(PassportVersion.status == "ANCHORED")
        .order_by(
            PassportVersion.issued_at.desc().nulls_last(),
            PassportVersion.version_id.desc(),
        )
        .limit(10)
    ).all()
    return Dashboard(
        checkin_open=events_in("CHECKIN_OPEN"),
        awaiting_completion=events_in("CHECKIN_CLOSED"),
        unregistered_checkins=db.scalar(unregistered) or 0,
        failed_versions=db.scalar(failed) or 0,
        recent=[version_row(v, s) for v, s in recent],
    )
