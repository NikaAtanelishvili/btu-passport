"""Catalog schemas: skills (BE-35 read side, BE-50 writes) and categories (BE-51)."""

from pydantic import BaseModel, ConfigDict


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


class SkillCreate(BaseModel):
    """Field rules are checked in app/services/catalog.py, so all errors come back at once."""

    name: str
    category_id: int
    description: str


class SkillPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    category_id: int | None = None
    description: str | None = None
