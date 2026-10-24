"""Events (BE-40): lifecycle, the 15-second tick, soft delete and Mark as done (FR-26 - FR-32).

Completed events are read-only and can't be deleted; the trigger event_rules enforces the
same in SQL. Mark as done is idempotent: the event is the key (award_submissions.event_id is
UNIQUE), so a repeat returns the stored response.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select
from sqlalchemy import update as sql_update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import (
    AwardSubmission,
    Event,
    EventParticipant,
    Skill,
    SkillAward,
    SkillCategory,
)
from app.schemas.event import (
    AwardedStudent,
    CompleteOut,
    EventCounts,
    EventCreate,
    EventDetail,
    EventPatch,
    EventSkill,
    Participant,
)
from app.services import audit, issuance

if TYPE_CHECKING:
    from app.auth.deps import Principal

NAME_MAX = 120
DESCRIPTION_MAX = 500
OPENS_BEFORE_END = timedelta(minutes=15)  # DEFAULT(Q17): 15 min before the end
CLOSES_AFTER_END = timedelta(minutes=30)  # DEFAULT(Q17): 30 min after the end
EXTEND_BY = timedelta(minutes=30)  # open/reopen after the window gives it 30 more minutes
FIELDS = (
    "name",
    "skill_id",
    "description",
    "starts_at",
    "ends_at",
    "location",
    "checkin_opens_at",
    "checkin_closes_at",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _clean(db: Session, values: dict[str, Any], *, skill_changed: bool) -> dict[str, str]:
    """Field errors for a complete set of event values (normalised in place)."""
    fields: dict[str, str] = {}
    values["name"] = (values["name"] or "").strip()
    if not 1 <= len(values["name"]) <= NAME_MAX:
        fields["name"] = f"Required, at most {NAME_MAX} characters."
    for key in ("description", "location"):
        values[key] = (values[key] or "").strip() or None
    if values["description"] and len(values["description"]) > DESCRIPTION_MAX:
        fields["description"] = f"At most {DESCRIPTION_MAX} characters."
    if skill_changed:
        skill = db.get(Skill, values["skill_id"])
        if skill is None:
            fields["skill_id"] = "Choose a skill."
        elif skill.archived_at is not None:
            fields["skill_id"] = "This skill is archived."
    if values["ends_at"] <= values["starts_at"]:
        fields["ends_at"] = "The end must be after the start."
    if values["checkin_closes_at"] <= values["checkin_opens_at"]:
        fields["checkin_closes_at"] = "Check-in must close after it opens."
    return fields


def _snapshot(event: Event, keys: Any = FIELDS) -> dict[str, Any]:
    """Audit values: the given fields, datetimes as ISO strings."""
    values = {k: getattr(event, k) for k in keys}
    return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in values.items()}


def create(db: Session, actor: "Principal", body: EventCreate) -> Event:
    values = body.model_dump()
    values["checkin_opens_at"] = values["checkin_opens_at"] or body.ends_at - OPENS_BEFORE_END
    values["checkin_closes_at"] = values["checkin_closes_at"] or body.ends_at + CLOSES_AFTER_END
    if fields := _clean(db, values, skill_changed=True):
        raise AppError("validation_error", "Some fields are invalid.", 422, fields)
    event = Event(
        **values,
        event_id=uuid.uuid4(),
        status="DRAFT",
        qr_secret=os.urandom(32),
        created_by=actor.user.user_id,
    )
    db.add(event)
    db.flush()
    audit.record(db, actor, "event.create", "event", str(event.event_id), after=_snapshot(event))
    db.flush()
    return event


def get_live(db: Session, event_id: uuid.UUID, *, lock: bool = False) -> Event:
    """The event unless it is missing or soft-deleted (404)."""
    event = db.get(Event, event_id, with_for_update=lock)
    if event is None or event.deleted_at is not None:
        raise AppError("not_found", "No such event.", 404)
    return event


def _editable(db: Session, event_id: uuid.UUID) -> Event:
    event = get_live(db, event_id, lock=True)
    if event.status == "COMPLETED":
        raise AppError("event_completed", "A completed event is read-only.", 409)
    return event


def _has_participants(db: Session, event_id: uuid.UUID) -> bool:
    return bool(db.scalar(select(exists().where(EventParticipant.event_id == event_id))))


def update(db: Session, actor: "Principal", event_id: uuid.UUID, body: EventPatch) -> Event:
    event = _editable(db, event_id)
    given = body.model_dump(exclude_unset=True)
    values = {k: getattr(event, k) for k in FIELDS} | given
    skill_changed = values["skill_id"] != event.skill_id
    if skill_changed and _has_participants(db, event_id):
        raise AppError(
            "skill_locked",
            "The skill is locked: participants have checked in.",
            409,
            {"skill_id": "Locked: participants have checked in."},
        )
    if fields := _clean(db, values, skill_changed=skill_changed):
        raise AppError("validation_error", "Some fields are invalid.", 422, fields)
    changed = [k for k in FIELDS if values[k] != getattr(event, k)]
    if changed:
        before = _snapshot(event, changed)
        for k in changed:
            setattr(event, k, values[k])
        db.flush()
        audit.record(
            db, actor, "event.update", "event", str(event_id), before, _snapshot(event, changed)
        )
        db.flush()
    return event


def _transition(
    db: Session,
    actor: "Principal | None",
    event: Event,
    action: str,
    status: str,
    **times: datetime,
) -> Event:
    before = {"status": event.status, **_snapshot(event, list(times))}
    event.status = status
    for k, v in times.items():
        setattr(event, k, v)
    db.flush()
    after = {"status": status, **_snapshot(event, list(times))}
    audit.record(db, actor, action, "event", str(event.event_id), before, after)
    db.flush()
    return event


def _require(event: Event, *allowed: str) -> None:
    if event.status not in allowed:
        raise AppError(
            "invalid_transition",
            f"Not possible while the event is {event.status.replace('_', ' ').lower()}.",
            409,
        )


def open_checkin(db: Session, actor: "Principal", event_id: uuid.UUID, now: datetime) -> Event:
    event = _editable(db, event_id)
    _require(event, "DRAFT", "CHECKIN_CLOSED")
    closes = event.checkin_closes_at if event.checkin_closes_at > now else now + EXTEND_BY
    return _transition(
        db,
        actor,
        event,
        "event.open",
        "CHECKIN_OPEN",
        checkin_opens_at=min(event.checkin_opens_at, now),
        checkin_closes_at=closes,
    )


def close_checkin(db: Session, actor: "Principal", event_id: uuid.UUID, now: datetime) -> Event:
    event = _editable(db, event_id)
    _require(event, "CHECKIN_OPEN")
    opens = min(event.checkin_opens_at, now - timedelta(microseconds=1))
    return _transition(
        db,
        actor,
        event,
        "event.close",
        "CHECKIN_CLOSED",
        checkin_opens_at=opens,
        checkin_closes_at=now,
    )


def reopen_checkin(db: Session, actor: "Principal", event_id: uuid.UUID, now: datetime) -> Event:
    event = _editable(db, event_id)
    _require(event, "CHECKIN_CLOSED")
    return _transition(
        db, actor, event, "event.reopen", "CHECKIN_OPEN", checkin_closes_at=now + EXTEND_BY
    )


def tick(db: Session, now: datetime | None = None) -> int:
    """Worker, every 15 s: open DRAFT events whose window has started, close OPEN events
    whose window has ended. Audited with the system as actor. Returns events changed."""
    now = now or _now()
    due = db.scalars(
        select(Event)
        .where(
            Event.deleted_at.is_(None),
            (
                (Event.status == "DRAFT")
                & (Event.checkin_opens_at <= now)
                & (Event.checkin_closes_at > now)
            )
            | ((Event.status == "CHECKIN_OPEN") & (Event.checkin_closes_at <= now)),
        )
        .with_for_update(skip_locked=True)
    ).all()
    for event in due:
        if event.status == "DRAFT":
            _transition(db, None, event, "event.open", "CHECKIN_OPEN")
        else:
            _transition(db, None, event, "event.close", "CHECKIN_CLOSED")
    return len(due)


def delete(db: Session, actor: "Principal", event_id: uuid.UUID) -> None:
    """Soft delete (FR-27); check-ins stay so students see "Event deleted"."""
    event = _editable(db, event_id)
    event.deleted_at = _now()
    db.flush()
    audit.record(db, actor, "event.delete", "event", str(event_id), before={"status": event.status})
    db.flush()


# --- participants, flags, blockers -----------------------------------------------------


def _submission(db: Session, event_id: uuid.UUID) -> AwardSubmission | None:
    return db.scalar(select(AwardSubmission).where(AwardSubmission.event_id == event_id))


def participants(db: Session, event: Event, *, include_removed: bool = False) -> list[Participant]:
    """Check-ins with their flags. ALREADY_HOLDS ignores awards made by this event's own
    Mark as done, so a completed event still shows who was skipped."""
    own = _submission(db, event.event_id)
    holds = (
        select(SkillAward.award_id)
        .where(
            SkillAward.student_id == EventParticipant.student_id,
            SkillAward.skill_id == event.skill_id,
        )
        .exists()
    )
    if own is not None:
        holds = (
            select(SkillAward.award_id)
            .where(
                SkillAward.student_id == EventParticipant.student_id,
                SkillAward.skill_id == event.skill_id,
                SkillAward.submission_id != own.submission_id,
            )
            .exists()
        )
    stmt = (
        select(EventParticipant, holds)
        .where(EventParticipant.event_id == event.event_id)
        .order_by(EventParticipant.checked_in_at, EventParticipant.id)
    )
    if not include_removed:
        stmt = stmt.where(EventParticipant.removed_at.is_(None))
    rows = []
    for p, already in db.execute(stmt).all():
        flags: list[Any] = []
        if p.student_id is None:
            flags.append("UNREGISTERED")
        elif already:
            flags.append("ALREADY_HOLDS")
        rows.append(
            Participant(
                email=p.email,
                student_id=p.student_id,
                name=p.display_name,
                checked_in_at=p.checked_in_at,
                method=p.method,
                flags=flags,
                removed_at=p.removed_at,
            )
        )
    return rows


def _blockers(event: Event, live: list[Participant]) -> list[Any]:
    if event.status == "COMPLETED":
        return []
    blockers: list[Any] = []
    if event.status == "DRAFT":
        blockers.append("DRAFT")
    if event.status == "CHECKIN_OPEN":
        blockers.append("CHECKIN_OPEN")
    if any("UNREGISTERED" in p.flags for p in live):
        blockers.append("UNREGISTERED_PRESENT")
    if not live:
        blockers.append("NO_PARTICIPANTS")
    return blockers


def detail(db: Session, event_id: uuid.UUID) -> EventDetail:
    event = get_live(db, event_id)
    skill, category = db.execute(
        select(Skill, SkillCategory)
        .join(SkillCategory, SkillCategory.category_id == Skill.category_id)
        .where(Skill.skill_id == event.skill_id)
    ).one()
    live = participants(db, event)
    blockers = _blockers(event, live)
    submission = _submission(db, event_id)
    return EventDetail(
        event_id=event.event_id,
        name=event.name,
        skill_id=event.skill_id,
        description=event.description,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        location=event.location,
        checkin_opens_at=event.checkin_opens_at,
        checkin_closes_at=event.checkin_closes_at,
        status=event.status,
        skill=EventSkill(
            skill_id=skill.skill_id,
            name=skill.name,
            category=category.name,
            stamp_sha256=category.stamp_sha256,
        ),
        skill_locked=_has_participants(db, event_id),
        counts=EventCounts(
            total=len(live),
            unregistered=sum("UNREGISTERED" in p.flags for p in live),
            already_held=sum("ALREADY_HOLDS" in p.flags for p in live),
        ),
        can_complete=event.status == "CHECKIN_CLOSED" and not blockers,
        complete_blockers=blockers,
        completion=CompleteOut.model_validate(submission.response_json)
        if submission is not None and submission.response_json
        else None,
        completed_at=event.completed_at,
    )


def event_date(event: Event) -> Any:
    """The event's local date in TIMEZONE: the date earned of its awards."""
    return event.starts_at.astimezone(ZoneInfo(get_settings().timezone)).date()


