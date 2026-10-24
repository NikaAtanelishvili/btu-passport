"""Students and their one passport each (FR-02, FR-10, FR-11)."""

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Sequence, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    EDUCATION_LEVELS,
    STUDENT_STATUSES,
    Base,
    created_at,
    lower_email,
    one_of,
    updated_at,
)

# Next Passport ID = 'BTU-AI-' || lpad(nextval, 6, '0'). Created by the migration.
passport_number_seq = Sequence("passport_number_seq", start=1, metadata=Base.metadata)


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        lower_email(),
        one_of("education_level", EDUCATION_LEVELS),
        one_of("status", STUDENT_STATUSES),
    )

    student_id: Mapped[str] = mapped_column(Text, primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    program: Mapped[str] = mapped_column(Text)
    education_level: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class Passport(Base):
    """Frozen fields (holder names, first_issued_on) are set at first issue; trigger guards them."""

    __tablename__ = "passports"
    passport_id: Mapped[str] = mapped_column(Text, primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), unique=True)
    holder_first_name: Mapped[str | None] = mapped_column(Text)
    holder_last_name: Mapped[str | None] = mapped_column(Text)
    first_issued_on: Mapped[date | None] = mapped_column(Date)
    latest_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("passport_versions.version_id", use_alter=True)
    )
    created_at: Mapped[datetime] = created_at()
