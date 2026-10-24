"""Issuance (BE-23): direct awards and `create_versions`, the one place versions are made
(direct awards, events, seed).

Deviation from FR-04: "date earned not before the first-issued date" is not checked, because
an event can happen before a student is registered.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import (
    AwardSubmission,
    Passport,
    PassportVersion,
    Skill,
    SkillAward,
    Student,
    VersionAward,
)
from app.schemas.award import AwardIn, AwardOut, CreatedVersion, PreviewRow
from app.services import audit, jobs

if TYPE_CHECKING:
    from app.auth.deps import Principal

REASON_MAX = 300


@dataclass(frozen=True)
class NewVersion:
    student_id: str
    version_id: int
    version_no: int


def today() -> date:
    """'Today' in TIMEZONE (default Asia/Tbilisi), for date checks."""
    return datetime.now(ZoneInfo(get_settings().timezone)).date()


def _validate(db: Session, body: AwardIn) -> tuple[list[Student], Skill]:
    """All field errors at once; 422 and nothing saved if any."""
    fields: dict[str, str] = {}
    ids = sorted({s.strip() for s in body.student_ids if s.strip()})
    students = list(db.scalars(select(Student).where(Student.student_id.in_(ids))))
    if not ids:
        fields["student_ids"] = "Choose at least one student."
    elif missing := sorted(set(ids) - {s.student_id for s in students}):
        fields["student_ids"] = f"Unknown student: {', '.join(missing)}."
    skill = db.get(Skill, body.skill_id)
    if skill is None:
        fields["skill_id"] = "Unknown skill."
    elif skill.archived_at is not None:
        fields["skill_id"] = "This skill is archived."
    if body.date_earned > today():
        fields["date_earned"] = "Date earned can't be in the future."
    if not 1 <= len(body.reason.strip()) <= REASON_MAX:
        fields["reason"] = f"Give a reason of 1 to {REASON_MAX} characters."
    if fields:
        raise AppError("validation_error", "Some fields are invalid.", 422, fields)
    assert skill is not None
    return sorted(students, key=lambda s: s.student_id), skill


def _holders(db: Session, student_ids: list[str], skill_id: str) -> set[str]:
    return set(
        db.scalars(
            select(SkillAward.student_id).where(
                SkillAward.skill_id == skill_id, SkillAward.student_id.in_(student_ids)
            )
        )
    )


def _highest_version_no(db: Session, passport_id: str) -> int:
    stmt = select(func.max(PassportVersion.version_no)).where(
        PassportVersion.passport_id == passport_id
    )
    return db.scalar(stmt) or 0


def preview_award(db: Session, body: AwardIn) -> list[PreviewRow]:
    """What a direct award would do, per student. No writes."""
    students, skill = _validate(db, body)
    holders = _holders(db, [s.student_id for s in students], skill.skill_id)
    pairs = db.execute(
        select(Passport.student_id, Passport.passport_id).where(
            Passport.student_id.in_([s.student_id for s in students])
        )
    )
    passports = {student_id: passport_id for student_id, passport_id in pairs}
    rows = []
    for s in students:
        name = f"{s.first_name} {s.last_name}"
        if s.student_id in holders:
            rows.append(PreviewRow(student_id=s.student_id, name=name, result="SKIP_ALREADY_HELD"))
            continue
        highest = _highest_version_no(db, passports[s.student_id])
        rows.append(
            PreviewRow(
                student_id=s.student_id,
                name=name,
                result="NEW_VERSION",
                from_version=highest or None,
                to_version=highest + 1,
            )
        )
    return rows


def create_direct_award(
    db: Session, actor: "Principal", body: AwardIn, idempotency_key: uuid.UUID
) -> dict[str, Any]:
    """FR-03/FR-13: one submission, one award per student who lacks the skill, one new
    version each. A repeated Idempotency-Key returns the stored response (A3)."""
    key = str(idempotency_key)
    stored = _stored_response(db, key)
    if stored is not None:
        return stored
    students, skill = _validate(db, body)

    # A concurrent request with the same key blocks here until it commits, then we replay it.
    submission_id = db.scalar(
        insert(AwardSubmission)
        .values(
            submission_id=uuid.uuid4(),
            kind="DIRECT",
            idempotency_key=key,
            reason=body.reason.strip(),
            submitted_by=actor.user.user_id,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(AwardSubmission.submission_id)
    )
    if submission_id is None:
        replay = _stored_response(db, key)
        assert replay is not None
        return replay

    holders = _holders(db, [s.student_id for s in students], skill.skill_id)
    awarded = []
    for s in students:
        if s.student_id in holders:
            continue
        award_id = db.scalar(
            insert(SkillAward)
            .values(
                student_id=s.student_id,
                skill_id=skill.skill_id,
                date_earned=body.date_earned,
                submission_id=submission_id,
            )
            .on_conflict_do_nothing(index_elements=["student_id", "skill_id"])
            .returning(SkillAward.award_id)
        )
        if award_id is not None:  # None: awarded concurrently by someone else
            awarded.append(s.student_id)

    created = create_versions(db, awarded)
    response = AwardOut(
        submission_id=submission_id,
        versions=[CreatedVersion(**v.__dict__) for v in created],
        skipped=[s.student_id for s in students if s.student_id not in awarded],
    ).model_dump(mode="json")
    submission = db.get(AwardSubmission, submission_id)
    assert submission is not None
    submission.response_json = response
    audit.record(
        db,
        actor,
        "award.direct",
        "award_submission",
        str(submission_id),
        after={
            "skill_id": skill.skill_id,
            "date_earned": body.date_earned.isoformat(),
            "reason": body.reason.strip(),
            **response,
        },
    )
    db.flush()
    return response


def _stored_response(db: Session, key: str) -> dict[str, Any] | None:
    return db.scalar(
        select(AwardSubmission.response_json).where(AwardSubmission.idempotency_key == key)
    )


def create_versions(db: Session, student_ids: list[str]) -> list[NewVersion]:
    """A PENDING version per student holding all their awards at this moment, plus an
    ISSUE_VERSION job each. Students are processed by ID so locks are always taken in the
    same order (no deadlocks); the passport row lock serialises version numbers, and
    UNIQUE (passport_id, version_no) backs it up."""
    created = []
    for student_id in sorted(set(student_ids)):
        passport = db.scalars(
            select(Passport).where(Passport.student_id == student_id).with_for_update()
        ).one_or_none()
        if passport is None:
            raise AppError("no_passport", f"{student_id} has no passport.", 409)
        version = PassportVersion(
            passport_id=passport.passport_id,
            version_no=_highest_version_no(db, passport.passport_id) + 1,
            status="PENDING",
        )
        db.add(version)
        db.flush()
        award_ids = db.scalars(
            select(SkillAward.award_id).where(SkillAward.student_id == student_id)
        )
        db.add_all(VersionAward(version_id=version.version_id, award_id=a) for a in award_ids)
        jobs.enqueue(db, "ISSUE_VERSION", {"version_id": version.version_id})
        created.append(NewVersion(student_id, version.version_id, version.version_no))
    db.flush()
    return created


# Students with an award that isn't in their highest-numbered version (of any status).
_PENDING_STUDENTS = text("""
    SELECT p.student_id FROM passports p
    WHERE EXISTS (
      SELECT 1 FROM skill_awards a
      WHERE a.student_id = p.student_id AND NOT EXISTS (
        SELECT 1 FROM version_awards va JOIN passport_versions v USING (version_id)
        WHERE va.award_id = a.award_id AND v.passport_id = p.passport_id
          AND v.version_no = (SELECT max(version_no) FROM passport_versions
                              WHERE passport_id = p.passport_id)))
    ORDER BY p.student_id
