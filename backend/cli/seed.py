"""`python -m cli seed`: import the hackathon CSV (BE-04).

Idempotent: every insert is "insert if the natural key doesn't exist", so a second run
changes nothing and reports zeros.
"""

import csv
import hashlib
import uuid
from dataclasses import astuple, dataclass, fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.models import (
    AwardSubmission,
    Passport,
    PassportVersion,
    Skill,
    SkillAward,
    SkillCategory,
    Student,
    VersionAward,
)
from app.services import storage

SEED_CSV = REPO_ROOT / "seed" / "test-data.csv"
STAMPS_DIR = REPO_ROOT / "seed" / "stamps"
HEADER_LINE = 4  # lines 1-3 are a title block
EXPECTED_ROWS = 60
# One SEED submission owns every imported award; a fixed id keeps re-runs idempotent.
SEED_SUBMISSION_ID = uuid.uuid5(uuid.NAMESPACE_URL, "btu-passport:seed:test-data.csv")

EDUCATION_LEVELS = {"Bachelor's": "BACHELOR", "Master's": "MASTER", "Doctoral": "DOCTORAL"}
STATUSES = {"Active": "ACTIVE", "Graduate": "GRADUATE"}


@dataclass(frozen=True)
class SeedRow:
    student_id: str
    first_name: str
    last_name: str
    email: str
    program: str
    education_level: str
    passport_id: str
    first_issued: date
    status: str
    record_id: str
    skill_id: str
    skill_name: str
    category: str
    badge_code: str
    skill_description: str
    date_earned: date
    synced: bool
    synced_at: datetime | None


@dataclass(frozen=True)
class SeedCounts:
    students: int = 0
    passports: int = 0
    categories: int = 0
    skills: int = 0
    awards: int = 0
    legacy_versions: int = 0

    def __str__(self) -> str:
        return " / ".join(
            f"{f.name.replace('_', ' ')} {v}"
            for f, v in zip(fields(self), astuple(self), strict=True)
        )


def _synced_at(value: str) -> datetime | None:
    # '2026-10-17 10:00 UTC'
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M UTC").replace(tzinfo=UTC)


def parse_csv(path: Path) -> list[SeedRow]:
    """Data rows start after the header on line 4 and end at the first empty Record ID."""
    with path.open(newline="", encoding="utf-8") as fh:
        lines = list(csv.reader(fh))
    header = lines[HEADER_LINE - 1]
    rows: list[SeedRow] = []
    for raw in lines[HEADER_LINE:]:
        r = dict(zip(header, raw, strict=False))
        if not r.get("Record ID", "").strip():
            break
        rows.append(
            SeedRow(
                student_id=r["Student ID"].strip(),
                first_name=r["First Name"].strip(),
                last_name=r["Last Name"].strip(),
                email=r["BTU Email (Test)"].strip().lower(),
                program=r["Program"].strip(),
                education_level=EDUCATION_LEVELS[r["Education Level"].strip()],
                passport_id=r["Passport ID (Existing)"].strip(),
                first_issued=date.fromisoformat(r["First Issued (Existing)"].strip()),
                status=STATUSES[r["Student Status"].strip()],
                record_id=r["Record ID"].strip(),
                skill_id=r["Skill ID"].strip(),
                skill_name=r["Skill Name"].strip(),
                category=r["Skill Category"].strip(),
                badge_code=r["Badge/Stamp Code"].strip(),
                skill_description=r["Skill Description"].strip(),
                date_earned=date.fromisoformat(r["Date Earned"].strip()),
                synced=r["Passport Sync Status"].strip() == "SYNCED",
                synced_at=_synced_at(r["Synced At (UTC)"].strip()),
            )
        )
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(f"expected {EXPECTED_ROWS} data rows in {path.name}, found {len(rows)}")
    return rows


def _insert_new(db: Session, model: Any, values: list[dict[str, Any]], key: list[str]) -> int:
    """INSERT ... ON CONFLICT (key) DO NOTHING; returns how many rows were new."""
    if not values:
        return 0
    stmt = insert(model).values(values).on_conflict_do_nothing(index_elements=key)
    return len(db.execute(stmt.returning(*[getattr(model, k) for k in key])).all())


