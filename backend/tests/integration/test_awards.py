"""BE-23/BE-24: direct awards through the API."""

import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, AwardSubmission, Job, PassportVersion, Skill, SkillAward

ClientAs = Callable[[str | None], TestClient]
TODAY = date.today()


def _body(**over: Any) -> dict[str, Any]:
    body = {
        "student_ids": ["BTU-T-0021"],
        "skill_id": "SKL-001",  # BTU-T-0021 doesn't hold it
        "date_earned": "2026-10-20",
        "reason": "Completed the AI Literacy workshop",
    }
    return {**body, **over}


def _post(client: TestClient, body: dict[str, Any], key: str | None = None) -> Any:
    headers = {"Idempotency-Key": key or str(uuid.uuid4())}
    return client.post("/api/admin/awards", json=body, headers=headers)


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


@pytest.fixture
def admin(seeded: Session, client_as: ClientAs) -> TestClient:
    return client_as("admin")


def test_direct_award_creates_award_version_and_job(seeded: Session, admin: TestClient) -> None:
    r = _post(admin, _body())
    assert r.status_code == 202, r.text
    body = r.json()
    [v] = body["versions"]
    assert (v["student_id"], v["version_no"], body["skipped"]) == ("BTU-T-0021", 1, [])
    version = seeded.get(PassportVersion, v["version_id"])
    assert version is not None and version.status == "PENDING"
    award = seeded.scalars(
        select(SkillAward).where(
            SkillAward.student_id == "BTU-T-0021", SkillAward.skill_id == "SKL-001"
        )
    ).one()
    assert str(award.submission_id) == body["submission_id"]
    assert award.date_earned == date(2026, 10, 20)
    audit = seeded.scalars(select(AuditLog).where(AuditLog.action == "award.direct")).one()
    assert audit.entity_id == body["submission_id"] and audit.actor_email == "admin@btu.test"


def test_A3_idempotent(seeded: Session, admin: TestClient) -> None:
    key = str(uuid.uuid4())
    first = _post(admin, _body(), key)
    counts = [_count(seeded, m) for m in (AwardSubmission, SkillAward, PassportVersion, Job)]
    again = _post(admin, _body(), key)
    assert (first.status_code, again.status_code) == (202, 202)
    assert again.json() == first.json()
    assert [
        _count(seeded, m) for m in (AwardSubmission, SkillAward, PassportVersion, Job)
    ] == counts


def test_already_held_is_skipped(seeded: Session, admin: TestClient) -> None:
    # Both hold SKL-002 (REC-0002, REC-0049); neither holds SKL-001.
    r = _post(admin, _body(student_ids=["BTU-T-0021", "BTU-T-0002"], skill_id="SKL-002"))
    assert (r.status_code, r.json()["versions"]) == (202, [])
    assert r.json()["skipped"] == ["BTU-T-0002", "BTU-T-0021"]
    r2 = _post(admin, _body(student_ids=["BTU-T-0021", "BTU-T-0002"]))
    assert [v["student_id"] for v in r2.json()["versions"]] == ["BTU-T-0002", "BTU-T-0021"]


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"date_earned": str(TODAY + timedelta(days=2))}, "date_earned"),
        ({"reason": ""}, "reason"),
        ({"reason": "x" * 301}, "reason"),
        ({"skill_id": "SKL-999"}, "skill_id"),
        ({"student_ids": ["BTU-T-0021", "BTU-T-9999"]}, "student_ids"),
        ({"student_ids": []}, "student_ids"),
    ],
)
def test_invalid_award_saves_nothing(
    seeded: Session, admin: TestClient, over: dict[str, Any], field: str
) -> None:
    before = [_count(seeded, m) for m in (AwardSubmission, SkillAward, PassportVersion, Job)]
    r = _post(admin, _body(**over))
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "validation_error" and field in r.json()["fields"]
    assert [
        _count(seeded, m) for m in (AwardSubmission, SkillAward, PassportVersion, Job)
    ] == before


def test_today_in_tbilisi_is_allowed(seeded: Session, admin: TestClient) -> None:
    today = datetime.now(ZoneInfo("Asia/Tbilisi")).date()
    assert _post(admin, _body(date_earned=str(today))).status_code == 202


def test_archived_skill_is_rejected(seeded: Session, admin: TestClient) -> None:
    skill = seeded.get(Skill, "SKL-001")
    assert skill is not None
    skill.archived_at = func.now()
    seeded.commit()
    r = _post(admin, _body())
    assert (r.status_code, list(r.json()["fields"])) == (422, ["skill_id"])


def test_idempotency_key_is_required(seeded: Session, admin: TestClient) -> None:
    r = admin.post("/api/admin/awards", json=_body())
    assert r.status_code == 422 and "Idempotency-Key" in r.json()["fields"]


def test_preview_writes_nothing(seeded: Session, admin: TestClient) -> None:
    before = [_count(seeded, m) for m in (AwardSubmission, SkillAward, PassportVersion, Job)]
    r = admin.post(
        "/api/admin/awards/preview",
        json=_body(student_ids=["BTU-T-0002", "BTU-T-0021"], skill_id="SKL-002"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == [
        {
            "student_id": "BTU-T-0002",
            "name": "Mariam Beridze",
            "result": "SKIP_ALREADY_HELD",
            "from_version": None,
            "to_version": None,
        },
        {
            "student_id": "BTU-T-0021",
            "name": "Luka Japaridze",
            "result": "SKIP_ALREADY_HELD",
            "from_version": None,
            "to_version": None,
        },
    ]
    r = admin.post("/api/admin/awards/preview", json=_body(student_ids=["BTU-T-0002"]))
    assert r.json()["rows"][0] == {
        "student_id": "BTU-T-0002",
        "name": "Mariam Beridze",
        "result": "NEW_VERSION",
        "from_version": 1,
        "to_version": 2,
    }
    assert [
        _count(seeded, m) for m in (AwardSubmission, SkillAward, PassportVersion, Job)
    ] == before


def test_student_cannot_award(seeded: Session, client_as: ClientAs) -> None:
    r = _post(client_as("unregistered"), _body())
    assert r.status_code == 403
