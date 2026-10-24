"""Skill catalog: categories (with stamp image) and skills (FR-07, FR-34, FR-35)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at, updated_at


class SkillCategory(Base):
    __tablename__ = "skill_categories"

    category_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    badge_code: Mapped[str] = mapped_column(Text, unique=True)
    stamp_sha256: Mapped[str | None] = mapped_column(Text)
    stamp_key: Mapped[str | None] = mapped_column(Text)
    stamp_mime: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint("length(name) <= 80", name="name_length"),
        CheckConstraint("length(description) <= 300", name="description_length"),
    )

    skill_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("skill_categories.category_id"))
    description: Mapped[str] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()
