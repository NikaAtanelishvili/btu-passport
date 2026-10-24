"""Minimal row builders for integration tests."""

import os
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    AwardSubmission,
    Event,
    EventParticipant,
    Passport,
    Skill,
    SkillAward,
    SkillCategory,
    Student,
    User,
)


def student(db: Session, n: int = 1, *, holder: bool = False) -> Student:
    s = Student(
        student_id=f"BTU-T-{n:04d}",
        first_name="Nino",
        last_name="Test",
        email=f"btu-t-{n:04d}@example.org",
        program="Information Technologies",
        education_level="BACHELOR",
        status="ACTIVE",
    )
    db.add(s)
    db.flush()
    db.add(
        Passport(
            passport_id=f"BTU-AI-{n:06d}",
            student_id=s.student_id,
            holder_first_name="Nino" if holder else None,
            holder_last_name="Test" if holder else None,
            first_issued_on=date(2026, 10, 1) if holder else None,
        )
    )
    db.flush()
    return s


def skill(db: Session, skill_id: str = "SKL-001") -> Skill:
    category = SkillCategory(name=f"Category {skill_id}", badge_code=f"BDG-{skill_id}")
    db.add(category)
    db.flush()
    s = Skill(
        skill_id=skill_id,
        name=f"Skill {skill_id}",
        category_id=category.category_id,
        description="A skill.",
    )
    db.add(s)
    db.flush()
    return s


def award(db: Session, st: Student, sk: Skill) -> SkillAward:
    submission = AwardSubmission(kind="SEED")
    db.add(submission)
    db.flush()
    a = SkillAward(
        student_id=st.student_id,
        skill_id=sk.skill_id,
        date_earned=date(2026, 10, 1),
        submission_id=submission.submission_id,
    )
    db.add(a)
    db.flush()
    return a


def user(db: Session, email: str = "superadmin@btu.test") -> User:
    u = User(email=email, display_name=email.split("@")[0])
    db.add(u)
    db.flush()
    return u


def event(db: Session, sk: Skill, creator: User, *, status: str = "DRAFT") -> Event:
    start = datetime(2026, 10, 21, 10, tzinfo=UTC)
    e = Event(
        name="AI Data Analysis Workshop",
        skill_id=sk.skill_id,
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        checkin_opens_at=start + timedelta(minutes=105),
        checkin_closes_at=start + timedelta(minutes=150),
        status=status,
        qr_secret=os.urandom(32),
        created_by=creator.user_id,
    )
    db.add(e)
    db.flush()
    return e


def participant(db: Session, ev: Event, email: str = "btu-t-0001@example.org") -> EventParticipant:
    p = EventParticipant(event_id=ev.event_id, email=email, display_name="Nino Test", method="QR")
    db.add(p)
    db.flush()
    return p


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
