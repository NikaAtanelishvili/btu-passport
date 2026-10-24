"""Declarative base, shared column helpers and the status vocabularies (BE-02)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable constraint names, so migrations and error handling can refer to them.
NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

EDUCATION_LEVELS = ("BACHELOR", "MASTER", "DOCTORAL")
STUDENT_STATUSES = ("ACTIVE", "GRADUATE")
SUBMISSION_KINDS = ("DIRECT", "EVENT", "SEED")
VERSION_STATUSES = ("LEGACY", "PENDING", "RENDERED", "ANCHORING", "ANCHORED", "FAILED")
BATCH_STATUSES = ("SUBMITTING", "ANCHORED", "FAILED")
JOB_TYPES = ("ISSUE_VERSION", "ANCHOR_BATCH")
JOB_STATUSES = ("QUEUED", "RUNNING", "DONE", "FAILED")
ROLES = ("SUPER_ADMIN", "ADMIN")
EVENT_STATUSES = ("DRAFT", "CHECKIN_OPEN", "CHECKIN_CLOSED", "COMPLETED")
CHECKIN_METHODS = ("QR", "MANUAL")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def one_of(column: str, values: tuple[str, ...], name: str | None = None) -> CheckConstraint:
    allowed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name or column)


def lower_email(column: str = "email") -> CheckConstraint:
    return CheckConstraint(f"{column} = lower({column})", name=f"{column}_lower")


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def updated_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
