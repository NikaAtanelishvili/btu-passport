"""Skill catalog writes (BE-50, BE-51; FR-07, FR-34, FR-35). Issued passports never change:
their skills are frozen in passport_versions.content_json and their PDFs are stored bytes, so
a rename, a new stamp or an archive applies to future versions only. Anything awarded or used
by an event (even a deleted one) is archived, never deleted; the foreign keys back this up."""

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import exists, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Event, Skill, SkillAward, SkillCategory
from app.schemas.catalog import CategoryRef, SkillCreate, SkillPatch, SkillRow
from app.services import audit

if TYPE_CHECKING:
    from app.auth.deps import Principal

SKILL_NAME_MAX = 80
SKILL_DESCRIPTION_MAX = 300
SKILL_FIELDS = ("name", "category_id", "description")


def _next_id(db: Session, column: Any, prefix: str) -> str:
    """`prefix` + the next number, at least 3 digits (SKL-017, BDG-AI-004). The transaction
    lock makes two concurrent creates take different numbers."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"next-id:{prefix}"})
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    numbers = [int(m.group(1)) for v in db.scalars(select(column)) if (m := pattern.match(v))]
    return f"{prefix}{max(numbers, default=0) + 1:03d}"


def _times_awarded(db: Session, skill_id: str) -> int:
    stmt = select(func.count()).where(SkillAward.skill_id == skill_id)
    return db.scalar(stmt) or 0


def skill_row(db: Session, skill: Skill) -> SkillRow:
    category = db.get_one(SkillCategory, skill.category_id)
    return SkillRow(
        skill_id=skill.skill_id,
        name=skill.name,
        category=CategoryRef.model_validate(category, from_attributes=True),
        description=skill.description,
        times_awarded=_times_awarded(db, skill.skill_id),
        archived=skill.archived_at is not None,
    )


def _skill(db: Session, skill_id: str) -> Skill:
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise AppError("not_found", "No such skill.", 404)
    return skill


def _clean_skill(db: Session, values: dict[str, Any], own_id: str | None) -> dict[str, str]:
    """Normalise `values` in place; field errors, or a 409 for a name already in use."""
    fields: dict[str, str] = {}
    values["name"] = values["name"].strip()
    values["description"] = values["description"].strip()
    if not 1 <= len(values["name"]) <= SKILL_NAME_MAX:
        fields["name"] = f"Required, at most {SKILL_NAME_MAX} characters."
    if not 1 <= len(values["description"]) <= SKILL_DESCRIPTION_MAX:
        fields["description"] = f"Required, at most {SKILL_DESCRIPTION_MAX} characters."
    category = db.get(SkillCategory, values["category_id"])
    if category is None:
        fields["category_id"] = "Choose a category."
    elif category.archived_at is not None and own_id is None:
        fields["category_id"] = "This category is archived."
    if fields:
        return fields
    holder = db.scalar(
        select(Skill.skill_id).where(func.lower(Skill.name) == values["name"].lower())
    )
    if holder is not None and holder != own_id:
        raise _duplicate_name(holder)
    return fields


def _duplicate_name(holder: str) -> AppError:
    return AppError(
        "duplicate_name",
        "A skill with this name already exists.",
        409,
        {"name": f"Already used by {holder}."},
    )


def create_skill(db: Session, actor: "Principal", body: SkillCreate) -> Skill:
    values = body.model_dump()
    if fields := _clean_skill(db, values, None):
        raise AppError("validation_error", "Some fields are invalid.", 422, fields)
    skill = Skill(skill_id=_next_id(db, Skill.skill_id, "SKL-"), **values)
    db.add(skill)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:  # the same name, created concurrently
        raise _duplicate_name("another skill") from None
    audit.record(db, actor, "skill.create", "skill", skill.skill_id, after=values)
    db.flush()
    return skill


def update_skill(db: Session, actor: "Principal", skill_id: str, body: SkillPatch) -> Skill:
    skill = _skill(db, skill_id)
    values = {k: getattr(skill, k) for k in SKILL_FIELDS} | body.model_dump(exclude_none=True)
    category_changed = values["category_id"] != skill.category_id
    fields = _clean_skill(db, values, skill_id)
    if category_changed and "category_id" not in fields:
        category = db.get_one(SkillCategory, values["category_id"])
        if category.archived_at is not None:
            fields["category_id"] = "This category is archived."
    if fields:
        raise AppError("validation_error", "Some fields are invalid.", 422, fields)
    changed = [k for k in SKILL_FIELDS if values[k] != getattr(skill, k)]
    if changed:
        before = {k: getattr(skill, k) for k in changed}
        for k in changed:
            setattr(skill, k, values[k])
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            raise _duplicate_name("another skill") from None
        audit.record(
            db, actor, "skill.update", "skill", skill_id, before, {k: values[k] for k in changed}
        )
        db.flush()
    return skill


def set_skill_archived(db: Session, actor: "Principal", skill_id: str, archived: bool) -> Skill:
    """Archived skills leave the award and event forms; issued passports keep them."""
    skill = _skill(db, skill_id)
    if (skill.archived_at is not None) != archived:
        skill.archived_at = datetime.now(UTC) if archived else None
        action = "skill.archive" if archived else "skill.unarchive"
        audit.record(
            db, actor, action, "skill", skill_id, {"archived": not archived}, {"archived": archived}
        )
        db.flush()
    return skill


def _in_use(message: str) -> AppError:
    return AppError("in_use", message, 409)


def delete_skill(db: Session, actor: "Principal", skill_id: str) -> None:
    skill = _skill(db, skill_id)
    awarded = exists().where(SkillAward.skill_id == skill_id)
    in_event = exists().where(Event.skill_id == skill_id)  # deleted events included
    if db.scalar(select(awarded)) or db.scalar(select(in_event)):
        raise _in_use("This skill has been awarded or is used by an event; archive it instead.")
    before = {k: getattr(skill, k) for k in SKILL_FIELDS}
    db.delete(skill)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:  # awarded or used concurrently (the foreign keys refuse)
        raise _in_use("This skill is in use; archive it instead.") from None
    audit.record(db, actor, "skill.delete", "skill", skill_id, before=before)
    db.flush()
