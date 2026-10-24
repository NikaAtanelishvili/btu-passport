"""Events (BE-44): list and detail for both admin roles; every write needs a super admin
(DEFAULT(Q14): admins view events read-only)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import SuperAdminUser
from app.db import get_db
from app.models import Event, EventParticipant, Skill
from app.schemas.common import Page
from app.schemas.event import (
    CompleteOut,
    EventCreate,
    EventDetail,
    EventPatch,
    EventRow,
    EventStatus,
    Participant,
    ParticipantAdd,
)
from app.services import events

router = APIRouter(tags=["admin: events"])
DB = Annotated[Session, Depends(get_db)]


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("/events", response_model=Page[EventRow])
def list_events(
    db: DB,
    status: EventStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[EventRow]:
    """Deleted events are excluded."""
    live = (
        select(EventParticipant.event_id, func.count().label("n"))
        .where(EventParticipant.removed_at.is_(None))
        .group_by(EventParticipant.event_id)
        .subquery()
    )
    stmt = (
        select(Event, Skill.name, func.coalesce(live.c.n, 0))
        .join(Skill, Skill.skill_id == Event.skill_id)
        .outerjoin(live, live.c.event_id == Event.event_id)
        .where(Event.deleted_at.is_(None))
    )
    if status:
        stmt = stmt.where(Event.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(Event.starts_at.desc(), Event.event_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        EventRow(
            event_id=e.event_id,
            name=e.name,
            skill_name=skill_name,
            starts_at=e.starts_at,
            participant_count=n,
            status=e.status,
        )
        for e, skill_name, n in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/events", status_code=201, response_model=EventDetail)
def create_event(body: EventCreate, principal: SuperAdminUser, db: DB) -> EventDetail:
    """Window defaults: opens = ends - 15 min, closes = ends + 30 min."""
    event = events.create(db, principal, body)
    return events.detail(db, event.event_id)


@router.get("/events/{event_id}", response_model=EventDetail)
def get_event(event_id: uuid.UUID, db: DB) -> EventDetail:
    return events.detail(db, event_id)


@router.patch("/events/{event_id}", response_model=EventDetail)
def update_event(
    event_id: uuid.UUID, body: EventPatch, principal: SuperAdminUser, db: DB
) -> EventDetail:
    """409 skill_locked once someone has checked in; 409 event_completed."""
    events.update(db, principal, event_id, body)
    return events.detail(db, event_id)


@router.delete("/events/{event_id}", status_code=204, response_class=Response)
def delete_event(event_id: uuid.UUID, principal: SuperAdminUser, db: DB) -> Response:
    """Soft delete; 409 event_completed (A16)."""
    events.delete(db, principal, event_id)
    return Response(status_code=204)


@router.post("/events/{event_id}/open", response_model=EventDetail)
def open_checkin(event_id: uuid.UUID, principal: SuperAdminUser, db: DB) -> EventDetail:
    events.open_checkin(db, principal, event_id, _now())
    return events.detail(db, event_id)


@router.post("/events/{event_id}/close", response_model=EventDetail)
def close_checkin(event_id: uuid.UUID, principal: SuperAdminUser, db: DB) -> EventDetail:
    events.close_checkin(db, principal, event_id, _now())
    return events.detail(db, event_id)


@router.post("/events/{event_id}/reopen", response_model=EventDetail)
def reopen_checkin(event_id: uuid.UUID, principal: SuperAdminUser, db: DB) -> EventDetail:
    events.reopen_checkin(db, principal, event_id, _now())
    return events.detail(db, event_id)


@router.post("/events/{event_id}/complete", response_model=CompleteOut)
def complete_event(event_id: uuid.UUID, principal: SuperAdminUser, db: DB) -> CompleteOut:
    """Mark as done. 409 cannot_complete with `blockers`; a repeat returns the stored
    response and creates nothing (A15)."""
    return events.complete(db, principal, event_id)


@router.get("/events/{event_id}/participants", response_model=list[Participant])
def list_participants(
    event_id: uuid.UUID, db: DB, include_removed: bool = False
) -> list[Participant]:
    return events.participants(db, events.get_live(db, event_id), include_removed=include_removed)


@router.post("/events/{event_id}/participants", status_code=201, response_model=Participant)
def add_participant(
    event_id: uuid.UUID, body: ParticipantAdd, principal: SuperAdminUser, db: DB
) -> Participant:
    """Manual add; 409 already_checked_in if present."""
    return events.add_participant(db, principal, event_id, body.student_id)


@router.delete("/events/{event_id}/participants/{email}", status_code=204, response_class=Response)
def remove_participant(
    event_id: uuid.UUID, email: str, principal: SuperAdminUser, db: DB
) -> Response:
    events.remove_participant(db, principal, event_id, email)
    return Response(status_code=204)
