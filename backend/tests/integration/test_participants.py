"""BE-43: manual add and remove, flags."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import Principal
from app.errors import AppError
from app.models import AuditLog, Event, EventParticipant, Skill
from app.schemas.event import EventCreate
from app.services import events
from tests import factories

START = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)


@pytest.fixture
def event(db: Session, boss: Principal) -> Event:
    factories.skill(db, "SKL-001")
    return events.create(
        db,
        boss,
        EventCreate(
            name="Workshop", skill_id="SKL-001", starts_at=START, ends_at=START + timedelta(hours=2)
        ),
    )


def test_manual_add_uses_the_students_email(db: Session, boss: Principal, event: Event) -> None:
    factories.student(db, 2)
    p = events.add_participant(db, boss, event.event_id, "BTU-T-0002")
    assert (p.email, p.student_id, p.method, p.flags) == (
        "btu-t-0002@example.org",
        "BTU-T-0002",
        "MANUAL",
        [],
    )
    row = db.scalars(select(EventParticipant)).one()
    assert row.added_by == boss.user.user_id and row.display_name == "Nino Test"
    with pytest.raises(AppError) as err:
        events.add_participant(db, boss, event.event_id, "BTU-T-0002")
    assert (err.value.status, err.value.code) == (409, "already_checked_in")
    with pytest.raises(AppError) as err:
        events.add_participant(db, boss, event.event_id, "BTU-T-9999")
    assert err.value.status == 422 and "student_id" in err.value.fields


def test_remove_then_add_again_restores_the_row(db: Session, boss: Principal, event: Event) -> None:
    factories.student(db, 2)
    events.add_participant(db, boss, event.event_id, "BTU-T-0002")
    events.remove_participant(db, boss, event.event_id, "BTU-T-0002@example.org")
    row = db.scalars(select(EventParticipant)).one()
    assert row.removed_at is not None and row.removed_by == boss.user.user_id
    assert events.participants(db, event) == []
    assert len(events.participants(db, event, include_removed=True)) == 1
    events.add_participant(db, boss, event.event_id, "BTU-T-0002")
    db.refresh(row)
    assert row.removed_at is None and row.removed_by is None
    actions = [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert actions == ["event.create", "participant.add", "participant.remove", "participant.add"]
    with pytest.raises(AppError) as err:
        events.remove_participant(db, boss, event.event_id, "nobody@btu.test")
    assert err.value.status == 404


def test_flags(db: Session, boss: Principal, event: Event) -> None:
    holder = factories.student(db, 3)
    skill = db.get(Skill, "SKL-001")
    assert skill is not None
    factories.award(db, holder, skill)
    events.add_participant(db, boss, event.event_id, "BTU-T-0003")
    factories.participant(db, event, "newcomer@btu.test")
    flags = {p.email: p.flags for p in events.participants(db, event)}
    assert flags == {
        "btu-t-0003@example.org": ["ALREADY_HOLDS"],
        "newcomer@btu.test": ["UNREGISTERED"],
    }


def test_no_changes_once_completed(db: Session, boss: Principal, event: Event) -> None:
    factories.student(db, 2)
    events.add_participant(db, boss, event.event_id, "BTU-T-0002")
    events.open_checkin(db, boss, event.event_id, START)
    events.close_checkin(db, boss, event.event_id, START + timedelta(minutes=1))
    events.complete(db, boss, event.event_id)
    factories.student(db, 4)
    for action in (
        lambda: events.add_participant(db, boss, event.event_id, "BTU-T-0004"),
        lambda: events.remove_participant(db, boss, event.event_id, "btu-t-0002@example.org"),
    ):
        with pytest.raises(AppError) as err:
            action()
        assert err.value.code == "event_completed"
