"""Student portal reads (BE-47, FR-25): the signed-in student's own passport, its versions and
their downloads. Everything starts from the student's passport row; no route takes a student,
passport or version ID from the caller, so there is no other student's record to ask for (A8).
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Passport, PassportVersion, Student
from app.schemas.me import IssuingVersion, MyPassport, SkillOnPassport, VersionSummary
from app.services.content import version_skills

IN_PROGRESS = ("PENDING", "RENDERED", "ANCHORING")


def _passport(db: Session, student: Student) -> Passport:
    return db.scalars(select(Passport).where(Passport.student_id == student.student_id)).one()


def _versions(db: Session, passport_id: str) -> list[PassportVersion]:
    return list(
        db.scalars(
            select(PassportVersion)
            .where(PassportVersion.passport_id == passport_id)
            .order_by(PassportVersion.version_no.desc())
        )
    )


def _skills(db: Session, version: PassportVersion) -> list[dict[str, Any]]:
    """From the frozen snapshot once rendered; LEGACY and PENDING versions have none."""
    if version.content_json is not None:
        return list(version.content_json["skills"])
    return version_skills(db, version.version_id)


def _summaries(
    versions: list[PassportVersion], skills: dict[int, list[dict[str, Any]]]
) -> list[VersionSummary]:
    latest_anchored = max((v.version_no for v in versions if v.status == "ANCHORED"), default=0)
    by_no = {v.version_no: v for v in versions}
    out = []
    for v in versions:
        names = [s["name"] for s in skills[v.version_id]]
        before = by_no.get(v.version_no - 1)
        held = {s["name"] for s in skills[before.version_id]} if before else set()
        anchored = v.status == "ANCHORED"
        out.append(
            VersionSummary(
                version_no=v.version_no,
                status=v.status,
                issued_at=v.issued_at,
                verification_code=v.verification_code if anchored else None,
                skill_count=len(names),
                added_skills=[n for n in names if n not in held],
                superseded=anchored and v.version_no < latest_anchored,
            )
        )
    return out


def versions(db: Session, student: Student) -> list[VersionSummary]:
    """Newest first, LEGACY included."""
    rows = _versions(db, _passport(db, student).passport_id)
    return _summaries(rows, {v.version_id: _skills(db, v) for v in rows})


def _skill_card(s: dict[str, Any]) -> SkillOnPassport:
    source = s["source"]
    return SkillOnPassport(
        name=s["name"],
        category=s["category"],
        badge_code=s["badge_code"],
        stamp_sha256=s["stamp_sha256"],
        description=s["description"],
        date_earned=s["date_earned"],
        source=source["type"].upper(),
        event_name=source.get("event_name"),
    )


def passport(db: Session, student: Student) -> MyPassport:
    p = _passport(db, student)
    rows = _versions(db, p.passport_id)
    skills = {v.version_id: _skills(db, v) for v in rows}
    summaries = dict(zip((v.version_id for v in rows), _summaries(rows, skills), strict=True))

    current = next((v for v in rows if v.status == "ANCHORED"), None)
    current_no = current.version_no if current else 0
    issuing = next((v for v in rows if v.status in IN_PROGRESS and v.version_no > current_no), None)
    # The cards show what the current PDF shows; before any issued PDF, the legacy record's.
    shown = current or next((v for v in rows if v.status == "LEGACY"), None)

    if p.holder_first_name is not None:
        first, last = p.holder_first_name, p.holder_last_name or ""
    else:
        first, last = student.first_name, student.last_name
    return MyPassport(
        passport_id=p.passport_id,
        holder_name=f"{first} {last}",
        first_name=first,
        last_name=last,
        first_issued_on=p.first_issued_on,
        current=summaries[current.version_id] if current else None,
        issuing=IssuingVersion(version_no=issuing.version_no) if issuing else None,
        skills=[_skill_card(s) for s in skills[shown.version_id]] if shown else [],
    )


def anchored_version(db: Session, student: Student, version_no: int) -> PassportVersion:
    """One of the student's own ANCHORED versions; anything else is a 404 (A8)."""
    version = db.scalars(
        select(PassportVersion).where(
            PassportVersion.passport_id == _passport(db, student).passport_id,
            PassportVersion.version_no == version_no,
            PassportVersion.status == "ANCHORED",
        )
    ).one_or_none()
    if version is None or not version.pdf_key:
        raise AppError("not_found", "You have no issued passport version with this number.", 404)
    return version
