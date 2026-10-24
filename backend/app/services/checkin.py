"""Check-in by QR (BE-42, FR-28 - FR-30). Any signed-in BTU user may check in; one row per
email per event (FR-29), recorded as Unregistered when the email has no student record."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Event, EventParticipant, Skill, SkillAward, SkillCategory
from app.schemas.event import (
    CheckinEvent,
    CheckinEventSkill,
    CheckinResult,
    CheckinState,
    CheckinView,
)
from app.services import qr_tokens

if TYPE_CHECKING:
    from app.auth.deps import Principal

# Status codes for a POST that can't check in; the body carries the state for the page.
_POST_STATUS = {"NOT_FOUND": 404}


def _event(db: Session, event_id: str) -> Event | None:
    try:
        eid = uuid.UUID(event_id)
    except ValueError:
        return None
    event = db.get(Event, eid)
    return event if event is not None and event.deleted_at is None else None


def _holds_skill(db: Session, principal: "Principal", event: Event) -> bool:
    if principal.student is None:
        return False
    stmt = exists().where(
        SkillAward.student_id == principal.student.student_id,
        SkillAward.skill_id == event.skill_id,
    )
    return bool(db.scalar(select(stmt)))


def _state(
    db: Session, principal: "Principal", event: Event | None, t: str, now: datetime
) -> CheckinState:
    """The plan's order: missing/deleted, own row removed, own row, not open, closed, token."""
    if event is None:
        return "NOT_FOUND"
    row = db.scalar(
        select(EventParticipant).where(
            EventParticipant.event_id == event.event_id,
            EventParticipant.email == principal.user.email,
        )
    )
    if row is not None:
        return "REMOVED" if row.removed_at is not None else "CHECKED_IN"
    if event.status == "DRAFT":
        return "NOT_OPEN"
    if event.status in ("CHECKIN_CLOSED", "COMPLETED"):
        return "CLOSED"
    if not qr_tokens.is_valid(event.qr_secret, event.event_id, t, now):
        return "TOKEN_EXPIRED"
    return "CONFIRM"


def view(db: Session, principal: "Principal", event_id: str, t: str) -> CheckinView:
    """GET: what the check-in page shows. Never writes."""
    event = _event(db, event_id)
    state = _state(db, principal, event, t, datetime.now(UTC))
    if event is None:
        return CheckinView(event=None, state=state)
    skill, category = db.execute(
        select(Skill, SkillCategory)
        .join(SkillCategory, SkillCategory.category_id == Skill.category_id)
        .where(Skill.skill_id == event.skill_id)
    ).one()
    return CheckinView(
        event=CheckinEvent(
            name=event.name,
            description=event.description,
            starts_at=event.starts_at,
            location=event.location,
            skill=CheckinEventSkill(
                name=skill.name, category=category.name, stamp_sha256=category.stamp_sha256
            ),
        ),
        state=state,
        unregistered=principal.student is None,
        already_holds_skill=_holds_skill(db, principal, event),
    )


def check_in(db: Session, principal: "Principal", event_id: str, t: str) -> CheckinResult:
    """POST: records the check-in; a repeat returns the same body (no second row)."""
    event = _event(db, event_id)
    state = _state(db, principal, event, t, datetime.now(UTC))
    if state not in ("CONFIRM", "CHECKED_IN"):
        raise AppError(
            state.lower(),
            _MESSAGES[state],
            _POST_STATUS.get(state, 409),
            extra={"state": state},
        )
    assert event is not None
    if state == "CONFIRM":
        db.execute(
            insert(EventParticipant)
            .values(
                event_id=event.event_id,
                email=principal.user.email,
                student_id=principal.student.student_id if principal.student else None,
                display_name=principal.user.display_name,
                method="QR",
            )
            .on_conflict_do_nothing(index_elements=["event_id", "email"])
        )
        db.flush()
    return CheckinResult(
        state="CHECKED_IN",
        unregistered=principal.student is None,
        already_holds_skill=_holds_skill(db, principal, event),
    )


_MESSAGES: dict[str, str] = {
    "NOT_FOUND": "Event not found.",
    "REMOVED": "The organiser removed your check-in.",
    "NOT_OPEN": "Check-in hasn't opened yet.",
    "CLOSED": "Check-in has closed.",
    "TOKEN_EXPIRED": "This code has expired. Scan the code on the screen again.",
}