def _categories(db: Session, rows: list[SeedRow]) -> int:
    distinct = dict.fromkeys((r.category, r.badge_code) for r in rows)
    new = _insert_new(
        db, SkillCategory, [{"name": n, "badge_code": b} for n, b in distinct], ["badge_code"]
    )
    for category in db.scalars(select(SkillCategory).where(SkillCategory.stamp_sha256.is_(None))):
        stamp = STAMPS_DIR / f"{category.badge_code}.svg"
        if not stamp.is_file():
            continue
        data = stamp.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        key = f"stamps/{sha}.svg"
        storage.put_bytes(key, data, "image/svg+xml")
        category.stamp_sha256, category.stamp_key, category.stamp_mime = sha, key, "image/svg+xml"
    db.flush()
    return new


def run(db: Session) -> SeedCounts:
    rows = parse_csv(SEED_CSV)
    by_student = {r.student_id: r for r in rows}  # student fields are identical on every row

    categories = _categories(db, rows)
    category_ids = {c.name: c.category_id for c in db.scalars(select(SkillCategory))}

    skills = {
        r.skill_id: {
            "skill_id": r.skill_id,
            "name": r.skill_name,
            "category_id": category_ids[r.category],
            "description": r.skill_description,
        }
        for r in rows
    }
    new_skills = _insert_new(db, Skill, list(skills.values()), ["skill_id"])

    new_students = _insert_new(
        db,
        Student,
        [
            {
                "student_id": s.student_id,
                "first_name": s.first_name,
                "last_name": s.last_name,
                "email": s.email,
                "program": s.program,
                "education_level": s.education_level,
                "status": s.status,
            }
            for s in by_student.values()
        ],
        ["student_id"],
    )
    # The seed is the one place holder names and first_issued_on are set without an issued
    # version: the CSV says these passports already exist.
    new_passports = _insert_new(
        db,
        Passport,
        [
            {
                "passport_id": s.passport_id,
                "student_id": s.student_id,
                "holder_first_name": s.first_name,
                "holder_last_name": s.last_name,
                "first_issued_on": s.first_issued,
            }
            for s in by_student.values()
        ],
        ["passport_id"],
    )
    highest = max(int(s.passport_id.removeprefix("BTU-AI-")) for s in by_student.values())
    db.execute(
        text(
            "SELECT setval('passport_number_seq',"
            " GREATEST((SELECT last_value FROM passport_number_seq), :n), true)"
        ),
        {"n": highest},
    )

    _insert_new(
        db,
        AwardSubmission,
        [{"submission_id": SEED_SUBMISSION_ID, "kind": "SEED", "reason": "Hackathon seed import"}],
        ["submission_id"],
    )
    new_awards = _insert_new(
        db,
        SkillAward,
        [
            {
                "student_id": r.student_id,
                "skill_id": r.skill_id,
                "date_earned": r.date_earned,
                "submission_id": SEED_SUBMISSION_ID,
                "legacy_record_id": r.record_id,
            }
            for r in rows
        ],
        ["legacy_record_id"],
    )

    new_versions = _legacy_versions(db, rows)
    db.flush()
    return SeedCounts(
        students=new_students,
        passports=new_passports,
        categories=categories,
        skills=new_skills,
        awards=new_awards,
        legacy_versions=new_versions,
    )


def _legacy_versions(db: Session, rows: list[SeedRow]) -> int:
    """One LEGACY V1 per student with SYNCED rows (Requirements Q2 default)."""
    # DEFAULT(Q2): SYNCED rows become a LEGACY V1 with no PDF or code; not verifiable.
    synced: dict[str, list[SeedRow]] = {}
    for r in rows:
        if r.synced:
            synced.setdefault(r.passport_id, []).append(r)

    award_ids = {
        record_id: award_id
        for record_id, award_id in db.execute(
            select(SkillAward.legacy_record_id, SkillAward.award_id)
        )
    }
    created = 0
    for passport_id, synced_rows in synced.items():
        issued_at = max(r.synced_at for r in synced_rows if r.synced_at is not None)
        version_id = db.scalar(
            insert(PassportVersion)
            .values(passport_id=passport_id, version_no=1, status="LEGACY", issued_at=issued_at)
            .on_conflict_do_nothing(index_elements=["passport_id", "version_no"])
            .returning(PassportVersion.version_id)
        )
        if version_id is None:
            continue  # already seeded
        created += 1
        db.execute(
            insert(VersionAward).values(
                [
                    {"version_id": version_id, "award_id": award_ids[r.record_id]}
                    for r in synced_rows
                ]
            )
        )
        db.execute(
            update(Passport)
            .where(Passport.passport_id == passport_id, Passport.latest_version_id.is_(None))
            .values(latest_version_id=version_id)
        )
    return created


def main() -> None:
    from app.db import SessionLocal

    with SessionLocal() as db, db.begin():
        counts = run(db)
    print(f"seed: {counts}")
