"""BE-42: check-in by QR (FR-28 - FR-30, A13)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Event, EventParticipant, Skill, Student
from app.services import qr_tokens
from tests import factories

ClientAs = Callable[[str | None], TestClient]
NOW = datetime(2026, 10, 21, 11, 45, 0, tzinfo=UTC)  # a window boundary


@pytest.fixture
def event(db: Session) -> Event:
    skill = factories.skill(db, "SKL-001")
    e = factories.event(db, skill, factories.user(db, "organiser@btu.test"), status="CHECKIN_OPEN")
    db.commit()
    return e


def _t(event: Event, at: datetime = NOW) -> str:
    return qr_tokens.token(event.qr_secret, event.event_id, qr_tokens.window(at))


def _rows(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(EventParticipant)) or 0


def _url(event: Event) -> str:
    return f"/api/checkin/{event.event_id}"


def test_confirm_then_check_in(db: Session, client_as: ClientAs, event: Event) -> None:
    client = client_as("student")  # BTU-T-0001
    with time_machine.travel(NOW, tick=False):
        view = client.get(_url(event), params={"t": _t(event)}).json()
        assert view["state"] == "CONFIRM" and view["event"]["skill"]["name"] == "Skill SKL-001"
        assert _rows(db) == 0  # GET never writes
        r = client.post(_url(event), json={"t": _t(event)})
    assert r.status_code == 200, r.text
    assert r.json() == {"state": "CHECKED_IN", "unregistered": False, "already_holds_skill": False}
    row = db.scalars(select(EventParticipant)).one()
    assert (row.email, row.student_id, row.method) == ("btu-t-0001@example.org", "BTU-T-0001", "QR")


def test_checking_in_twice_changes_nothing(db: Session, client_as: ClientAs, event: Event) -> None:
    client = client_as("student")
    with time_machine.travel(NOW, tick=False):
        first = client.post(_url(event), json={"t": _t(event)})
    # Later, with an old token: still "checked in", no second row (FR-29).
    with time_machine.travel(NOW + timedelta(minutes=10), tick=False):
        again = client.post(_url(event), json={"t": _t(event)})
        view = client.get(_url(event), params={"t": "whatever"}).json()
    assert (first.json(), again.status_code) == (again.json(), 200)
    assert view["state"] == "CHECKED_IN" and _rows(db) == 1


@pytest.mark.parametrize("later", [timedelta(seconds=0), timedelta(seconds=59)])
def test_token_lives_30_to_60_seconds(client_as: ClientAs, event: Event, later: timedelta) -> None:
    with time_machine.travel(NOW + later, tick=False):
        r = client_as("student").post(_url(event), json={"t": _t(event)})
    assert r.status_code == 200


@pytest.mark.parametrize("later", [timedelta(seconds=60), timedelta(minutes=2)])
def test_A13_expired_token(
    db: Session, client_as: ClientAs, event: Event, later: timedelta
) -> None:
    """A photo of the QR shared a minute later doesn't work."""
    client = client_as("student")
    with time_machine.travel(NOW + later, tick=False):
        view = client.get(_url(event), params={"t": _t(event)}).json()
        r = client.post(_url(event), json={"t": _t(event)})
    assert view["state"] == "TOKEN_EXPIRED"
    assert (r.status_code, r.json()["error"], r.json()["state"]) == (
        409,
        "token_expired",
        "TOKEN_EXPIRED",
    )
    assert _rows(db) == 0


def test_unregistered_is_recorded(db: Session, client_as: ClientAs, event: Event) -> None:
    with time_machine.travel(NOW, tick=False):
        r = client_as("unregistered").post(_url(event), json={"t": _t(event)})
    assert r.json() == {"state": "CHECKED_IN", "unregistered": True, "already_holds_skill": False}
    row = db.scalars(select(EventParticipant)).one()
    assert (row.email, row.student_id, row.display_name) == ("newcomer@btu.test", None, "newcomer")


def test_already_holds_skill(db: Session, client_as: ClientAs, event: Event) -> None:
    client = client_as("student")
    skill = db.get(Skill, "SKL-001")
    student = db.get(Student, "BTU-T-0001")
    assert skill is not None and student is not None
    factories.award(db, student, skill)
    db.commit()
    with time_machine.travel(NOW, tick=False):
        assert client.get(_url(event), params={"t": _t(event)}).json()["already_holds_skill"]
        r = client.post(_url(event), json={"t": _t(event)})
    assert r.json()["already_holds_skill"] is True


@pytest.mark.parametrize(
    ("status", "state"),
    [("DRAFT", "NOT_OPEN"), ("CHECKIN_CLOSED", "CLOSED"), ("COMPLETED", "CLOSED")],
)
def test_not_open_or_closed(
    db: Session, client_as: ClientAs, event: Event, status: str, state: str
) -> None:
    event.status = status
    db.commit()
    client = client_as("student")
    with time_machine.travel(NOW, tick=False):
        assert client.get(_url(event), params={"t": _t(event)}).json()["state"] == state
        r = client.post(_url(event), json={"t": _t(event)})
    assert (r.status_code, r.json()["state"]) == (409, state) and _rows(db) == 0


def test_removed(db: Session, client_as: ClientAs, event: Event) -> None:
    client = client_as("student")
    with time_machine.travel(NOW, tick=False):
        client.post(_url(event), json={"t": _t(event)})
    row = db.scalars(select(EventParticipant)).one()
    row.removed_at = NOW
    db.commit()
    with time_machine.travel(NOW + timedelta(seconds=5), tick=False):
        assert client.get(_url(event), params={"t": _t(event)}).json()["state"] == "REMOVED"
        r = client.post(_url(event), json={"t": _t(event)})
    assert r.json()["state"] == "REMOVED"
    db.refresh(row)
    assert row.removed_at is not None  # a scan doesn't undo the organiser's removal


def test_not_found(db: Session, client_as: ClientAs, event: Event) -> None:
    client = client_as("student")
    for eid in (str(uuid.uuid4()), "not-a-uuid"):
        assert client.get(f"/api/checkin/{eid}", params={"t": "x"}).json() == {
            "event": None,
            "state": "NOT_FOUND",
            "unregistered": False,
            "already_holds_skill": False,
        }
    event.deleted_at = NOW
    db.commit()
    with time_machine.travel(NOW, tick=False):
        r = client.post(_url(event), json={"t": _t(event)})
    assert (r.status_code, r.json()["state"]) == (404, "NOT_FOUND")


def test_sign_in_required(client_as: ClientAs, event: Event) -> None:
    r = client_as(None).get(_url(event), params={"t": "x"})
    assert (r.status_code, r.json()["error"]) == (401, "unauthenticated")
