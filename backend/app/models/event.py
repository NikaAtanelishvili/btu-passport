"""Events and their check-in participants (FR-26-FR-33)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    CHECKIN_METHODS,
    EVENT_STATUSES,
    Base,
    created_at,
    lower_email,
    one_of,
    updated_at,
)


class Event(Base):
    """Soft-deleted via deleted_at; trigger event_rules makes COMPLETED events read-only."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("length(name) <= 120", name="name_length"),
        CheckConstraint("length(description) <= 500", name="description_length"),
        CheckConstraint("ends_at > starts_at", name="ends_after_starts"),
        CheckConstraint("checkin_closes_at > checkin_opens_at", name="checkin_closes_after_opens"),
        one_of("status", EVENT_STATUSES),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.skill_id"))
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(Text)
    checkin_opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checkin_closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    qr_secret: Mapped[bytes] = mapped_column(LargeBinary)  # 32 random bytes
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class EventParticipant(Base):
    __tablename__ = "event_participants"
    __table_args__ = (
        UniqueConstraint("event_id", "email"),  # FR-29
        UniqueConstraint("event_id", "pass_nonce"),  # a check-in pass is used once
        lower_email(),
        one_of("method", CHECKIN_METHODS),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.event_id"))
    email: Mapped[str] = mapped_column(Text)
    student_id: Mapped[str | None] = mapped_column(
        ForeignKey("students.student_id")
    )  # NULL = Unregistered
    display_name: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text)
    checked_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"))
    pass_nonce: Mapped[str | None] = mapped_column(Text)  # set when checked in with a pass