""")


def issue_pending(db: Session) -> int:
    """`python -m cli issue-pending` (BE-04 step 8): a new version for every student whose
    awards aren't all in their latest version. Re-running creates nothing new."""
    return len(create_versions(db, list(db.scalars(_PENDING_STUDENTS))))


def retry_version(db: Session, actor: "Principal", version_id: int) -> PassportVersion:
    """BE-29: a FAILED version goes back to RENDERED if it has a PDF (the next anchor tick
    re-batches it), otherwise to PENDING with a new ISSUE_VERSION job."""
    version = db.get(PassportVersion, version_id, with_for_update=True)
    if version is None:
        raise AppError("not_found", "No such version.", 404)
    if version.status != "FAILED":
        raise AppError("not_failed", "Only failed versions can be retried.", 409)
    before = {"status": version.status, "error": version.error}
    version.error = None
    if version.pdf_sha256:
        version.status = "RENDERED"
        version.batch_id = None
        version.merkle_proof = None
    else:
        version.status = "PENDING"
        jobs.enqueue(db, "ISSUE_VERSION", {"version_id": version.version_id})
    audit.record(
        db,
        actor,
        "version.retry",
        "passport_version",
        str(version.version_id),
        before=before,
        after={"status": version.status},
    )
    db.flush()
    return version


def retry_failed(db: Session, actor: "Principal") -> int:
    failed = db.scalars(
        select(PassportVersion.version_id)
        .where(PassportVersion.status == "FAILED")
        .order_by(PassportVersion.version_id)
    ).all()
    for version_id in failed:
        retry_version(db, actor, version_id)
    return len(failed)
