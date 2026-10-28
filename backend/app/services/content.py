"""The content snapshot (BE-25): the JSON stored in passport_versions.content_json and the only
input to the PDF renderer, so an issued version can always be explained from its row.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AwardSubmission,
    Event,
    Passport,
    PassportVersion,
    Skill,
    SkillAward,
    SkillCategory,
    Student,
    VersionAward,
)

SCHEMA = "btu-ai-passport/2"  # /2: direct awards carry their reason (the PDF shows it)
ISSUER_NAME = "Business and Technology University"


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def _source(
    kind: str, event_name: str | None, reason: str | None, earned_through: str | None
) -> dict[str, str]:
    if kind == "EVENT":
        return {"type": "event", "event_name": event_name or ""}
    if kind == "DIRECT" and reason:
        return {"type": "direct", "reason": reason}
    if kind == "SHEET" and earned_through:
        return {"type": "sheet", "earned_through": earned_through}
    return {"type": kind.lower()}  # "direct" | "seed" | "sheet"


def version_skills(db: Session, version_id: int) -> list[dict[str, Any]]:
    """The version's own awards as content skills, by date earned then award ID. Also used for
    LEGACY versions, which have no content snapshot (BE-47)."""
    rows = db.execute(
        select(
            SkillAward,
            Skill,
            SkillCategory,
            AwardSubmission.kind,
            Event.name,
            AwardSubmission.reason,
        )
        .join(VersionAward, VersionAward.award_id == SkillAward.award_id)
        .join(Skill, Skill.skill_id == SkillAward.skill_id)
        .join(SkillCategory, SkillCategory.category_id == Skill.category_id)
        .join(AwardSubmission, AwardSubmission.submission_id == SkillAward.submission_id)
        .outerjoin(Event, Event.event_id == AwardSubmission.event_id)
        .where(VersionAward.version_id == version_id)
        .order_by(SkillAward.date_earned, SkillAward.award_id)
    ).all()
    return [
        {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "category": category.name,
            "badge_code": category.badge_code,
            "stamp_sha256": category.stamp_sha256,
            "description": skill.description,
            "date_earned": award.date_earned.isoformat(),
            "source": _source(kind, event_name, reason, award.earned_through),
        }
        for award, skill, category, kind, event_name, reason in rows
    ]


def build_content(
    db: Session, version: PassportVersion, *, verification_code: str, issued_at: datetime
) -> dict[str, Any]:
    """Freeze the passport's holder fields on first issue (same transaction; the trigger then
    keeps them), and snapshot the version's own awards, by date earned then award ID."""
    s = get_settings()
    passport = db.scalars(
        select(Passport).where(Passport.passport_id == version.passport_id).with_for_update()
    ).one()
    if passport.first_issued_on is None:
        student = db.get(Student, passport.student_id)
        assert student is not None
        passport.holder_first_name = student.first_name
        passport.holder_last_name = student.last_name
        passport.first_issued_on = issued_at.astimezone(ZoneInfo(s.timezone)).date()
        db.flush()

    return {
        "schema": SCHEMA,
        "passport_id": passport.passport_id,
        "version_no": version.version_no,
        "holder": {
            "first_name": passport.holder_first_name,
            "last_name": passport.holder_last_name,
        },
        "first_issued_on": passport.first_issued_on.isoformat()
        if passport.first_issued_on
        else None,
        "issued_at": iso_utc(issued_at),
        "verification_code": verification_code,
        "verify_url": f"{s.public_base_url.rstrip('/')}/v/{verification_code}",
        "skills": version_skills(db, version.version_id),
        "issuer": {
            "name": ISSUER_NAME,
            "chain_id": s.chain_id,
            "contract_address": s.contract_address,
            "issuer_address": s.issuer_address,
        },
    }
