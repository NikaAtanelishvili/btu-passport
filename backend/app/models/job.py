"""Postgres-backed job queue (BE-26)."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import JOB_STATUSES, JOB_TYPES, Base, created_at, one_of


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        one_of("type", JOB_TYPES),
        one_of("status", JOB_STATUSES),
        Index("jobs_ready", "status", "run_after"),
        Index(
            "jobs_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
    )

    job_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="5")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
