"""Check-in by QR (BE-42, FR-28 - FR-30). Any signed-in BTU user may check in; one row per
email per event (FR-29), recorded as Unregistered when the email has no student record.

A signed-out scan swaps the QR token for a check-in pass (`issue_pass`), checked here in place
of the token after sign-in. A pass is single use: its nonce is stored on the row it creates."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Event, EventParticipant, Skill, SkillAward, SkillCategory
from app.schemas.event import (
    CheckinEvent,
    CheckinEventSkill,
    CheckinPass,
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


def _open_state(event: Event | None) -> CheckinState | None:
    if event is None:
        return "NOT_FOUND"
    if event.status == "DRAFT":
        return "NOT_OPEN"
    if event.status in ("CHECKIN_CLOSED", "COMPLETED"):
        return "CLOSED"
    return None


def _unused_pass(db: Session, event: Event, p: str, now: datetime) -> str | None:
    """The nonce of a valid pass for this event that no check-in has used yet."""
    nonce = qr_tokens.read_pass(event.qr_secret, event.event_id, p, now) if p else None
    if nonce is None:
        return None
    used = exists().where(
        EventParticipant.event_id == event.event_id, EventParticipant.pass_nonce == nonce
    )
    return None if db.scalar(select(used)) else nonce


def _state(
    db: Session, principal: "Principal", event: Event | None, t: str, p: str, now: datetime
) -> tuple[CheckinState, str | None]:
    """The plan's order: missing/deleted, own row removed, own row, not open, closed, token
    (or pass). Returns the state and, when a pass is what lets the caller in, its nonce."""
    if event is None:
        return "NOT_FOUND", None
    row = db.scalar(
        select(EventParticipant).where(
            EventParticipant.event_id == event.event_id,
            EventParticipant.email == principal.user.email,
        )
    )
    if row is not None:
        return ("REMOVED" if row.removed_at is not None else "CHECKED_IN"), None
    closed = _open_state(event)
    if closed is not None:
        return closed, None
    if qr_tokens.is_valid(event.qr_secret, event.event_id, t, now):
        return "CONFIRM", None
    nonce = _unused_pass(db, event, p, now)
    return ("CONFIRM", nonce) if nonce is not None else ("TOKEN_EXPIRED", None)


def _fail(state: CheckinState) -> AppError:
    return AppError(
        state.lower(), _MESSAGES[state], _POST_STATUS.get(state, 409), extra={"state": state}
    )


def issue_pass(db: Session, event_id: str, t: str) -> CheckinPass:
    """A signed-out scan: check the event and the QR token now, and hand out a pass that
    survives sign-in. Public; an expired token gets no pass (409 TOKEN_EXPIRED)."""
    event = _event(db, event_id)
    now = datetime.now(UTC)
    state = _open_state(event)
    if state is None:
        assert event is not None
        if not qr_tokens.is_valid(event.qr_secret, event.event_id, t, now):
            state = "TOKEN_EXPIRED"
    if state is not None:
        raise _fail(state)
    assert event is not None
    return CheckinPass(
        pass_=qr_tokens.issue_pass(event.qr_secret, event.event_id, now),
        expires_at=now.replace(microsecond=0) + timedelta(seconds=qr_tokens.PASS_SECONDS),
    )


def view(db: Session, principal: "Principal", event_id: str, t: str, p: str) -> CheckinView:
    """GET: what the check-in page shows. Never writes."""
    event = _event(db, event_id)
    state, _ = _state(db, principal, event, t, p, datetime.now(UTC))
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


def check_in(db: Session, principal: "Principal", event_id: str, t: str, p: str) -> CheckinResult:
    """POST: records the check-in; a repeat returns the same body (no second row)."""
    event = _event(db, event_id)
    state, nonce = _state(db, principal, event, t, p, datetime.now(UTC))
    if state not in ("CONFIRM", "CHECKED_IN"):
        raise _fail(state)
    assert event is not None
    if state == "CONFIRM":
        # No conflict target: a duplicate email (a repeat) or a pass someone else just used
        # (UNIQUE event_id, pass_nonce) both insert nothing; only the second is a failure.
        inserted = db.scalar(
            insert(EventParticipant)
            .values(
                event_id=event.event_id,
                email=principal.user.email,
                student_id=principal.student.student_id if principal.student else None,
                display_name=principal.user.display_name,
                method="QR",
                pass_nonce=nonce,
            )
            .on_conflict_do_nothing()
            .returning(EventParticipant.id)
        )
        if inserted is None and nonce is not None:
            mine = select(EventParticipant.id).where(
                EventParticipant.event_id == event.event_id,
                EventParticipant.email == principal.user.email,
            )
            if db.scalar(mine) is None:
                raise _fail("TOKEN_EXPIRED")
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
