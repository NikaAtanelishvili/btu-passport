"""BE-23: issuance service — the one place versions are made."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Job, Passport, PassportVersion, SkillAward, VersionAward
from app.services import issuance
from tests import factories as f


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
