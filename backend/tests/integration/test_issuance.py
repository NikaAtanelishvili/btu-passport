"""BE-23: issuance service — the one place versions are made."""

import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AnchorBatch,
    Job,
    Passport,
    PassportVersion,
    Skill,
    SkillAward,
    Student,
    VersionAward,
)
from app.services import issuance, storage
from tests import factories as f
from tests.conftest import FakeSigner

ClientAs = Callable[[str | None], TestClient]
RunJobs = Callable[[], int]


def _versions(db: Session, passport_id: str) -> list[PassportVersion]:
    return list(
        db.scalars(
            select(PassportVersion)
            .where(PassportVersion.passport_id == passport_id)
            .order_by(PassportVersion.version_no)
        )
    )


def _award_ids(db: Session, version_id: int) -> set[int]:
    return set(
        db.scalars(select(VersionAward.award_id).where(VersionAward.version_id == version_id))
    )


def test_first_version_is_1_and_holds_all_awards(db: Session) -> None:
    st = f.student(db, 1)
    a1, a2 = f.award(db, st, f.skill(db, "SKL-001")), f.award(db, st, f.skill(db, "SKL-002"))
    [made] = issuance.create_versions(db, [st.student_id])
    version = db.get(PassportVersion, made.version_id)
    assert version is not None
    assert (made.student_id, made.version_no, version.status) == ("BTU-T-0001", 1, "PENDING")
    assert version.passport_id == "BTU-AI-000001"
    assert _award_ids(db, version.version_id) == {a1.award_id, a2.award_id}


def test_version_number_is_highest_plus_one(db: Session) -> None:
    st = f.student(db, 1)
    f.award(db, st, f.skill(db))
    first = issuance.create_versions(db, [st.student_id])
    second = issuance.create_versions(db, [st.student_id])
    assert [first[0].version_no, second[0].version_no] == [1, 2]


def test_each_version_enqueues_one_issue_job(db: Session) -> None:
    sts = [f.student(db, n) for n in (3, 1, 2)]
    sk = f.skill(db)
    for st in sts:
        f.award(db, st, sk)
    made = issuance.create_versions(db, [st.student_id for st in sts])
    assert [m.student_id for m in made] == ["BTU-T-0001", "BTU-T-0002", "BTU-T-0003"]  # lock order
    jobs = db.scalars(select(Job).order_by(Job.job_id)).all()
    assert [(j.type, j.payload) for j in jobs] == [
        ("ISSUE_VERSION", {"version_id": m.version_id}) for m in made
    ]


def test_issue_pending_on_the_seed_makes_18_versions(seeded: Session) -> None:
    db = seeded
    assert issuance.issue_pending(db) == 18
    assert db.scalar(select(func.count()).where(PassportVersion.status == "PENDING")) == 18
    assert issuance.issue_pending(db) == 0  # nothing left out of a latest version


def test_issue_pending_legacy_student_gets_v2_with_all_awards(seeded: Session) -> None:
    db = seeded
    issuance.issue_pending(db)
    v1, v2 = _versions(db, "BTU-AI-000126")  # BTU-T-0002, legacy V1
    assert (v1.version_no, v1.status, v2.version_no, v2.status) == (1, "LEGACY", 2, "PENDING")
    all_awards = set(
        db.scalars(select(SkillAward.award_id).where(SkillAward.student_id == "BTU-T-0002"))
    )
    assert len(all_awards) == 4 and _award_ids(db, v2.version_id) == all_awards
    assert len(_award_ids(db, v1.version_id)) == 2  # the legacy version is untouched
    passport = db.get(Passport, "BTU-AI-000126")
    assert passport is not None and passport.latest_version_id == v1.version_id  # until anchored


def test_issue_pending_unsynced_student_gets_v1(seeded: Session) -> None:
    db = seeded
    issuance.issue_pending(db)
    [v1] = _versions(db, "BTU-AI-000139")  # BTU-T-0021, never issued
    assert (v1.version_no, v1.status) == (1, "PENDING")


# --- Acceptance scenarios (Infra tab §4), API/CLI + worker with the fake signer ----------


def _post_award(client: Any, student_ids: list[str], skill_id: str) -> Any:
    body = {
        "student_ids": student_ids,
        "skill_id": skill_id,
        "date_earned": "2026-10-20",
        "reason": "Workshop completed",
    }
    r = client.post("/api/admin/awards", json=body, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 202, r.text
    return r.json()


def test_A1_additional_award(
    seeded: Session, client_as: ClientAs, fake_signer: FakeSigner, run_jobs: RunJobs
) -> None:
    """BTU-T-0021 (passport BTU-AI-000139, never issued) gets an extra award: V1 with both
    skills, one PDF in storage, anchored."""
    db = seeded
    body = _post_award(client_as("admin"), ["BTU-T-0021"], "SKL-001")
    [v] = body["versions"]
    run_jobs()
    db.expire_all()
    version = db.get_one(PassportVersion, v["version_id"])
    assert (version.passport_id, version.version_no, version.status) == (
        "BTU-AI-000139",
        1,
        "ANCHORED",
    )
    assert version.content_json is not None
    assert sorted(s["skill_id"] for s in version.content_json["skills"]) == ["SKL-001", "SKL-002"]
    assert version.pdf_key and storage.exists(version.pdf_key)
    assert len(fake_signer.calls) == 1
    assert db.get_one(Passport, "BTU-AI-000139").latest_version_id == version.version_id


def test_A2_issue_pending_one_version(
    seeded: Session, fake_signer: FakeSigner, run_jobs: RunJobs
) -> None:
    """BTU-T-0002 at legacy V1 with 2 unsynced awards: one new version, same Passport ID,
    skills in date order."""
    db = seeded
    issuance.issue_pending(db)
    db.commit()
    run_jobs()
    db.expire_all()
    versions = _versions(db, "BTU-AI-000126")
    assert [(v.version_no, v.status) for v in versions] == [(1, "LEGACY"), (2, "ANCHORED")]
    content = versions[1].content_json
    assert content is not None and content["passport_id"] == "BTU-AI-000126"
    dates = [s["date_earned"] for s in content["skills"]]
    assert len(dates) == 4 and dates == sorted(dates)
    assert db.get_one(Passport, "BTU-AI-000126").latest_version_id == versions[1].version_id
    assert db.scalar(select(func.count()).where(PassportVersion.status == "ANCHORED")) == 18
    assert len(fake_signer.calls) == 1  # all 18 in one batch


def test_A10_bulk_one_batch(
    seeded: Session, client_as: ClientAs, fake_signer: FakeSigner, run_jobs: RunJobs
) -> None:
    """A newly created skill awarded to all 18 seed students: 18 versions, one Merkle batch."""
    db = seeded
    sk = Skill(skill_id="SKL-017", name="AI Agents", category_id=1, description="Agents.")
    db.add(sk)
    db.commit()
    students = list(db.scalars(select(Student.student_id).order_by(Student.student_id)))
    body = _post_award(client_as("admin"), students, "SKL-017")
    assert len(body["versions"]) == 18 and body["skipped"] == []
    run_jobs()
    db.expire_all()
    batches = db.scalars(select(AnchorBatch)).all()
    assert [(b.leaf_count, b.status) for b in batches] == [(18, "ANCHORED")]
    assert fake_signer.calls == [(batches[0].merkle_root, 18)]
