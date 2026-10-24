"""BE-46: GET /api/me/events — the student's check-ins and what became of them (FR-33)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.deps import Principal
from app.models import Event, Skill, Student
from app.schemas.event import EventCreate
from app.services import events
from tests import factories

ClientAs = Callable[[str | None], TestClient]
START = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)


def _event(db: Session, boss: Principal, name: str, skill_id: str = "SKL-001") -> Event:
    if db.get(Skill, skill_id) is None:
        factories.skill(db, skill_id)
    event = events.create(
        db,
        boss,
        EventCreate(
            name=name, skill_id=skill_id, starts_at=START, ends_at=START + timedelta(hours=1)
        ),
    )
    events.open_checkin(db, boss, event.event_id, START)
    return event


def test_statuses(db: Session, boss: Principal, client_as: ClientAs) -> None:
    client = client_as("student")  # BTU-T-0001, btu-t-0001@example.org
    me = "BTU-T-0001"
    waiting = _event(db, boss, "Waiting")
    awarded = _event(db, boss, "Awarded")
    held = _event(db, boss, "Held", "SKL-002")
    removed = _event(db, boss, "Removed")
    deleted = _event(db, boss, "Deleted")
    _event(db, boss, "Someone else's")
    student = db.get(Student, me)
    skill2 = db.get(Skill, "SKL-002")
    assert student is not None and skill2 is not None
    factories.award(db, student, skill2)  # already holds SKL-002
    for e in (waiting, awarded, held, removed, deleted):
        events.add_participant(db, boss, e.event_id, me)
    events.remove_participant(db, boss, removed.event_id, "btu-t-0001@example.org")
    events.delete(db, boss, deleted.event_id)
    for e in (awarded, held):
        events.close_checkin(db, boss, e.event_id, START + timedelta(minutes=5))
        events.complete(db, boss, e.event_id)
    db.commit()

    rows = {r["name"]: r for r in client.get("/api/me/events").json()}
    assert {name: r["status"] for name, r in rows.items()} == {
        "Waiting": "WAITING",
        "Awarded": "AWARDED",
        "Held": "ALREADY_HELD",
        "Removed": "NOT_CONFIRMED",
        "Deleted": "EVENT_DELETED",
    }
    # The version that first contained the award: the seed-less student's V1 from "Awarded"
    # (the "Held" completion skipped them, so no version from it).
    assert rows["Awarded"]["version_no"] == 1
    assert rows["Waiting"]["version_no"] is None
    assert rows["Awarded"]["skill_name"] == "Skill SKL-001"
    assert rows["Awarded"]["event_date"] == "2026-10-21"


def test_students_only(client_as: ClientAs) -> None:
    assert client_as("admin").get("/api/me/events").status_code == 403
    assert client_as(None).get("/api/me/events").status_code == 401
    assert client_as("student").get("/api/me/events").json() == []
