"""Award submissions (one per request, event or seed) and the awards they create."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SUBMISSION_KINDS, Base, created_at, one_of


class AwardSubmission(Base):
    __tablename__ = "award_submissions"
    __table_args__ = (one_of("kind", SUBMISSION_KINDS),)

    submission_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)  # DIRECT
    event_id: Mapped[uuid.UUID | None] = mapped_column(  # EVENT: one per event (FR-32)
        ForeignKey("events.event_id"), unique=True
    )
    reason: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"))
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()


class SkillAward(Base):
    """Never deleted (trigger skill_awards_no_delete): issued versions reference them."""

    __tablename__ = "skill_awards"
    __table_args__ = (UniqueConstraint("student_id", "skill_id"),)

    award_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"))
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.skill_id"))
    date_earned: Mapped[date] = mapped_column(Date)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("award_submissions.submission_id"))
    legacy_record_id: Mapped[str | None] = mapped_column(Text, unique=True)  # 'REC-0001'
    created_at: Mapped[datetime] = created_at()
