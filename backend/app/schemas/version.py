"""Passport version schemas (admin issuance page, BE-29)."""

from datetime import datetime

from pydantic import BaseModel


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
