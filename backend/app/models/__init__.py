"""All models, imported here so Base.metadata knows every table (Alembic, tests)."""

from app.models.audit import AuditLog
from app.models.award import AwardSubmission, SkillAward
from app.models.base import Base
from app.models.catalog import Skill, SkillCategory
from app.models.event import Event, EventParticipant
from app.models.job import Job
from app.models.student import Passport, Student, passport_number_seq
from app.models.user import LoginCode, User, UserRole, UserSession
from app.models.version import AnchorBatch, PassportVersion, VersionAward

__all__ = [
    "AnchorBatch",
    "AuditLog",
    "AwardSubmission",
    "Base",
    "Event",
    "EventParticipant",
    "Job",
    "LoginCode",
    "Passport",
    "PassportVersion",
    "Skill",
    "SkillAward",
    "SkillCategory",
    "Student",
    "User",
    "UserRole",
    "UserSession",
    "VersionAward",
    "passport_number_seq",
]
