"""Student notices (SH-10): when a version is anchored, email the student about its new skills.

Queued as a NOTIFY_VERSION job in the anchoring transaction, sent by the worker, so SMTP never
holds up or rolls back anchoring. A version gets at most one notice. No notice when the version
adds no skill (a new student's empty V1) or only seed imports (the seeded students' first issued
versions: BTU's earlier records, not news to the student).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AwardSubmission, Passport, PassportVersion, SkillAward, Student, VersionAward
from app.services import jobs, mailer


def _award_ids(db: Session, version_id: int) -> set[int]:
    return set(
        db.scalars(select(VersionAward.award_id).where(VersionAward.version_id == version_id))
    )


def added_awards(db: Session, version: PassportVersion) -> list[tuple[SkillAward, str]]:
    """Awards in this version that weren't in the version before it, with their source kind."""
    previous = db.scalar(
        select(PassportVersion.version_id).where(
            PassportVersion.passport_id == version.passport_id,
            PassportVersion.version_no == version.version_no - 1,
        )
    )
    new = _award_ids(db, version.version_id) - (_award_ids(db, previous) if previous else set())
    if not new:
        return []
    rows = db.execute(
        select(SkillAward, AwardSubmission.kind)
        .join(AwardSubmission, AwardSubmission.submission_id == SkillAward.submission_id)
        .where(SkillAward.award_id.in_(new))
        .order_by(SkillAward.date_earned, SkillAward.award_id)
    )
    return [(award, kind) for award, kind in rows]


def enqueue_if_due(db: Session, version: PassportVersion) -> int | None:
    """In the caller's (anchoring) transaction."""
    added = added_awards(db, version)
    if not added or all(kind == "SEED" for _, kind in added):
        return None
    return jobs.enqueue(
        db,
        "NOTIFY_VERSION",
        {"version_id": version.version_id},
        dedupe_key=f"notify:{version.version_id}",
        max_attempts=3,
    )


def send(db: Session, version_id: int) -> None:
    """The NOTIFY_VERSION job. Skill names come from the version's frozen content."""
    version = db.get_one(PassportVersion, version_id)
    passport = db.get_one(Passport, version.passport_id)
    student = db.get_one(Student, passport.student_id)
    added = {award.skill_id for award, _ in added_awards(db, version)}
    skills = [
        s["name"] for s in (version.content_json or {}).get("skills", []) if s["skill_id"] in added
    ]
    mailer.send_version_notice(
        email=student.email,
        first_name=passport.holder_first_name or student.first_name,
        passport_id=passport.passport_id,
        version_no=version.version_no,
        skills=skills,
        url=f"{get_settings().public_base_url.rstrip('/')}/me",
    )
