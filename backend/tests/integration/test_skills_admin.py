"""BE-50: skills catalog writes (FR-07, FR-34, FR-35). Super admin only; admins read."""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, PassportVersion, Skill
from app.services import issuance, storage
from tests import factories as f
from tests.conftest import FakeChain

ClientAs = Callable[[str | None], TestClient]
RunJobs = Callable[[], int]


@pytest.fixture
def sa(client_as: ClientAs) -> TestClient:
    return client_as("super_admin")


@pytest.fixture
def category_id(db: Session) -> int:
    sk = f.skill(db, "SKL-009")  # also gives a category
    db.commit()
    return sk.category_id


def _audit(db: Session, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)))


def _create(client: TestClient, category_id: int, name: str = "Agentic AI Basics") -> Any:
    r = client.post(
        "/api/admin/skills",
        json={"name": name, "category_id": category_id, "description": "Using AI agents."},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_numbers_the_next_skill_id_and_audits(
    db: Session, sa: TestClient, category_id: int
) -> None:
    row = _create(sa, category_id)
    assert row["skill_id"] == "SKL-010"  # after SKL-009
    assert (row["name"], row["times_awarded"], row["archived"]) == ("Agentic AI Basics", 0, False)
    assert row["category"]["category_id"] == category_id
    assert _create(sa, category_id, "Second")["skill_id"] == "SKL-011"
    (entry, _) = _audit(db, "skill.create")
    assert (entry.actor_email, entry.entity, entry.entity_id) == (
        "superadmin@btu.test",
        "skill",
        "SKL-010",
    )
    assert entry.before is None and entry.after == {
        "name": "Agentic AI Basics",
        "category_id": category_id,
        "description": "Using AI agents.",
    }


def test_create_validation(db: Session, sa: TestClient, category_id: int) -> None:
    r = sa.post(
        "/api/admin/skills",
        json={"name": " ", "category_id": 999, "description": "x" * 301},
    )
    assert (r.status_code, r.json()["error"]) == (422, "validation_error")
    assert set(r.json()["fields"]) == {"name", "category_id", "description"}
    assert sa.post(
        "/api/admin/skills", json={"name": "x" * 81, "category_id": category_id, "description": "d"}
    ).json()["fields"].keys() == {"name"}


def test_duplicate_name_is_a_409_under_the_field(sa: TestClient, category_id: int) -> None:
    r = sa.post(
        "/api/admin/skills",
        json={"name": "skill skl-009", "category_id": category_id, "description": "d"},
    )
    assert (r.status_code, r.json()["error"]) == (409, "duplicate_name")
    assert "name" in r.json()["fields"]


def test_edit_audits_only_what_changed(db: Session, sa: TestClient, category_id: int) -> None:
    r = sa.patch("/api/admin/skills/SKL-009", json={"name": "Renamed", "description": "A skill."})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    (entry,) = _audit(db, "skill.update")
    assert (entry.before, entry.after) == ({"name": "Skill SKL-009"}, {"name": "Renamed"})
    assert sa.patch("/api/admin/skills/SKL-009", json={"name": "Renamed"}).status_code == 200
    assert len(_audit(db, "skill.update")) == 1  # nothing changed, nothing audited
    bad = sa.patch("/api/admin/skills/SKL-009", json={"skill_id": "SKL-100"})
    assert bad.status_code == 422
    assert sa.patch("/api/admin/skills/SKL-404", json={"name": "x"}).status_code == 404


def test_archive_hides_the_skill_from_forms(
    db: Session, client_as: ClientAs, sa: TestClient, category_id: int
) -> None:
    r = sa.post("/api/admin/skills/SKL-009/archive")
    assert (r.status_code, r.json()["archived"]) == (200, True)
    admin = client_as("admin")
    assert [s["skill_id"] for s in admin.get("/api/admin/skills").json()] == []
    listed = admin.get("/api/admin/skills", params={"include_archived": True}).json()
    assert [(s["skill_id"], s["archived"]) for s in listed] == [("SKL-009", True)]

    f.student(db, 1)
    db.commit()
    award = {
        "student_ids": ["BTU-T-0001"],
        "skill_id": "SKL-009",
        "date_earned": "2026-10-01",
        "reason": "Course",
    }
    preview = admin.post("/api/admin/awards/preview", json=award)
    assert preview.status_code == 422 and "skill_id" in preview.json()["fields"]
    start = datetime(2026, 11, 1, 10, tzinfo=UTC)
    event = sa.post(
        "/api/admin/events",
        json={
            "name": "Workshop",
            "skill_id": "SKL-009",
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=2)).isoformat(),
        },
    )
    assert event.status_code == 422 and "skill_id" in event.json()["fields"]

    assert sa.post("/api/admin/skills/SKL-009/archive").status_code == 200
    assert len(_audit(db, "skill.archive")) == 1  # archiving twice changes nothing
    r = sa.post("/api/admin/skills/SKL-009/unarchive")
    assert (r.status_code, r.json()["archived"]) == (200, False)
    assert len(_audit(db, "skill.unarchive")) == 1


def test_delete_only_when_unused(db: Session, sa: TestClient, category_id: int) -> None:
    unused = _create(sa, category_id)["skill_id"]
    assert sa.delete(f"/api/admin/skills/{unused}").status_code == 204
    assert db.get(Skill, unused) is None
    (entry,) = _audit(db, "skill.delete")
    assert entry.before is not None and entry.before["name"] == "Agentic AI Basics"
    assert sa.delete(f"/api/admin/skills/{unused}").status_code == 404

    awarded = db.get_one(Skill, "SKL-009")
    f.award(db, f.student(db, 1), awarded)
    in_event = f.skill(db, "SKL-020")
    ev = f.event(db, in_event, f.user(db, "organiser@btu.test"))
    ev.deleted_at = datetime.now(UTC)  # even a deleted event still names its skill
    db.commit()
    for skill_id in ("SKL-009", "SKL-020"):
        r = sa.delete(f"/api/admin/skills/{skill_id}")
        assert (r.status_code, r.json()["error"]) == (409, "in_use"), skill_id
    assert db.get(Skill, "SKL-009") is not None


def test_rename_and_archive_leave_issued_passports_alone(
    db: Session, sa: TestClient, s3_bucket: str, fake_chain: FakeChain, run_jobs: RunJobs
) -> None:
    st, sk = f.student(db, 1), f.skill(db, "SKL-001")
    f.award(db, st, sk)
    (made,) = issuance.create_versions(db, [st.student_id])
    db.commit()
    run_jobs()
    db.expire_all()
    version = db.get_one(PassportVersion, made.version_id)
    assert version.status == "ANCHORED"
    content, pdf_sha = version.content_json, version.pdf_sha256

    r = sa.patch("/api/admin/skills/SKL-001", json={"name": "Renamed", "description": "New."})
    assert r.status_code == 200, r.text
    assert sa.post("/api/admin/skills/SKL-001/archive").status_code == 200
    db.expire_all()
    version = db.get_one(PassportVersion, made.version_id)
    assert version.content_json == content
    assert content is not None and content["skills"][0]["name"] == "Skill SKL-001"
    assert hashlib.sha256(storage.get(version.pdf_key or "")).hexdigest() == pdf_sha
    verdict = sa.get(f"/api/verify/{version.verification_code}").json()
    assert verdict["verdict"] == "VALID"
    assert verdict["version"]["skills"][0]["name"] == "Skill SKL-001"
