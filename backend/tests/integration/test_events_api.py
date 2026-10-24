"""BE-44: /api/admin/events routes. Reads for both admin roles; writes for super admins."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests import factories

ClientAs = Callable[[str | None], TestClient]
START = datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)


def _new(**over: Any) -> dict[str, Any]:
    body = {
        "name": "AI Data Analysis Workshop",
        "skill_id": "SKL-001",
        "starts_at": START.isoformat(),
        "ends_at": (START + timedelta(hours=2)).isoformat(),
        "location": "Room 301",
    }
    return {**body, **over}


@pytest.fixture
def boss_client(db: Session, client_as: ClientAs) -> TestClient:
    factories.skill(db, "SKL-001")
    db.commit()
    return client_as("super_admin")


def _create(client: TestClient, **over: Any) -> dict[str, Any]:
    r = client.post("/api/admin/events", json=_new(**over))
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def test_create_and_read(boss_client: TestClient) -> None:
    event = _create(boss_client)
    assert event["status"] == "DRAFT" and event["skill"]["skill_id"] == "SKL-001"
    assert event["complete_blockers"] == ["DRAFT", "NO_PARTICIPANTS"]
    eid = event["event_id"]
    assert boss_client.get(f"/api/admin/events/{eid}").json()["name"] == event["name"]
    page = boss_client.get("/api/admin/events", params={"status": "DRAFT"}).json()
    assert [e["event_id"] for e in page["items"]] == [eid]
    assert page["items"][0]["participant_count"] == 0
    assert boss_client.get("/api/admin/events", params={"status": "COMPLETED"}).json()["total"] == 0


def test_create_errors_under_the_fields(boss_client: TestClient) -> None:
    r = boss_client.post("/api/admin/events", json=_new(name="", ends_at=START.isoformat()))
    assert r.status_code == 422 and {"name", "ends_at"} <= set(r.json()["fields"])
    r = boss_client.post("/api/admin/events", json=_new(starts_at="2026-10-21T10:00:00"))
    assert r.status_code == 422 and "starts_at" in r.json()["fields"]  # needs a timezone


def test_lifecycle_complete_and_A16_over_the_api(db: Session, boss_client: TestClient) -> None:
    eid = _create(boss_client)["event_id"]
    assert boss_client.post(f"/api/admin/events/{eid}/open").json()["status"] == "CHECKIN_OPEN"
    factories.student(db, 2)
    db.commit()
    r = boss_client.post(f"/api/admin/events/{eid}/participants", json={"student_id": "BTU-T-0002"})
    assert r.status_code == 201 and r.json()["method"] == "MANUAL"
    r = boss_client.post(f"/api/admin/events/{eid}/complete")
    assert (r.status_code, r.json()["error"], r.json()["blockers"]) == (
        409,
        "cannot_complete",
        ["CHECKIN_OPEN"],
    )
    assert boss_client.post(f"/api/admin/events/{eid}/close").json()["status"] == "CHECKIN_CLOSED"
    first = boss_client.post(f"/api/admin/events/{eid}/complete")
    again = boss_client.post(f"/api/admin/events/{eid}/complete")
    assert (first.status_code, again.status_code) == (200, 200)
    assert first.json() == again.json() and len(first.json()["awarded"]) == 1
    detail = boss_client.get(f"/api/admin/events/{eid}").json()
    assert detail["status"] == "COMPLETED" and detail["completion"] == first.json()

    r = boss_client.delete(f"/api/admin/events/{eid}")
    assert (r.status_code, r.json()["error"]) == (409, "event_completed")
    r = boss_client.patch(f"/api/admin/events/{eid}", json={"name": "x"})
    assert (r.status_code, r.json()["error"]) == (409, "event_completed")


def test_delete_is_soft_and_hidden(boss_client: TestClient) -> None:
    eid = _create(boss_client)["event_id"]
    assert boss_client.delete(f"/api/admin/events/{eid}").status_code == 204
    assert boss_client.get(f"/api/admin/events/{eid}").status_code == 404
    assert boss_client.get("/api/admin/events").json()["total"] == 0


def test_skill_locked_over_the_api(db: Session, boss_client: TestClient) -> None:
    eid = _create(boss_client)["event_id"]
    factories.skill(db, "SKL-002")
    factories.student(db, 2)
    db.commit()
    boss_client.post(f"/api/admin/events/{eid}/participants", json={"student_id": "BTU-T-0002"})
    r = boss_client.patch(f"/api/admin/events/{eid}", json={"skill_id": "SKL-002"})
    assert (r.status_code, r.json()["error"]) == (409, "skill_locked")
    assert "skill_id" in r.json()["fields"]


def test_participants_list_and_remove(db: Session, boss_client: TestClient) -> None:
    eid = _create(boss_client)["event_id"]
    factories.student(db, 2)
    db.commit()
    boss_client.post(f"/api/admin/events/{eid}/participants", json={"student_id": "BTU-T-0002"})
    r = boss_client.delete(f"/api/admin/events/{eid}/participants/btu-t-0002@example.org")
    assert r.status_code == 204
    assert boss_client.get(f"/api/admin/events/{eid}/participants").json() == []
    rows = boss_client.get(
        f"/api/admin/events/{eid}/participants", params={"include_removed": True}
    ).json()
    assert len(rows) == 1 and rows[0]["removed_at"] is not None


def test_Q14_admin_reads_but_cannot_write(db: Session, client_as: ClientAs) -> None:
    factories.skill(db, "SKL-001")
    db.commit()
    eid = _create(client_as("super_admin"))["event_id"]
    admin = client_as("admin")
    for path in (
        "/api/admin/events",
        f"/api/admin/events/{eid}",
        f"/api/admin/events/{eid}/participants",
    ):
        assert admin.get(path).status_code == 200, path
    writes = [
        ("POST", "/api/admin/events", _new()),
        ("PATCH", f"/api/admin/events/{eid}", {"name": "x"}),
        ("DELETE", f"/api/admin/events/{eid}", None),
        ("POST", f"/api/admin/events/{eid}/open", None),
        ("POST", f"/api/admin/events/{eid}/close", None),
        ("POST", f"/api/admin/events/{eid}/reopen", None),
        ("POST", f"/api/admin/events/{eid}/complete", None),
        ("POST", f"/api/admin/events/{eid}/participants", {"student_id": "BTU-T-0001"}),
        ("DELETE", f"/api/admin/events/{eid}/participants/x@btu.test", None),
    ]
    for method, path, body in writes:
        r = admin.request(method, path, json=body)
        assert (r.status_code, r.json()["error"]) == (403, "forbidden"), (method, path)