def complete(db: Session, actor: "Principal", event_id: uuid.UUID) -> CompleteOut:
    """Mark as done (FR-31, FR-32): one EVENT submission; an award dated the event's local
    date for every live, registered participant who lacks the skill; one new version each.
    A repeat returns the stored response and creates nothing (A15)."""
    event = get_live(db, event_id, lock=True)  # serialises concurrent clicks
    stored = _submission(db, event_id)
    if stored is not None and stored.response_json:
        return CompleteOut.model_validate(stored.response_json)
    live = participants(db, event)
    if blockers := _blockers(event, live):
        raise AppError(
            "cannot_complete",
            "The event can't be marked as done yet.",
            409,
            extra={"blockers": blockers},
        )
    if event.status != "CHECKIN_CLOSED":
        raise AppError("cannot_complete", "The event can't be marked as done yet.", 409)

    submission = AwardSubmission(
        submission_id=uuid.uuid4(), kind="EVENT", event_id=event_id, submitted_by=actor.user.user_id
    )
    db.add(submission)
    db.flush()
    earned = event_date(event)
    awarded: list[str] = []
    skipped: list[str] = []
    for student_id in sorted({p.student_id for p in live if p.student_id}):
        award_id = db.scalar(
            insert(SkillAward)
            .values(
                student_id=student_id,
                skill_id=event.skill_id,
                date_earned=earned,
                submission_id=submission.submission_id,
            )
            .on_conflict_do_nothing(index_elements=["student_id", "skill_id"])
            .returning(SkillAward.award_id)
        )
        (awarded if award_id is not None else skipped).append(student_id)
    created = issuance.create_versions(db, awarded)
    out = CompleteOut(
        submission_id=submission.submission_id,
        awarded=[AwardedStudent(student_id=v.student_id, version_no=v.version_no) for v in created],
        skipped=skipped,
    )
    submission.response_json = out.model_dump(mode="json")
    event.status = "COMPLETED"
    event.completed_by = actor.user.user_id
    event.completed_at = _now()
    db.flush()
    audit.record(
        db, actor, "event.complete", "event", str(event_id), after=out.model_dump(mode="json")
    )
    db.flush()
    return out


def link_participants(db: Session, student_id: str, email: str) -> int:
    """A newly registered student (or a changed email) claims their Unregistered check-ins."""
    result = db.execute(
        sql_update(EventParticipant)
        .where(EventParticipant.email == email, EventParticipant.student_id.is_(None))
        .values(student_id=student_id)
    )
    return int(getattr(result, "rowcount", 0) or 0)


def participant_count(db: Session, event_id: uuid.UUID) -> int:
    stmt = select(func.count()).where(
        EventParticipant.event_id == event_id, EventParticipant.removed_at.is_(None)
    )
    return db.scalar(stmt) or 0
