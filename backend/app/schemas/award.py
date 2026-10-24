"""Direct award schemas (BE-24)."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel


class AwardIn(BaseModel):
    student_ids: list[str]
    skill_id: str
    date_earned: date
    reason: str


class PreviewRow(BaseModel):
    student_id: str
    name: str
    result: Literal["NEW_VERSION", "SKIP_ALREADY_HELD"]
    from_version: int | None = None
    to_version: int | None = None


class PreviewOut(BaseModel):
    rows: list[PreviewRow]


class CreatedVersion(BaseModel):
    student_id: str
    version_id: int
    version_no: int


class AwardOut(BaseModel):
    submission_id: uuid.UUID
    versions: list[CreatedVersion]
    skipped: list[str]
