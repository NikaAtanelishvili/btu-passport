"""Passport version schemas (admin issuance page, BE-29)."""

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.models import PassportVersion, Student


class VersionRow(BaseModel):
    version_id: int
    passport_id: str
    student_id: str
    student_name: str
    version_no: int
    status: str
    error: str | None
    issued_at: datetime | None
    created_at: datetime


class RetryCount(BaseModel):
    count: int


def version_row(version: "PassportVersion", student: "Student") -> VersionRow:
    return VersionRow(
        version_id=version.version_id,
        passport_id=version.passport_id,
        student_id=student.student_id,
        student_name=f"{student.first_name} {student.last_name}",
        version_no=version.version_no,
        status=version.status,
        error=version.error,
        issued_at=version.issued_at,
        created_at=version.created_at,
    )
