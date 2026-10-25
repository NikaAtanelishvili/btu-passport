"""BE-53: the audit log page's API (FR-09). Super admin only; newest first; filters."""

import io
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.models import AuditLog
from tests import factories as f

ClientAs = Callable[[str | None], TestClient]
SA = "superadmin@btu.test"


@pytest.fixture
def sa(client_as: ClientAs) -> TestClient:
    return client_as("super_admin")


def _row(db: Session, at: datetime, actor: str | None, action: str, entity_id: str = "x") -> None:
    db.add(
        AuditLog(
            at=at,
            actor_email=actor,
            action=action,
            entity=action.split(".")[0],
            entity_id=entity_id,
            before={"n": 1},
            after={"n": 2},
        )
    )


@pytest.fixture
def rows(db: Session) -> None:
    _row(db, datetime(2026, 10, 20, 8, tzinfo=UTC), "admin@btu.test", "student.create", "S1")
    _row(db, datetime(2026, 10, 21, 8, tzinfo=UTC), SA, "skill.create", "SKL-001")
    # 21:30 UTC on the 21st is already the 22nd in Tbilisi (UTC+4).
    _row(db, datetime(2026, 10, 21, 21, 30, tzinfo=UTC), SA, "skill.update", "SKL-001")
    _row(db, datetime(2026, 10, 23, 8, tzinfo=UTC), None, "event.open", "E1")  # the system
    db.commit()


def _get(client: TestClient, **params: Any) -> Any:
    r = client.get("/api/admin/audit", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_newest_first_with_before_and_after(sa: TestClient, rows: None) -> None:
    page = _get(sa)
    assert page["total"] == 4 and (page["page"], page["page_size"]) == (1, 25)
    assert [r["action"] for r in page["items"]] == [
        "event.open",
        "skill.update",
        "skill.create",
        "student.create",
    ]
    first = page["items"][1]
    assert set(first) == {
        "id",
        "at",
        "actor_email",
        "action",
        "entity",
        "entity_id",
        "before",
        "after",
    }
    assert (first["actor_email"], first["before"], first["after"]) == (SA, {"n": 1}, {"n": 2})
    assert page["items"][0]["actor_email"] is None


def test_filters(sa: TestClient, rows: None) -> None:
    def actions(**params: Any) -> list[str]:
        return [r["action"] for r in _get(sa, **params)["items"]]

    assert actions(actor="SUPERADMIN") == ["skill.update", "skill.create"]  # part of the email
    assert actions(action="skill.create") == ["skill.create"]
    # Dates are BTU's calendar days (Asia/Tbilisi), both ends included.
    assert actions(**{"from": "2026-10-22"}) == ["event.open", "skill.update"]
    assert actions(to="2026-10-21") == ["skill.create", "student.create"]
    assert actions(**{"from": "2026-10-21", "to": "2026-10-21"}) == ["skill.create"]
    assert actions(actor="superadmin", **{"from": "2026-10-22"}) == ["skill.update"]
    r = sa.get("/api/admin/audit", params={"from": "2026-10-23", "to": "2026-10-20"})
    assert r.status_code == 422 and "to" in r.json()["fields"]


def test_paging(sa: TestClient, rows: None) -> None:
    page = _get(sa, page=2, page_size=3)
    assert (page["total"], [r["action"] for r in page["items"]]) == (4, ["student.create"])


def test_action_list_for_the_filter(sa: TestClient, rows: None) -> None:
    r = sa.get("/api/admin/audit/actions")
    assert r.json() == ["event.open", "skill.create", "skill.update", "student.create"]


def test_every_super_admin_action_is_audited(db: Session, sa: TestClient, s3_bucket: str) -> None:
    """Catalog and roles through the API: one row each, with actor, before and after."""
    png = io.BytesIO()
    Image.new("RGB", (600, 600), "navy").save(png, "PNG")
    category = sa.post("/api/admin/categories", json={"name": "AI Skill"}).json()["category_id"]
    calls = [
        ("patch", f"/api/admin/categories/{category}", {"name": "AI Core Skill"}),
        ("post", f"/api/admin/categories/{category}/stamp", None),
        ("post", "/api/admin/skills", {"name": "S", "category_id": category, "description": "d"}),
        ("patch", "/api/admin/skills/SKL-001", {"description": "Better."}),
        ("post", "/api/admin/skills/SKL-001/archive", None),
        ("post", "/api/admin/skills/SKL-001/unarchive", None),
        ("delete", "/api/admin/skills/SKL-001", None),
        ("post", f"/api/admin/categories/{category}/archive", None),
        ("post", f"/api/admin/categories/{category}/unarchive", None),
        ("delete", f"/api/admin/categories/{category}", None),
        ("put", "/api/admin/roles/helper@btu.test", {"role": "ADMIN"}),
        ("delete", "/api/admin/roles/helper@btu.test", None),
    ]
    for method, url, body in calls:
        if url.endswith("/stamp"):
            r = sa.post(url, files={"file": ("s.png", png.getvalue(), "image/png")})
        else:
            r = sa.request(method.upper(), url, json=body)
        assert r.is_success, (url, r.text)

    items = _get(sa, actor=SA, page_size=100)["items"]
    assert sorted(r["action"] for r in items) == sorted(
        [
            "category.create",
            "category.update",
            "category.stamp",
            "skill.create",
            "skill.update",
            "skill.archive",
            "skill.unarchive",
            "skill.delete",
            "category.archive",
            "category.unarchive",
            "category.delete",
            "role.grant",
            "role.revoke",
        ]
    )
    for r in items:
        assert r["actor_email"] == SA
        assert r["before"] is not None or r["after"] is not None, r
        if r["action"].endswith((".update", ".archive", ".unarchive", ".stamp")):
            assert r["before"] is not None and r["after"] is not None, r


def test_events_by_super_admin_are_audited_too(db: Session, sa: TestClient) -> None:
    f.skill(db, "SKL-001")
    db.commit()
    start = "2026-11-01T10:00:00+04:00"
    r = sa.post(
        "/api/admin/events",
        json={
            "name": "Workshop",
            "skill_id": "SKL-001",
            "starts_at": start,
            "ends_at": "2026-11-01T12:00:00+04:00",
        },
    )
    assert r.status_code == 201, r.text
    assert sa.patch(f"/api/admin/events/{r.json()['event_id']}", json={"name": "W2"}).is_success
    actions = {x["action"]: x for x in _get(sa, actor=SA)["items"]}
    assert {"event.create", "event.update"} <= set(actions)
    assert actions["event.update"]["before"] == {"name": "Workshop"}
