"""Skills: both admin roles read (award and event forms); writes are super admin only (BE-50)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import SuperAdminUser
from app.db import get_db
from app.models import Skill, SkillAward, SkillCategory
from app.schemas.catalog import CategoryRef, SkillCreate, SkillPatch, SkillRow
from app.services import catalog

router = APIRouter(tags=["admin: catalog"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/skills", response_model=list[SkillRow])
def list_skills(db: DB, include_archived: bool = False) -> list[SkillRow]:
    awarded = (
        select(SkillAward.skill_id, func.count().label("n"))
        .group_by(SkillAward.skill_id)
        .subquery()
    )
    stmt = (
        select(Skill, SkillCategory, func.coalesce(awarded.c.n, 0))
        .join(SkillCategory, SkillCategory.category_id == Skill.category_id)
        .outerjoin(awarded, awarded.c.skill_id == Skill.skill_id)
        .order_by(Skill.skill_id)
    )
    if not include_archived:
        stmt = stmt.where(Skill.archived_at.is_(None))
    return [
        SkillRow(
            skill_id=skill.skill_id,
            name=skill.name,
            category=CategoryRef.model_validate(category, from_attributes=True),
            description=skill.description,
            times_awarded=times,
            archived=skill.archived_at is not None,
        )
        for skill, category, times in db.execute(stmt).all()
    ]


@router.post("/skills", status_code=201, response_model=SkillRow)
def create_skill(body: SkillCreate, principal: SuperAdminUser, db: DB) -> SkillRow:
    """The next SKL-nnn. 422 with fields; 409 duplicate_name."""
    return catalog.skill_row(db, catalog.create_skill(db, principal, body))


@router.patch("/skills/{skill_id}", response_model=SkillRow)
def update_skill(skill_id: str, body: SkillPatch, principal: SuperAdminUser, db: DB) -> SkillRow:
    """Applies to future passport versions only; issued ones are frozen."""
    return catalog.skill_row(db, catalog.update_skill(db, principal, skill_id, body))


@router.post("/skills/{skill_id}/archive", response_model=SkillRow)
def archive_skill(skill_id: str, principal: SuperAdminUser, db: DB) -> SkillRow:
    return catalog.skill_row(db, catalog.set_skill_archived(db, principal, skill_id, True))


@router.post("/skills/{skill_id}/unarchive", response_model=SkillRow)
def unarchive_skill(skill_id: str, principal: SuperAdminUser, db: DB) -> SkillRow:
    return catalog.skill_row(db, catalog.set_skill_archived(db, principal, skill_id, False))


@router.delete("/skills/{skill_id}", status_code=204, response_class=Response)
def delete_skill(skill_id: str, principal: SuperAdminUser, db: DB) -> Response:
    """409 in_use when awarded or used by an event; archive instead."""
    catalog.delete_skill(db, principal, skill_id)
    return Response(status_code=204)
