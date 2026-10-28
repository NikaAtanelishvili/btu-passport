"""Students (BE-35): register with one passport (FR-02, FR-10), edit without touching what an
issued passport printed (FR-11), and the admin detail view."""

import re
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import (
    AwardSubmission,
    Event,
    EventParticipant,
    Passport,
    PassportVersion,
    Skill,
    SkillAward,
    SkillCategory,
    Student,
    User,
    passport_number_seq,
)
from app.models.base import EDUCATION_LEVELS, STUDENT_STATUSES
from app.schemas.student import (
    AwardRow,
    ParticipationRow,
    PassportInfo,
    StudentCreate,
    StudentDetail,
    StudentPatch,
    StudentProfile,
)
from app.schemas.version import version_row
from app.services import audit, events

if TYPE_CHECKING:
    from app.auth.deps import Principal

# DEFAULT(Q16): the Student ID format of the test data, BTU-T-0001.
STUDENT_ID_RE = re.compile(r"^BTU-T-\d{4,}$")
NAME_MAX = 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PROFILE_FIELDS = ("first_name", "last_name", "email", "program", "education_level", "status")


def clean_fields(values: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Normalise the given fields and check them; returns (values, field errors)."""
    out: dict[str, str] = {}
    fields: dict[str, str] = {}
    for name, raw in values.items():
        value = raw.strip()
        if name == "student_id":
            value = value.upper()
            if not STUDENT_ID_RE.match(value):
                fields[name] = "Use the BTU format, e.g. BTU-T-0001."
        elif name in ("first_name", "last_name"):
            if not 1 <= len(value) <= NAME_MAX:
                fields[name] = f"Required, at most {NAME_MAX} characters."
        elif name == "email":
            value = value.lower()
            domains = get_settings().allowed_email_domains
            if not EMAIL_RE.match(value):
                fields[name] = "Enter a valid email address."
            elif value.rpartition("@")[2] not in domains:
                fields[name] = "Use a BTU email address."
        elif name == "program":
            if not value:
                fields[name] = "Choose or type a program."
        elif name == "education_level":
            if value not in EDUCATION_LEVELS:
                fields[name] = "Choose Bachelor's, Master's or Doctoral."
        elif name == "status" and value not in STUDENT_STATUSES:
            fields[name] = "Choose Active or Graduate."
        out[name] = value
    return out, fields


def duplicate_error(db: Session, values: dict[str, str], own_id: str | None) -> AppError | None:
    if "student_id" in values and db.get(Student, values["student_id"]) is not None:
        return AppError(
            "duplicate_student_id",
            "A student with this Student ID already exists.",
            409,
            {"student_id": "This Student ID is already registered."},
        )
    if "email" in values:
        holder = db.scalar(select(Student.student_id).where(Student.email == values["email"]))
        if holder is not None and holder != own_id:
            return AppError(
                "duplicate_email",
                "A student with this email already exists.",
                409,
                {"email": f"Already used by {holder}."},
            )
    return None


def _flush_unique(db: Session, values: dict[str, str], own_id: str | None) -> None:
    """Flush, turning a UNIQUE violation from a concurrent request into the same 409."""
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        error = duplicate_error(db, values, own_id)
        raise error or AppError("conflict", "The student was changed concurrently.", 409) from None


def create_student(
    db: Session, actor: "Principal | None", body: StudentCreate, action: str = "student.create"
) -> Student:
    """FR-02/FR-10: the student and their one passport, with the next Passport ID. Frozen
    fields stay empty until the first version is issued (BE-02). `actor` None: the CLI or the
    Sheet sync (action `sheet.student.create`)."""
    values, fields = clean_fields(body.model_dump())
    if fields:
        raise AppError("validation_error", "Some fields are invalid.", 422, fields)
    if error := duplicate_error(db, values, None):
        raise error
    student = Student(**values)
    db.add(student)
    _flush_unique(db, values, None)
    passport_id = f"BTU-AI-{db.scalar(passport_number_seq.next_value()):06d}"
    db.add(Passport(passport_id=passport_id, student_id=student.student_id))
    db.flush()
    events.link_participants(db, student.student_id, student.email)  # Unregistered check-ins
    audit.record(
        db,
        actor,
        action,
        "student",
        student.student_id,
        after={**values, "passport_id": passport_id},
    )
    db.flush()
    return student


def update_student(
    db: Session, actor: "Principal", student_id: str, body: StudentPatch
) -> tuple[Student, list[str]]:
    """Profile edits. The passport row is never touched: names printed on an issued version
    stay as printed (trigger passport_frozen_fields), and a differing name is reported."""
    student = db.get(Student, student_id, with_for_update=True)
    if student is None:
        raise AppError("not_found", "No such student.", 404)
    given = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    values, fields = clean_fields(given)
    if fields:
        raise AppError("validation_error", "Some fields are invalid.", 422, fields)
    changed = {k: v for k, v in values.items() if getattr(student, k) != v}
    if error := duplicate_error(db, changed, student_id):
        raise error
    if changed:
        before = {k: getattr(student, k) for k in changed}
        for k, v in changed.items():
            setattr(student, k, v)
        _flush_unique(db, changed, student_id)
        if "email" in changed:
            events.link_participants(db, student_id, student.email)
        audit.record(db, actor, "student.update", "student", student_id, before, changed)
        db.flush()
    return student, _warnings(db, student)


def _warnings(db: Session, student: Student) -> list[str]:
    passport = _passport(db, student.student_id)
    if passport.first_issued_on is not None and (
        passport.holder_first_name != student.first_name
        or passport.holder_last_name != student.last_name
    ):
        return ["printed_name_differs"]
    return []


def _passport(db: Session, student_id: str) -> Passport:
    passport = db.scalar(select(Passport).where(Passport.student_id == student_id))
    if passport is None:  # every student is registered with one (FR-10)
        raise AppError("no_passport", f"{student_id} has no passport.", 409)
    return passport


def detail(db: Session, student_id: str, warnings: list[str] | None = None) -> StudentDetail:
    student = db.get(Student, student_id)
    if student is None:
        raise AppError("not_found", "No such student.", 404)
    passport = _passport(db, student_id)
    versions = db.scalars(
        select(PassportVersion)
        .where(PassportVersion.passport_id == passport.passport_id)
        .order_by(PassportVersion.version_no.desc())
    )
    return StudentDetail(
        profile=StudentProfile.model_validate(student, from_attributes=True),
        passport=PassportInfo(
            passport_id=passport.passport_id,
            first_issued_on=passport.first_issued_on,
            holder_first_name=passport.holder_first_name,
            holder_last_name=passport.holder_last_name,
            frozen=passport.first_issued_on is not None,
            versions=[version_row(v, student) for v in versions],
        ),
        awards=_awards(db, student_id),
        events=_events(db, student_id),
        warnings=warnings or [],
    )


def _awards(db: Session, student_id: str) -> list[AwardRow]:
    rows = db.execute(
        select(SkillAward, Skill, SkillCategory, AwardSubmission, Event.name, User.email)
        .join(Skill, Skill.skill_id == SkillAward.skill_id)
        .join(SkillCategory, SkillCategory.category_id == Skill.category_id)
        .join(AwardSubmission, AwardSubmission.submission_id == SkillAward.submission_id)
        .outerjoin(Event, Event.event_id == AwardSubmission.event_id)
        .outerjoin(User, User.user_id == AwardSubmission.submitted_by)
        .where(SkillAward.student_id == student_id)
        .order_by(SkillAward.date_earned, SkillAward.award_id)
    ).all()
    return [
        AwardRow(
            award_id=award.award_id,
            skill_id=skill.skill_id,
            skill_name=skill.name,
            category=category.name,
            stamp_sha256=category.stamp_sha256,
            date_earned=award.date_earned,
            source=submission.kind,
            submission_id=submission.submission_id,
            event_id=submission.event_id,
            event_name=event_name,
            source_record_id=award.source_record_id,
            reason=submission.reason,
            awarded_by=awarded_by,
        )
        for award, skill, category, submission, event_name, awarded_by in rows
    ]


def _events(db: Session, student_id: str) -> list[ParticipationRow]:
    rows = db.execute(
        select(EventParticipant, Event)
        .join(Event, Event.event_id == EventParticipant.event_id)
        .where(EventParticipant.student_id == student_id)
        .order_by(Event.starts_at.desc())
    ).all()
    return [
        ParticipationRow(
            event_id=event.event_id,
            event_name=event.name,
            starts_at=event.starts_at,
            event_status=event.status,
            event_deleted=event.deleted_at is not None,
            checked_in_at=p.checked_in_at,
            method=p.method,
            removed=p.removed_at is not None,
        )
        for p, event in rows
    ]
