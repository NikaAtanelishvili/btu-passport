"""Google Sheets intake (M11): one row per sync run, and the last decision for every Sheet row."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    SHEET_OUTCOMES,
    SHEET_RUN_STATUSES,
    SHEET_RUN_TRIGGERS,
    SHEET_TABS,
    Base,
    created_at,
    one_of,
)


class SheetSyncRun(Base):
    __tablename__ = "sheet_sync_runs"
    __table_args__ = (
        one_of("trigger", SHEET_RUN_TRIGGERS),
        one_of("status", SHEET_RUN_STATUSES),
        # At most one run waiting or running (SH-05); the job's dedupe key backs it up.
        Index(
            "sheet_sync_runs_one_active",
            text("(true)"),
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
    )

    run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)  # "Google Sheet", "upload passports.xlsx"
    created_at: Mapped[datetime] = created_at()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)


class SheetRecord(Base):
    """`key` is the Record ID, Student ID or skill code; a repeat of a key already in the tab
    is stored as `<key>@<row>`."""

    __tablename__ = "sheet_records"
    __table_args__ = (
        one_of("tab", SHEET_TABS),
        one_of("outcome", SHEET_OUTCOMES),
        Index("sheet_records_outcome", "outcome"),
    )

    tab: Mapped[str] = mapped_column(Text, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    row_number: Mapped[int] = mapped_column(Integer)
    row_hash: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    award_id: Mapped[int | None] = mapped_column(ForeignKey("skill_awards.award_id"))
    version_id: Mapped[int | None] = mapped_column(ForeignKey("passport_versions.version_id"))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sheet_sync_runs.run_id"))
