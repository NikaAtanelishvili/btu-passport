"""BE-40: event service — lifecycle, tick, delete, complete (FR-26, FR-27, FR-30 - FR-32)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth import sessions
from app.auth.deps import Principal
from app.errors import AppError
from app.models import (
    AuditLog,
    AwardSubmission,
    Event,
    EventParticipant,
    PassportVersion,
    Skill,
    SkillAward,
    Student,
    UserRole,
)
from app.schemas.event import EventCreate, EventPatch
from app.schemas.student import StudentCreate
from app.services import events, students
from tests import factories

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
START = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)


@pytest.fixture
def boss(db: Session) -> Principal:
    user = factories.user(db, "superadmin@btu.test")
    db.add(UserRole(email=user.email, role="SUPER_ADMIN"))
    _, row = sessions.create_session(db, user)
    db.flush()
    return Principal(user=user, role="SUPER_ADMIN", student=None, session=row)


def _body(**over: Any) -> EventCreate:
    values: dict[str, Any] = {
        "name": "AI Data Analysis Workshop",
        "skill_id": "SKL-001",
        "starts_at": START,
        "ends_at": START + timedelta(hours=2),
        "location": "Room 301",
    }
    return EventCreate(**{**values, **over})


def _event(db: Session, boss: Principal, **over: Any) -> Event:
    if db.get(Skill, "SKL-001") is None:
        factories.skill(db, "SKL-001")
    return events.create(db, boss, _body(**over))


def _checkin(db: Session, event: Event, n: int, *, registered: bool = True) -> EventParticipant:
    email = f"btu-t-{n:04d}@example.org"
    if registered and db.scalar(select(func.count()).where(Student.email == email)) == 0:
        factories.student(db, n)
    p = factories.participant(db, event, email)
    p.student_id = f"BTU-T-{n:04d}" if registered else None
    db.flush()
    return p


def _closed(db: Session, boss: Principal, participants: int = 0) -> Event:
    event = _event(db, boss)
    events.open_checkin(db, boss, event.event_id, NOW)
    for n in range(1, participants + 1):
        _checkin(db, event, n)
    events.close_checkin(db, boss, event.event_id, NOW + timedelta(minutes=5))
    return event


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


# --- create / update -------------------------------------------------------------------


def test_create_fills_window_defaults_and_audits(db: Session, boss: Principal) -> None:
    event = _event(db, boss)
    assert event.status == "DRAFT" and len(event.qr_secret) == 32
    assert event.checkin_opens_at == START + timedelta(hours=2) - timedelta(minutes=15)
    assert event.checkin_closes_at == START + timedelta(hours=2) + timedelta(minutes=30)
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "event.create")).one()
    assert (audit.entity_id, audit.actor_email) == (str(event.event_id), "superadmin@btu.test")


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "x" * 121}, "name"),
        ({"description": "x" * 501}, "description"),
        ({"skill_id": "SKL-999"}, "skill_id"),
        ({"ends_at": START}, "ends_at"),
        (
            {"checkin_opens_at": START, "checkin_closes_at": START - timedelta(minutes=1)},
            "checkin_closes_at",
        ),
    ],
)
def test_invalid_event_is_422(
    db: Session, boss: Principal, over: dict[str, Any], field: str
) -> None:
    factories.skill(db, "SKL-001")
    with pytest.raises(AppError) as err:
        events.create(db, boss, _body(**over))
    assert err.value.status == 422 and field in err.value.fields
    assert _count(db, Event) == 0


def test_archived_skill_is_rejected(db: Session, boss: Principal) -> None:
    factories.skill(db, "SKL-001").archived_at = NOW
    with pytest.raises(AppError) as err:
        events.create(db, boss, _body())
    assert "skill_id" in err.value.fields


def test_FR26_skill_locked_after_first_checkin(db: Session, boss: Principal) -> None:
    event = _event(db, boss)
    factories.skill(db, "SKL-002")
    events.update(db, boss, event.event_id, EventPatch(skill_id="SKL-002"))  # no one yet
    _checkin(db, event, 1)
    with pytest.raises(AppError) as err:
        events.update(db, boss, event.event_id, EventPatch(skill_id="SKL-001"))
    assert (err.value.status, err.value.code) == (409, "skill_locked")
    events.update(db, boss, event.event_id, EventPatch(name="Renamed"))  # other fields still fine
    assert event.name == "Renamed" and event.skill_id == "SKL-002"


def test_update_rechecks_the_merged_times(db: Session, boss: Principal) -> None:
    event = _event(db, boss)
    with pytest.raises(AppError) as err:
        events.update(db, boss, event.event_id, EventPatch(ends_at=START - timedelta(hours=1)))
    assert "ends_at" in err.value.fields


# --- open / close / reopen / tick ------------------------------------------------------


def test_open_close_reopen(db: Session, boss: Principal) -> None:
    event = _event(db, boss)
    events.open_checkin(db, boss, event.event_id, NOW)
    assert event.status == "CHECKIN_OPEN" and event.checkin_opens_at == NOW
    with pytest.raises(AppError) as err:
        events.open_checkin(db, boss, event.event_id, NOW)
    assert (err.value.status, err.value.code) == (409, "invalid_transition")
    events.close_checkin(db, boss, event.event_id, NOW + timedelta(minutes=10))
    assert event.status == "CHECKIN_CLOSED"
    assert event.checkin_closes_at == NOW + timedelta(minutes=10)
    later = NOW + timedelta(hours=1)
    events.reopen_checkin(db, boss, event.event_id, later)
    assert event.status == "CHECKIN_OPEN" and event.checkin_closes_at == later + timedelta(
        minutes=30
    )
    actions = [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert actions == ["event.create", "event.open", "event.close", "event.reopen"]


def test_open_after_the_window_extends_it(db: Session, boss: Principal) -> None:
    event = _event(db, boss)
    late = event.checkin_closes_at + timedelta(minutes=5)
    events.open_checkin(db, boss, event.event_id, late)
    assert event.checkin_opens_at < late and event.checkin_closes_at == late + timedelta(minutes=30)


def test_tick_opens_and_closes_by_the_window(db: Session, boss: Principal) -> None:
    event = _event(db, boss)
    deleted = _event(db, boss, name="Deleted")
    events.delete(db, boss, deleted.event_id)
    assert events.tick(db, event.checkin_opens_at - timedelta(seconds=1)) == 0
    assert events.tick(db, event.checkin_opens_at) == 1
    assert event.status == "CHECKIN_OPEN" and deleted.status == "DRAFT"
    assert events.tick(db, event.checkin_closes_at) == 1
    assert event.status == "CHECKIN_CLOSED"
    rows = db.scalars(select(AuditLog).where(AuditLog.action.in_(["event.open", "event.close"])))
    assert all(r.actor_email is None for r in rows)  # the system


# --- delete (FR-27, A16) ---------------------------------------------------------------


def test_delete_is_soft(db: Session, boss: Principal) -> None:
    event = _event(db, boss)
    _checkin(db, event, 1)
    events.delete(db, boss, event.event_id)
    db.expire_all()
    assert db.get(Event, event.event_id).deleted_at is not None  # type: ignore[union-attr]
    assert _count(db, EventParticipant) == 1  # check-ins kept for "Event deleted"
    with pytest.raises(AppError) as err:
        events.get_live(db, event.event_id)
    assert err.value.status == 404


def test_A16_no_delete_or_edit_when_completed(db: Session, boss: Principal) -> None:
    event = _closed(db, boss, participants=1)
    events.complete(db, boss, event.event_id)
    for action in (
        lambda: events.delete(db, boss, event.event_id),
        lambda: events.update(db, boss, event.event_id, EventPatch(name="x")),
        lambda: events.reopen_checkin(db, boss, event.event_id, NOW),
    ):
        with pytest.raises(AppError) as err:
            action()
        assert (err.value.status, err.value.code) == (409, "event_completed")
    db.commit()
    for sql in (
        "UPDATE events SET deleted_at = now()",
        "UPDATE events SET name = 'x'",
        "DELETE FROM events",
    ):
        with pytest.raises(DBAPIError, match="read-only"):
            db.execute(text(sql))
        db.rollback()


# --- complete (FR-30 - FR-32, A14, A15) ------------------------------------------------


def test_A14_unregistered_blocks_until_registered(db: Session, boss: Principal) -> None:
    event = _closed(db, boss, participants=1)
    _checkin(db, event, 50, registered=False)  # btu-t-0050@example.org has no student row
    detail = events.detail(db, event.event_id)
    assert detail.complete_blockers == ["UNREGISTERED_PRESENT"] and not detail.can_complete
    assert detail.counts.unregistered == 1
    with pytest.raises(AppError) as err:
        events.complete(db, boss, event.event_id)
    assert (err.value.status, err.value.code) == (409, "cannot_complete")
    assert err.value.extra == {"blockers": ["UNREGISTERED_PRESENT"]}
    assert _count(db, AwardSubmission) == 0

    # Registering the student links the check-in (BE-40 "Linking Unregistered check-ins").
    db.execute(text("SELECT setval('passport_number_seq', 1000)"))  # past the factory IDs
    students.create_student(
        db,
        boss,
        StudentCreate(
            student_id="BTU-T-0050",
            first_name="Ana",
            last_name="New",
            email="btu-t-0050@example.org",
            program="Information Technologies",
            education_level="BACHELOR",
            status="ACTIVE",
        ),
    )
    detail = events.detail(db, event.event_id)
    assert detail.complete_blockers == [] and detail.can_complete
    out = events.complete(db, boss, event.event_id)
    assert sorted(a.student_id for a in out.awarded) == ["BTU-T-0001", "BTU-T-0050"]


def test_A14_unregistered_blocks_until_removed(db: Session, boss: Principal) -> None:
    event = _closed(db, boss, participants=1)
    unregistered = _checkin(db, event, 50, registered=False)
    unregistered.removed_at = NOW
    db.flush()
    assert events.detail(db, event.event_id).can_complete
    out = events.complete(db, boss, event.event_id)
    assert [a.student_id for a in out.awarded] == ["BTU-T-0001"]


def test_A15_complete_one_submission_skips_holders_and_is_idempotent(
    db: Session, boss: Principal
) -> None:
    event = _closed(db, boss, participants=20)
    skill = db.get(Skill, "SKL-001")
    for n in (3, 7):  # two already hold the skill
        factories.award(db, db.get(Student, f"BTU-T-{n:04d}"), skill)  # type: ignore[arg-type]
    removed = _checkin(db, event, 21)
    removed.removed_at = NOW
    db.flush()
    assert events.detail(db, event.event_id).counts.already_held == 2

    out = events.complete(db, boss, event.event_id)
    db.commit()
    assert len(out.awarded) == 18 and sorted(out.skipped) == ["BTU-T-0003", "BTU-T-0007"]
    assert "BTU-T-0021" not in [a.student_id for a in out.awarded]  # removed: no award
    assert all(a.version_no == 1 for a in out.awarded)
    submissions = db.scalars(select(AwardSubmission).where(AwardSubmission.kind == "EVENT")).all()
    assert len(submissions) == 1 and submissions[0].event_id == event.event_id
    event_awards = select(func.count()).where(
        SkillAward.submission_id == submissions[0].submission_id
    )
    assert db.scalar(event_awards) == 18
    assert (
        db.scalar(
            select(func.count())
            .select_from(SkillAward)
            .where(SkillAward.date_earned == date(2026, 10, 21))
        )
        == 18
    )
    db.refresh(event)
    assert event.status == "COMPLETED" and event.completed_by == boss.user.user_id
    counts = [_count(db, m) for m in (AwardSubmission, SkillAward, PassportVersion)]

    again = events.complete(db, boss, event.event_id)  # a double click or a retried request
    assert again == out
    assert [_count(db, m) for m in (AwardSubmission, SkillAward, PassportVersion)] == counts
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "event.complete")).all()
    assert len(audit) == 1 and audit[0].actor_email == "superadmin@btu.test"
    assert events.detail(db, event.event_id).completion == out


def test_award_date_is_the_events_local_date(db: Session, boss: Principal) -> None:
    # 22:30 UTC on 21 Oct is 02:30 on 22 Oct in Tbilisi (UTC+4).
    late = datetime(2026, 10, 21, 22, 30, tzinfo=UTC)
    event = _event(db, boss, starts_at=late, ends_at=late + timedelta(hours=1))
    events.open_checkin(db, boss, event.event_id, NOW)
    _checkin(db, event, 1)
    events.close_checkin(db, boss, event.event_id, NOW + timedelta(minutes=1))
    events.complete(db, boss, event.event_id)
    award = db.scalars(select(SkillAward)).one()
    assert award.date_earned == date(2026, 10, 22)


@pytest.mark.parametrize(
    ("setup", "blockers"),
    [
        ("draft", ["DRAFT", "NO_PARTICIPANTS"]),
        ("open", ["CHECKIN_OPEN"]),
        ("closed_empty", ["NO_PARTICIPANTS"]),
    ],
)
def test_blockers(db: Session, boss: Principal, setup: str, blockers: list[str]) -> None:
    event = _event(db, boss)
    if setup != "draft":
        events.open_checkin(db, boss, event.event_id, NOW)
    if setup == "open":
        _checkin(db, event, 1)
    if setup == "closed_empty":
        events.close_checkin(db, boss, event.event_id, NOW)
    assert events.detail(db, event.event_id).complete_blockers == blockers
    with pytest.raises(AppError) as err:
        events.complete(db, boss, event.event_id)
    assert err.value.code == "cannot_complete"


def test_unknown_event_is_404(db: Session, boss: Principal) -> None:
    with pytest.raises(AppError) as err:
        events.detail(db, uuid.uuid4())
    assert err.value.status == 404
