"""BE-47: the student portal API (FR-25, A8). Every /api/me route reads the signed-in student's
own passport; none of them takes a student or passport ID, so there is nothing to swap."""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PassportVersion, Skill, SkillAward, Student, VersionAward
from app.services import issuance
from tests import factories as f
from tests.conftest import FakeChain

ClientAs = Callable[[str | None], TestClient]
RunJobs = Callable[[], int]


def _client(db: Session, email: str) -> TestClient:
    """A signed-in client for any email (client_as only knows the fixed test roles)."""
    from app.auth import sessions
    from app.config import get_settings
    from app.main import create_app
    from app.models import User

    user = db.scalars(select(User).where(User.email == email)).one_or_none() or f.user(db, email)
    token, row = sessions.create_session(db, user)
    db.commit()
    client = TestClient(create_app())
    client.cookies.set(get_settings().session_cookie_name, token)
    client.cookies.set(sessions.CSRF_COOKIE, row.csrf_token)
    client.headers["X-CSRF-Token"] = row.csrf_token
    return client


def _version(db: Session, passport_id: str, version_no: int) -> PassportVersion:
    return db.scalars(
        select(PassportVersion).where(
            PassportVersion.passport_id == passport_id, PassportVersion.version_no == version_no
        )
    ).one()


@pytest.fixture
def issued(seeded: Session, fake_chain: FakeChain, run_jobs: RunJobs) -> Session:
    """The seed issued: BTU-T-0002 (BTU-AI-000126) has LEGACY v1 (2 skills), ANCHORED v2 (4)."""
    issuance.issue_pending(seeded)
    seeded.commit()
    run_jobs()
    seeded.expire_all()
    return seeded


def _award_new_version(db: Session, student_id: str, skill_id: str) -> None:
    student, skill = db.get_one(Student, student_id), db.get_one(Skill, skill_id)
    f.award(db, student, skill)
    issuance.create_versions(db, [student_id])
    db.commit()


def _unheld_skill(db: Session, student_id: str) -> str:
    owned = set(db.scalars(select(SkillAward.skill_id).where(SkillAward.student_id == student_id)))
    skills = db.scalars(select(Skill.skill_id).order_by(Skill.skill_id))
    return next(s for s in skills if s not in owned)


