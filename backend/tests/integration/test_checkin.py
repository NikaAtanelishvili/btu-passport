"""BE-42: check-in by QR (FR-28 - FR-30, A13)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

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
        times = {
            k: datetime.fromisoformat(view["event"][k]) for k in ("ends_at", "checkin_closes_at")
        }
        assert times == {"ends_at": event.ends_at, "checkin_closes_at": event.checkin_closes_at}
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
            "from_pass": False,
        }
    event.deleted_at = NOW
    db.commit()
    with time_machine.travel(NOW, tick=False):
        r = client.post(_url(event), json={"t": _t(event)})
    assert (r.status_code, r.json()["state"]) == (404, "NOT_FOUND")


def test_sign_in_required(client_as: ClientAs, event: Event) -> None:
    r = client_as(None).get(_url(event), params={"t": "x"})
    assert (r.status_code, r.json()["error"]) == (401, "unauthenticated")


# Check-in pass: a signed-out scan validates the QR token there and then and gets a pass that
# carries the check-in through sign-in (a token lives only 30-60 s; sign-in takes minutes). The
# pass is an HttpOnly cookie scoped to this event's check-in API, never part of a URL.

PASS_COOKIE = "checkin_pass"


def _scan(client: TestClient, event: Event, t: str) -> Any:
    return client.post(f"{_url(event)}/pass", json={"t": t})


def _pass_value(client: TestClient, event: Event) -> str | None:
    value: str | None = client.cookies.get(PASS_COOKIE, path=_url(event))
    return value


def _sign_in(browser: TestClient, signed_in: TestClient) -> TestClient:
    """The same browser after sign-in: keeps its cookies (the pass) and gains a session."""
    for name, value in signed_in.cookies.items():
        browser.cookies.set(name, value)
    browser.headers["X-CSRF-Token"] = signed_in.headers["X-CSRF-Token"]
    return browser


def _browser_with_pass(client_as: ClientAs, event: Event, at: datetime = NOW) -> TestClient:
    browser = client_as(None)
    with time_machine.travel(at, tick=False):
        assert _scan(browser, event, _t(event, at)).status_code == 200
    return browser


def test_scan_sets_a_scoped_httponly_cookie(client_as: ClientAs, event: Event) -> None:
    browser = client_as(None)
    with time_machine.travel(NOW, tick=False):
        r = _scan(browser, event, _t(event))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "expires_at": (NOW + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    }  # the pass itself is not in the body
    cookie = r.headers["set-cookie"].lower()
    assert cookie.startswith(f"{PASS_COOKIE}=")
    for part in ("httponly", "samesite=lax", f"path={_url(event)}", "max-age=600"):
        assert part in cookie, (part, cookie)
    assert _pass_value(browser, event)


def test_same_browser_completes_after_sign_in(
    db: Session, client_as: ClientAs, event: Event
) -> None:
    browser = _browser_with_pass(client_as, event)
    browser = _sign_in(browser, client_as("student"))
    with time_machine.travel(NOW + timedelta(minutes=3), tick=False):
        view = browser.get(_url(event)).json()  # no token in the URL any more
        assert (view["state"], view["from_pass"]) == ("CONFIRM", True)
        done = browser.post(_url(event), json={})
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "CHECKED_IN"
    assert _pass_value(browser, event) is None  # cleared once used
    row = db.scalars(select(EventParticipant)).one()
    assert (row.email, row.method) == ("btu-t-0001@example.org", "QR")


def test_other_browser_with_the_same_url_must_scan_again(
    db: Session, client_as: ClientAs, event: Event
) -> None:
    _browser_with_pass(client_as, event)
    other = client_as("student")  # same /checkin/<id> link, no cookie
    with time_machine.travel(NOW + timedelta(minutes=1), tick=False):
        view = other.get(_url(event)).json()
        r = other.post(_url(event), json={})
    assert (view["state"], view["from_pass"]) == ("TOKEN_EXPIRED", False)
    assert (r.status_code, r.json()["state"]) == (409, "TOKEN_EXPIRED") and _rows(db) == 0


def test_a_token_still_works_without_a_pass(client_as: ClientAs, event: Event) -> None:
    with time_machine.travel(NOW, tick=False):
        view = client_as("student").get(_url(event), params={"t": _t(event)}).json()
    assert (view["state"], view["from_pass"]) == ("CONFIRM", False)


def test_expired_token_at_scan_gets_no_pass(client_as: ClientAs, event: Event) -> None:
    browser = client_as(None)
    with time_machine.travel(NOW + timedelta(seconds=60), tick=False):
        r = _scan(browser, event, _t(event))
    assert (r.status_code, r.json()["error"], r.json()["state"]) == (
        409,
        "token_expired",
        "TOKEN_EXPIRED",
    )
    assert "set-cookie" not in r.headers and _pass_value(browser, event) is None


@pytest.mark.parametrize(
    ("status", "state"),
    [("DRAFT", "NOT_OPEN"), ("CHECKIN_CLOSED", "CLOSED"), ("COMPLETED", "CLOSED")],
)
def test_no_pass_unless_check_in_is_open(
    db: Session, client_as: ClientAs, event: Event, status: str, state: str
) -> None:
    event.status = status
    db.commit()
    with time_machine.travel(NOW, tick=False):
        r = _scan(client_as(None), event, _t(event))
    assert (r.status_code, r.json()["state"]) == (409, state) and "set-cookie" not in r.headers


def test_pass_for_a_missing_event(client_as: ClientAs) -> None:
    for eid in (str(uuid.uuid4()), "not-a-uuid"):
        r = client_as(None).post(f"/api/checkin/{eid}/pass", json={"t": "x"})
        assert (r.status_code, r.json()["state"]) == (404, "NOT_FOUND")


def test_pass_is_single_use(db: Session, client_as: ClientAs, event: Event) -> None:
    browser = _browser_with_pass(client_as, event)
    stolen = _pass_value(browser, event)
    assert stolen is not None
    browser = _sign_in(browser, client_as("student"))
    second = client_as("unregistered")
    second.cookies.set(PASS_COOKIE, stolen, path=_url(event))  # copied out of the first browser
    with time_machine.travel(NOW + timedelta(minutes=2), tick=False):
        assert browser.post(_url(event), json={}).status_code == 200
        assert second.get(_url(event)).json()["state"] == "TOKEN_EXPIRED"
        r = second.post(_url(event), json={})
    assert (r.status_code, r.json()["state"]) == (409, "TOKEN_EXPIRED")
    assert _rows(db) == 1


def test_pass_expires_after_10_minutes(db: Session, client_as: ClientAs, event: Event) -> None:
    browser = _sign_in(_browser_with_pass(client_as, event), client_as("student"))
    with time_machine.travel(NOW + timedelta(minutes=10, seconds=1), tick=False):
        assert browser.get(_url(event)).json()["state"] == "TOKEN_EXPIRED"
        r = browser.post(_url(event), json={})
    assert (r.status_code, r.json()["state"]) == (409, "TOKEN_EXPIRED") and _rows(db) == 0


def test_pass_for_another_event(db: Session, client_as: ClientAs, event: Event) -> None:
    skill = db.get(Skill, event.skill_id)
    assert skill is not None
    other = factories.event(db, skill, factories.user(db, "other@btu.test"), status="CHECKIN_OPEN")
    db.commit()
    browser = _browser_with_pass(client_as, other)
    value = _pass_value(browser, other)
    assert value is not None and _pass_value(browser, event) is None  # scoped to its event
    student = client_as("student")
    student.cookies.set(PASS_COOKIE, value, path=_url(event))  # moved by hand
    with time_machine.travel(NOW + timedelta(minutes=1), tick=False):
        r = student.post(_url(event), json={})
    assert (r.status_code, r.json()["state"]) == (409, "TOKEN_EXPIRED") and _rows(db) == 0


def test_pass_does_not_outlive_check_in(db: Session, client_as: ClientAs, event: Event) -> None:
    browser = _sign_in(_browser_with_pass(client_as, event), client_as("student"))
    event.status = "CHECKIN_CLOSED"
    db.commit()
    with time_machine.travel(NOW + timedelta(minutes=1), tick=False):
        r = browser.post(_url(event), json={})
    assert (r.status_code, r.json()["state"]) == (409, "CLOSED")


def test_a_pass_in_the_url_is_ignored(client_as: ClientAs, event: Event) -> None:
    """The old ?p= form: a forwarded link must carry nothing that checks anyone in."""
    from app.services import qr_tokens as q

    with time_machine.travel(NOW, tick=False):
        p = q.issue_pass(event.qr_secret, event.event_id, NOW)
    student = client_as("student")
    with time_machine.travel(NOW + timedelta(minutes=1), tick=False):
        assert student.get(_url(event), params={"p": p}).json()["state"] == "TOKEN_EXPIRED"
        r = student.post(_url(event), json={"p": p})
    assert r.json()["state"] == "TOKEN_EXPIRED"


def test_db_refuses_a_pass_used_twice(db: Session, event: Event) -> None:
    """Backstop for two people racing with one pass: UNIQUE (event_id, pass_nonce)."""
    from sqlalchemy.exc import IntegrityError

    a = factories.participant(db, event, "a@btu.test")
    a.pass_nonce = "n1"
    db.flush()
    b = factories.participant(db, event, "b@btu.test")
    b.pass_nonce = "n1"
    with pytest.raises(IntegrityError):
        db.flush()
