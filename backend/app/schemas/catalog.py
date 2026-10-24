"""Catalog schemas. M6 needs only the read side of skills (BE-35); writes come in BE-50."""

from pydantic import BaseModel


class CategoryRef(BaseModel):
    category_id: int
    name: str
    badge_code: str
    stamp_sha256: str | None


class SkillRow(BaseModel):
    skill_id: str
    name: str
    category: CategoryRef
    description: str
    times_awarded: int
    archived: bool
