"""Student portal schemas (BE-47). My events (BE-46) lives in app/schemas/event.py."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

VersionStatus = Literal["LEGACY", "PENDING", "RENDERED", "ANCHORING", "ANCHORED", "FAILED"]


class VersionSummary(BaseModel):
    version_no: int
    status: VersionStatus
    issued_at: datetime | None
    verification_code: str | None  # ANCHORED only: the code the student can share
    skill_count: int
    added_skills: list[str]  # skills this version holds that the one before it didn't
    superseded: bool  # ANCHORED, with a newer ANCHORED version


class SkillOnPassport(BaseModel):
    name: str
    category: str
    badge_code: str
    stamp_sha256: str | None
    description: str | None
    date_earned: date
    source: Literal["EVENT", "DIRECT", "SEED"]
    event_name: str | None


class IssuingVersion(BaseModel):
    version_no: int


class MyPassport(BaseModel):
    passport_id: str
    holder_name: str
    first_name: str
    last_name: str
    first_issued_on: date | None
    current: VersionSummary | None  # the latest ANCHORED version
    issuing: IssuingVersion | None  # a newer version still on its way
    skills: list[SkillOnPassport]