def test_A8_scoping(issued: Session) -> None:
    db = issued
    mariam = _client(db, "btu-t-0002@example.org")

    passport = mariam.get("/api/me/passport")
    assert passport.status_code == 200, passport.text
    body = passport.json()
    assert (body["passport_id"], body["holder_name"]) == ("BTU-AI-000126", "Mariam Beridze")
    v2 = _version(db, "BTU-AI-000126", 2)
    assert body["current"]["version_no"] == 2
    assert body["current"]["verification_code"] == v2.verification_code
    assert body["issuing"] is None and len(body["skills"]) == 4

    pdf = mariam.get("/api/me/versions/2/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert hashlib.sha256(pdf.content).hexdigest() == v2.pdf_sha256
    assert 'filename="BTU-AI-000126-v2.pdf"' in pdf.headers["content-disposition"]
    proof = mariam.get("/api/me/versions/2/proof.json")
    assert proof.status_code == 200 and proof.json()["passport_id"] == "BTU-AI-000126"

    # Another student's v3: Mariam has no v3, so the same URL is a 404 for her.
    other = db.scalars(select(Student).where(Student.student_id != "BTU-T-0002")).first()
    assert other is not None
    _award_new_version(db, other.student_id, _unheld_skill(db, other.student_id))
    for url in ("/api/me/versions/3/pdf", "/api/me/versions/3/proof.json"):
        assert mariam.get(url).status_code == 404

    # IDs in the query string are ignored; admin routes stay closed (A11).
    sneaky = mariam.get("/api/me/passport", params={"student_id": other.student_id})
    assert sneaky.json()["passport_id"] == "BTU-AI-000126"
    assert mariam.get(f"/api/admin/students/{other.student_id}").status_code == 403
    versions = mariam.get("/api/me/versions").json()
    assert {v["verification_code"] for v in versions} - {None} == {v2.verification_code}


def test_versions_newest_first_with_what_changed(issued: Session) -> None:
    db = issued
    mariam = _client(db, "btu-t-0002@example.org")
    versions = mariam.get("/api/me/versions").json()
    assert [(v["version_no"], v["status"], v["skill_count"]) for v in versions] == [
        (2, "ANCHORED", 4),
        (1, "LEGACY", 2),
    ]
    v2_skills = {s["name"] for s in (_version(db, "BTU-AI-000126", 2).content_json or {})["skills"]}
    assert len(versions[0]["added_skills"]) == 2 and set(versions[0]["added_skills"]) <= v2_skills
    assert len(versions[1]["added_skills"]) == 2  # the first version adds everything it holds
    assert versions[1]["verification_code"] is None and versions[1]["issued_at"]
    assert [v["superseded"] for v in versions] == [False, False]


def test_only_anchored_versions_download(issued: Session) -> None:
    db = issued
    mariam = _client(db, "btu-t-0002@example.org")
    assert mariam.get("/api/me/versions/1/pdf").status_code == 404  # LEGACY: no PDF
    assert mariam.get("/api/me/versions/1/proof.json").status_code == 404
    assert mariam.get("/api/me/versions/99/pdf").status_code == 404

    _award_new_version(db, "BTU-T-0002", _unheld_skill(db, "BTU-T-0002"))  # v3 PENDING
    body = mariam.get("/api/me/passport").json()
    assert body["issuing"] == {"version_no": 3} and body["current"]["version_no"] == 2
    v3 = mariam.get("/api/me/versions").json()[0]
    assert (v3["version_no"], v3["status"], v3["verification_code"]) == (3, "PENDING", None)
    assert mariam.get("/api/me/versions/3/pdf").status_code == 404


def test_newer_anchored_version_supersedes(issued: Session, run_jobs: RunJobs) -> None:
    db = issued
    _award_new_version(db, "BTU-T-0002", _unheld_skill(db, "BTU-T-0002"))
    run_jobs()
    mariam = _client(db, "btu-t-0002@example.org")
    body = mariam.get("/api/me/passport").json()
    assert body["current"]["version_no"] == 3 and len(body["skills"]) == 5
    versions = mariam.get("/api/me/versions").json()
    assert [(v["version_no"], v["superseded"]) for v in versions] == [
        (3, False),
        (2, True),
        (1, False),
    ]
    assert len(versions[0]["added_skills"]) == 1
    assert mariam.get("/api/me/versions/2/pdf").status_code == 200  # still the student's own


def test_skill_cards_come_from_the_current_version(issued: Session) -> None:
    db = issued
    skills = _client(db, "btu-t-0002@example.org").get("/api/me/passport").json()["skills"]
    content = _version(db, "BTU-AI-000126", 2).content_json or {}
    assert [s["name"] for s in skills] == [s["name"] for s in content["skills"]]
    first = skills[0]
    assert set(first) == {
        "name",
        "category",
        "badge_code",
        "stamp_sha256",
        "description",
        "date_earned",
        "source",
        "event_name",
    }
    assert first["source"] in ("SEED", "DIRECT", "EVENT")


def test_legacy_only_passport_shows_its_skills(db: Session) -> None:
    st, sk = f.student(db, 7), f.skill(db)
    award = f.award(db, st, sk)
    version = PassportVersion(
        passport_id="BTU-AI-000007",
        version_no=1,
        status="LEGACY",
        issued_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    db.add(version)
    db.flush()
    db.add(VersionAward(version_id=version.version_id, award_id=award.award_id))
    db.commit()
    body = _client(db, st.email).get("/api/me/passport").json()
    assert body["current"] is None and body["issuing"] is None
    assert [s["name"] for s in body["skills"]] == ["Skill SKL-001"]
    assert body["holder_name"] == "Nino Test"


def test_no_versions_yet(client_as: ClientAs) -> None:
    client = client_as("student")  # BTU-T-0001, passport row only
    body = client.get("/api/me/passport").json()
    assert body == {
        "passport_id": "BTU-AI-000001",
        "holder_name": "Nino Test",
        "first_issued_on": None,
        "current": None,
        "issuing": None,
        "skills": [],
    }
    assert client.get("/api/me/versions").json() == []


@pytest.mark.parametrize("role", ["admin", "unregistered", None])
def test_students_only(client_as: ClientAs, role: str | None) -> None:
    client = client_as(role)
    for url in ("/api/me/passport", "/api/me/versions", "/api/me/versions/1/pdf"):
        assert client.get(url).status_code == (401 if role is None else 403), url
