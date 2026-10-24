"""BE-25: the content snapshot frozen into content_json and rendered into the PDF."""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Passport, PassportVersion, SkillAward
from app.services import content, issuance
from tests import factories as f

ISSUED = datetime(2026, 10, 22, 15, 40, 12, 345678, tzinfo=UTC)


def _new_version(db: Session, student_id: str) -> PassportVersion:
    [made] = issuance.create_versions(db, [student_id])
    version = db.get(PassportVersion, made.version_id)
    assert version is not None
    return version


def test_snapshot_shape_for_a_seeded_legacy_student(seeded: Session) -> None:
    version = _new_version(seeded, "BTU-T-0002")
    c = content.build_content(seeded, version, verification_code="K7QM3XWP9D", issued_at=ISSUED)
    assert c["schema"] == "btu-ai-passport/1"
    assert (c["passport_id"], c["version_no"]) == ("BTU-AI-000126", 2)
    assert c["holder"] == {"first_name": "Mariam", "last_name": "Beridze"}
    assert c["first_issued_on"] == "2026-09-15"
    assert c["issued_at"] == "2026-10-22T15:40:12Z"
    assert c["verification_code"] == "K7QM3XWP9D"
    assert c["verify_url"] == "http://localhost:3000/v/K7QM3XWP9D"
    assert c["issuer"]["chain_id"] == 31337 and c["issuer"]["contract_address"].startswith("0x")
    assert c["issuer"]["name"] == "Business and Technology University"
    skill = c["skills"][0]
    assert set(skill) == {
        "skill_id",
        "name",
        "category",
        "badge_code",
        "stamp_sha256",
        "description",
        "date_earned",
        "source",
    }
    assert skill["source"] == {"type": "seed"}
    assert len(skill["stamp_sha256"]) == 64


def test_skills_sorted_by_date_earned_then_award_id(seeded: Session) -> None:
    version = _new_version(seeded, "BTU-T-0002")
    c = content.build_content(seeded, version, verification_code="K7QM3XWP9D", issued_at=ISSUED)
    awards = seeded.scalars(select(SkillAward).where(SkillAward.student_id == "BTU-T-0002"))
    expected = [a.skill_id for a in sorted(awards, key=lambda a: (a.date_earned, a.award_id))]
    assert [s["skill_id"] for s in c["skills"]] == expected
    dates = [s["date_earned"] for s in c["skills"]]
    assert dates == sorted(dates) and len(dates) == 4


def test_only_the_versions_own_awards_are_included(db: Session) -> None:
    st = f.student(db, 1)
    f.award(db, st, f.skill(db, "SKL-001"))
    version = _new_version(db, st.student_id)
    f.award(db, st, f.skill(db, "SKL-002"))  # after the version was made
    c = content.build_content(db, version, verification_code="K7QM3XWP9D", issued_at=ISSUED)
    assert [s["skill_id"] for s in c["skills"]] == ["SKL-001"]


def test_first_issue_freezes_holder_names_and_date(db: Session) -> None:
    st = f.student(db, 1)  # passport without holder names or first_issued_on
    f.award(db, st, f.skill(db))
    version = _new_version(db, st.student_id)
    c = content.build_content(db, version, verification_code="K7QM3XWP9D", issued_at=ISSUED)
    passport = db.get(Passport, "BTU-AI-000001")
    assert passport is not None
    assert (passport.holder_first_name, passport.holder_last_name) == ("Nino", "Test")
    assert passport.first_issued_on == date(2026, 10, 22)  # issue day in Asia/Tbilisi
    assert c["holder"] == {"first_name": "Nino", "last_name": "Test"}
    assert c["first_issued_on"] == "2026-10-22"


def test_later_name_change_does_not_touch_the_passport(db: Session) -> None:
    st = f.student(db, 1, holder=True)
    f.award(db, st, f.skill(db))
    st.first_name = "Nina"
    version = _new_version(db, st.student_id)
    c = content.build_content(db, version, verification_code="K7QM3XWP9D", issued_at=ISSUED)
    assert c["holder"]["first_name"] == "Nino"  # frozen at first issue (FR-11)
