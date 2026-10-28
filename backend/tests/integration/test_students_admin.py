"""BE-35: register, list, view and edit students (FR-02, FR-10, FR-11)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Passport, PassportVersion, Skill, Student
from tests import factories

ClientAs = Callable[[str | None], TestClient]


def _new(**over: Any) -> dict[str, Any]:
    body = {
        "student_id": "BTU-T-0100",
        "first_name": "Giorgi",
        "last_name": "Kapanadze",
        "email": "Giorgi.Kapanadze@btu.edu.ge",
        "program": "Information Technologies",
        "education_level": "BACHELOR",
        "status": "ACTIVE",
    }
    return {**body, **over}


@pytest.fixture
def admin(seeded: Session, client_as: ClientAs) -> TestClient:
    return client_as("admin")


def test_register_creates_student_and_one_passport(seeded: Session, admin: TestClient) -> None:
    r = admin.post("/api/admin/students", json=_new())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["profile"]["email"] == "giorgi.kapanadze@btu.edu.ge"  # stored lower-case
    # The seed's highest Passport ID is BTU-AI-000142.
    assert body["passport"]["passport_id"] == "BTU-AI-000143"
    # D5 (SH-08): the passport's first version V1 is queued at registration, with no skills.
    assert body["passport"]["frozen"] is False
    assert [(v["version_no"], v["status"]) for v in body["passport"]["versions"]] == [
        (1, "PENDING")
    ]
    passports = seeded.scalars(select(Passport).where(Passport.student_id == "BTU-T-0100")).all()
    assert len(passports) == 1 and passports[0].holder_first_name is None
    audit = seeded.scalars(select(AuditLog).where(AuditLog.action == "student.create")).one()
    assert (audit.entity_id, audit.actor_email) == ("BTU-T-0100", "admin@btu.test")
    assert audit.after is not None and audit.after["passport_id"] == "BTU-AI-000143"


@pytest.mark.parametrize(
    ("over", "error", "field"),
    [
        ({"email": "btu-t-0001@example.org"}, "duplicate_email", "email"),
        ({"email": "BTU-T-0001@EXAMPLE.ORG"}, "duplicate_email", "email"),
        ({"student_id": "BTU-T-0001"}, "duplicate_student_id", "student_id"),
    ],
)
def test_duplicate_is_409_under_the_field(
    seeded: Session, admin: TestClient, over: dict[str, Any], error: str, field: str
) -> None:
    before = seeded.scalar(select(func.count()).select_from(Student))
    r = admin.post("/api/admin/students", json=_new(**over))
    assert r.status_code == 409, r.text
    assert r.json()["error"] == error and field in r.json()["fields"]
    assert seeded.scalar(select(func.count()).select_from(Student)) == before


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"student_id": "12345"}, "student_id"),
        ({"first_name": ""}, "first_name"),
        ({"last_name": "x" * 61}, "last_name"),
        ({"email": "someone@gmail.com"}, "email"),
        ({"email": "not-an-email"}, "email"),
        ({"program": " "}, "program"),
        ({"education_level": "PHD"}, "education_level"),
        ({"status": "LEFT"}, "status"),
    ],
)
def test_invalid_registration_is_422_under_the_field(
    seeded: Session, admin: TestClient, over: dict[str, Any], field: str
) -> None:
    r = admin.post("/api/admin/students", json=_new(**over))
    assert r.status_code == 422, r.text
    assert field in r.json()["fields"]


def test_list_filters_and_columns(seeded: Session, admin: TestClient) -> None:
    page = admin.get("/api/admin/students", params={"q": "btu-t-0002"}).json()
    [row] = page["items"]
    assert row["passport_id"] == "BTU-AI-000126"
    # The seed gives BTU-T-0002 a LEGACY V1.
    assert (row["latest_version_no"], row["latest_status"]) == (1, "LEGACY")
    issued = admin.get("/api/admin/students", params={"has_passport": True}).json()
    not_issued = admin.get("/api/admin/students", params={"has_passport": False}).json()
    assert issued["total"] + not_issued["total"] == 18 and issued["total"] > 0
    masters = admin.get("/api/admin/students", params={"education_level": "MASTER"}).json()
    assert masters["total"] > 0
    assert all(s["education_level"] == "MASTER" for s in masters["items"])


def test_programs(seeded: Session, admin: TestClient) -> None:
    programs = admin.get("/api/admin/programs").json()
    assert len(programs) == len(set(programs)) > 1
    assert "Information Technologies" in programs


def test_detail(seeded: Session, admin: TestClient) -> None:
    r = admin.get("/api/admin/students/BTU-T-0002")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profile"]["student_id"] == "BTU-T-0002"
    assert body["passport"]["frozen"] is True
    assert [v["version_no"] for v in body["passport"]["versions"]] == [1]
    assert body["awards"] and all(a["source"] == "SEED" for a in body["awards"])
    assert {"skill_name", "category", "date_earned", "awarded_by"} <= set(body["awards"][0])
    assert body["events"] == []
    assert admin.get("/api/admin/students/BTU-T-9999").status_code == 404


def test_detail_shows_direct_award_source(seeded: Session, admin: TestClient) -> None:
    award = {
        "student_ids": ["BTU-T-0021"],
        "skill_id": "SKL-001",
        "date_earned": "2026-10-20",
        "reason": "Course completion",
    }
    headers = {"Idempotency-Key": "8a6e0f4e-4c39-4d7b-9a3c-0b8f6f0f0b01"}
    assert admin.post("/api/admin/awards", json=award, headers=headers).status_code == 202
    awards = admin.get("/api/admin/students/BTU-T-0021").json()["awards"]
    direct = next(a for a in awards if a["skill_id"] == "SKL-001")
    assert direct["source"] == "DIRECT" and direct["awarded_by"] == "admin@btu.test"
    assert direct["reason"] == "Course completion"


def test_edit_before_first_issue_changes_name_quietly(seeded: Session, admin: TestClient) -> None:
    admin.post("/api/admin/students", json=_new())
    r = admin.patch("/api/admin/students/BTU-T-0100", json={"first_name": "Giorgos"})
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["first_name"] == "Giorgos" and r.json()["warnings"] == []


def test_FR11_edit_after_issue_warns_and_leaves_passport(
    seeded: Session, admin: TestClient
) -> None:
    passport = seeded.scalars(select(Passport).where(Passport.student_id == "BTU-T-0002")).one()
    printed = (passport.holder_first_name, passport.holder_last_name, passport.first_issued_on)
    r = admin.patch(
        "/api/admin/students/BTU-T-0002",
        json={"last_name": "Beridze-Kapanadze", "status": "GRADUATE"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == ["printed_name_differs"]
    assert r.json()["profile"]["last_name"] == "Beridze-Kapanadze"
    seeded.expire_all()
    passport = seeded.scalars(select(Passport).where(Passport.student_id == "BTU-T-0002")).one()
    assert (
        passport.holder_first_name,
        passport.holder_last_name,
        passport.first_issued_on,
    ) == printed
    audit = seeded.scalars(select(AuditLog).where(AuditLog.action == "student.update")).one()
    assert audit.before == {"last_name": "Beridze", "status": "ACTIVE"}
    assert audit.after == {"last_name": "Beridze-Kapanadze", "status": "GRADUATE"}
    assert audit.actor_email == "admin@btu.test"


def test_edit_to_a_taken_email_is_409(seeded: Session, admin: TestClient) -> None:
    r = admin.patch("/api/admin/students/BTU-T-0002", json={"email": "btu-t-0003@example.org"})
    assert (r.status_code, r.json()["error"]) == (409, "duplicate_email")
    assert "email" in r.json()["fields"]


def test_edit_cannot_change_student_id(seeded: Session, admin: TestClient) -> None:
    r = admin.patch("/api/admin/students/BTU-T-0002", json={"student_id": "BTU-T-0999"})
    assert r.status_code == 422
    assert seeded.get(Student, "BTU-T-0002") is not None


def test_no_op_edit_writes_no_audit_row(seeded: Session, admin: TestClient) -> None:
    current = seeded.get(Student, "BTU-T-0002")
    assert current is not None
    r = admin.patch("/api/admin/students/BTU-T-0002", json={"status": current.status})
    assert r.status_code == 200
    assert seeded.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_skills_for_the_award_form(seeded: Session, admin: TestClient) -> None:
    skills = admin.get("/api/admin/skills").json()
    assert len(skills) == 16 and not any(s["archived"] for s in skills)
    first = skills[0]
    assert first["skill_id"] == "SKL-001" and first["category"]["stamp_sha256"]
    assert first["times_awarded"] > 0


def test_dashboard(seeded: Session, admin: TestClient) -> None:
    seeded.add(PassportVersion(passport_id="BTU-AI-000126", version_no=2, status="FAILED"))
    skill = seeded.get(Skill, "SKL-001")
    assert skill is not None
    creator = factories.user(seeded, "organiser@btu.test")
    open_ = factories.event(seeded, skill, creator, status="CHECKIN_OPEN")
    factories.participant(seeded, open_, "newcomer@btu.test")  # no student row: Unregistered
    factories.participant(seeded, open_, "btu-t-0002@example.org").student_id = "BTU-T-0002"
    factories.event(seeded, skill, creator, status="CHECKIN_CLOSED")
    factories.event(seeded, skill, creator, status="CHECKIN_CLOSED").deleted_at = func.now()
    seeded.commit()
    body = admin.get("/api/admin/dashboard").json()
    assert body["failed_versions"] == 1
    counts = (body["checkin_open"], body["awaiting_completion"], body["unregistered_checkins"])
    assert counts == (1, 1, 1)
    assert body["recent"] == []  # the seed's versions are LEGACY, not issued here


def test_dashboard_recent_lists_anchored_versions(seeded: Session, admin: TestClient) -> None:
    for n in range(2, 14):
        seeded.add(PassportVersion(passport_id="BTU-AI-000126", version_no=n, status="ANCHORED"))
    seeded.commit()
    recent = admin.get("/api/admin/dashboard").json()["recent"]
    assert [v["version_no"] for v in recent] == list(range(13, 3, -1))


def test_registered_student_gets_an_anchored_v1_that_verifies(
    seeded: Session,
    admin: TestClient,
    fake_chain: Any,
    run_jobs: Callable[[], int],
    s3_bucket: str,
) -> None:
    """SH-08 (D5, spec FR 1 "Adding a new student"): no award needed for the first PDF."""
    import hashlib

    from app.services import storage

    admin.post("/api/admin/students", json=_new())
    run_jobs()
    seeded.expire_all()
    passport = seeded.scalars(select(Passport).where(Passport.student_id == "BTU-T-0100")).one()
    [v1] = seeded.scalars(
        select(PassportVersion).where(PassportVersion.passport_id == passport.passport_id)
    ).all()
    assert (v1.version_no, v1.status) == (1, "ANCHORED")
    assert v1.content_json is not None and v1.content_json["skills"] == []
    # Frozen fields are set at V1.
    assert (passport.holder_first_name, passport.holder_last_name) == ("Giorgi", "Kapanadze")
    assert passport.first_issued_on is not None
    assert passport.latest_version_id == v1.version_id
    pdf = storage.get(storage.pdf_key(v1.pdf_sha256 or ""))
    verdict = admin.post("/api/verify/hash", json={"sha256": hashlib.sha256(pdf).hexdigest()})
    assert verdict.json()["verdict"] == "VALID", verdict.text
