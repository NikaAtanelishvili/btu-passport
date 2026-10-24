"""Student schemas (admin, BE-35)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.version import VersionRow


class StudentRow(BaseModel):
    student_id: str
    first_name: str
    last_name: str
    email: str
    program: str
    education_level: str
    status: str
    passport_id: str | None
    latest_version_no: int | None = None  # highest version of any status
    latest_status: str | None = None


class StudentCreate(BaseModel):
    """Field rules are checked in app/services/students.py, so every error comes back at
    once with a readable message under its field."""

    student_id: str
    first_name: str
    last_name: str
    email: str
    program: str
    education_level: str
    status: str


class StudentPatch(BaseModel):
    """Any StudentCreate field except student_id, which never changes."""

    model_config = ConfigDict(extra="forbid")

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    program: str | None = None
    education_level: str | None = None
    status: str | None = None


class StudentProfile(BaseModel):
    student_id: str
    first_name: str
    last_name: str
    email: str
    program: str
    education_level: str
    status: str
    created_at: datetime


class PassportInfo(BaseModel):
    passport_id: str
    first_issued_on: date | None
    holder_first_name: str | None
    holder_last_name: str | None
    frozen: bool  # holder names are printed on an issued version (FR-11)
    versions: list[VersionRow]  # newest first


class AwardRow(BaseModel):
    award_id: int
    skill_id: str
    skill_name: str
    category: str
    stamp_sha256: str | None
    date_earned: date
    source: Literal["DIRECT", "EVENT", "SEED"]
    submission_id: uuid.UUID
    event_id: uuid.UUID | None
    event_name: str | None
    legacy_record_id: str | None
    reason: str | None
    awarded_by: str | None  # email; None for the seed


class ParticipationRow(BaseModel):
    event_id: uuid.UUID
    event_name: str
    starts_at: datetime
    event_status: str
    event_deleted: bool
    checked_in_at: datetime
    method: str
    removed: bool


class StudentDetail(BaseModel):
    profile: StudentProfile
    passport: PassportInfo
    awards: list[AwardRow]
    events: list[ParticipationRow]
    warnings: list[Literal["printed_name_differs"]] = []
