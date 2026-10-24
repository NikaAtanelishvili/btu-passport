"""Skills, read side (BE-35 for the direct award form). Writes are super-admin only (BE-50, M9)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Skill, SkillAward, SkillCategory
from app.schemas.catalog import CategoryRef, SkillRow

router = APIRouter(tags=["admin: catalog"])


@router.get("/skills", response_model=list[SkillRow])
def list_skills(
    db: Annotated[Session, Depends(get_db)], include_archived: bool = False
) -> list[SkillRow]:
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
