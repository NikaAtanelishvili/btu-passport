"""Event, participant, check-in and My events schemas (BE-40 - BE-46)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

EventStatus = Literal["DRAFT", "CHECKIN_OPEN", "CHECKIN_CLOSED", "COMPLETED"]
Blocker = Literal["DRAFT", "CHECKIN_OPEN", "UNREGISTERED_PRESENT", "NO_PARTICIPANTS"]
Flag = Literal["UNREGISTERED", "ALREADY_HOLDS"]


class EventCreate(BaseModel):
    """Field rules are checked in app/services/events.py, so all errors come back at once."""

    name: str
    skill_id: str
    description: str | None = None
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    location: str | None = None
    checkin_opens_at: AwareDatetime | None = None  # default: ends_at - 15 min
    checkin_closes_at: AwareDatetime | None = None  # default: ends_at + 30 min


class EventPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    skill_id: str | None = None
    description: str | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    location: str | None = None
    checkin_opens_at: AwareDatetime | None = None
    checkin_closes_at: AwareDatetime | None = None


class EventSkill(BaseModel):
    skill_id: str
    name: str
    category: str
    stamp_sha256: str | None


class EventRow(BaseModel):
    event_id: uuid.UUID
    name: str
    skill_name: str
    starts_at: datetime
    participant_count: int
    status: EventStatus


class AwardedStudent(BaseModel):
    student_id: str
    version_no: int


class CompleteOut(BaseModel):
    submission_id: uuid.UUID
    awarded: list[AwardedStudent]
    skipped: list[str]  # held the skill already


class EventCounts(BaseModel):
    total: int  # live (not removed) participants
    unregistered: int
    already_held: int


class EventDetail(BaseModel):
    event_id: uuid.UUID
    name: str
    skill_id: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    location: str | None
    checkin_opens_at: datetime
    checkin_closes_at: datetime
    status: EventStatus
    skill: EventSkill
    skill_locked: bool  # someone has checked in (FR-26)
    counts: EventCounts
    can_complete: bool
    complete_blockers: list[Blocker]
    completion: CompleteOut | None
    completed_at: datetime | None


class Participant(BaseModel):
    email: str
    student_id: str | None
    name: str
    checked_in_at: datetime
    method: Literal["QR", "MANUAL"]
    flags: list[Flag]
    removed_at: datetime | None


class ParticipantAdd(BaseModel):
    student_id: str


class QrOut(BaseModel):
    url: str | None  # None unless check-in is open
    svg: str | None
    refresh_in_seconds: int
    participant_count: int
    status: EventStatus


CheckinState = Literal[
    "CONFIRM", "CHECKED_IN", "TOKEN_EXPIRED", "NOT_OPEN", "CLOSED", "REMOVED", "NOT_FOUND"
]


class CheckinEventSkill(BaseModel):
    name: str
    category: str
    stamp_sha256: str | None


class CheckinEvent(BaseModel):
    name: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    checkin_closes_at: datetime
    location: str | None
    skill: CheckinEventSkill


class CheckinView(BaseModel):
    event: CheckinEvent | None  # None for NOT_FOUND
    state: CheckinState
    unregistered: bool = False
    already_holds_skill: bool = False
    from_pass: bool = False  # CONFIRM thanks to this browser's check-in pass: check in now


class CheckinIn(BaseModel):
    """`t` is the QR token. A check-in pass from a signed-out scan travels as a cookie."""

    t: str = ""


class CheckinPassIn(BaseModel):
    t: str


class CheckinPass(BaseModel):
    """The pass itself is set as an HttpOnly cookie on the event's check-in API path."""

    expires_at: datetime


class CheckinResult(BaseModel):
    state: Literal["CHECKED_IN"]
    unregistered: bool
    already_holds_skill: bool


class MyEvent(BaseModel):
    event_id: uuid.UUID
    name: str
    starts_at: datetime
    event_date: date
    skill_name: str
    status: Literal["WAITING", "AWARDED", "ALREADY_HELD", "NOT_CONFIRMED", "EVENT_DELETED"]
    version_no: int | None = None
