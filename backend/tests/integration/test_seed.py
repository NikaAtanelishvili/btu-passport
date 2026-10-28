"""BE-04: `python -m cli seed` against the real CSV, Postgres and MinIO."""

import hashlib
from datetime import UTC, date, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Passport, PassportVersion, SkillAward, SkillCategory, VersionAward
from app.services import storage
from cli import seed

EXPECTED = seed.SeedCounts(
    students=18, passports=18, categories=3, skills=16, awards=60, legacy_versions=8
)


def test_fresh_seed_counts(db: Session, s3_bucket: str) -> None:
    assert seed.run(db) == EXPECTED
    for model, n in [(Passport, 18), (SkillAward, 60), (PassportVersion, 8)]:
        assert db.scalar(select(func.count()).select_from(model)) == n


def test_second_run_changes_nothing(db: Session, s3_bucket: str) -> None:
    seed.run(db)
    db.commit()
    assert seed.run(db) == seed.SeedCounts()


def test_legacy_version_holds_only_synced_awards(db: Session, s3_bucket: str) -> None:
    seed.run(db)
    passport = db.get(Passport, "BTU-AI-000126")  # Mariam Beridze, BTU-T-0002
    assert passport is not None and passport.latest_version_id is not None
    v1 = db.get(PassportVersion, passport.latest_version_id)
    assert v1 is not None
    assert (v1.version_no, v1.status, v1.pdf_sha256, v1.verification_code) == (
        1,
        "LEGACY",
        None,
        None,
    )
    assert v1.issued_at == datetime(2026, 10, 17, 10, 0, tzinfo=UTC)
    records = db.scalars(
        select(SkillAward.source_record_id)
        .join(VersionAward, VersionAward.award_id == SkillAward.award_id)
        .where(VersionAward.version_id == v1.version_id)
    ).all()
    assert sorted(str(r) for r in records) == ["REC-0002", "REC-0016"]


def test_unsynced_student_has_passport_but_no_version(db: Session, s3_bucket: str) -> None:
    seed.run(db)
    passport = db.get(Passport, "BTU-AI-000139")  # Luka Japaridze, BTU-T-0021 (A1)
    assert passport is not None
    assert passport.latest_version_id is None
    assert (passport.holder_first_name, passport.holder_last_name) == ("Luka", "Japaridze")
    assert passport.first_issued_on == date(2026, 10, 17)


def test_next_passport_number_follows_the_seed(db: Session, s3_bucket: str) -> None:
    seed.run(db)
    seed.run(db)
    assert db.scalar(text("SELECT nextval('passport_number_seq')")) == 143


def test_the_designed_stamps_are_uploaded_by_hash(db: Session, s3_bucket: str) -> None:
    seed.run(db)
    files = {
        "AI Skill": "stamp-ai-skill.png",  # red triangle
        "AI Applied Skill": "stamp-ai-applied.png",  # purple banner
        "AI Advanced Skill": "stamp-ai-advanced.png",  # navy circle
    }
    categories = list(db.scalars(select(SkillCategory)))
    assert {c.name for c in categories} == set(files)
    for category in categories:
        data = (seed.STAMPS_DIR / files[category.name]).read_bytes()
        assert category.stamp_sha256 == hashlib.sha256(data).hexdigest()
        assert category.stamp_key == f"stamps/{category.stamp_sha256}.png"
        assert category.stamp_mime == "image/png"
        assert storage.get(category.stamp_key) == data
