"""SH-03: the database side of the Sheet rules."""

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AwardSubmission, SheetSyncRun, SkillAward
from tests import factories


def test_one_award_per_source_record(db: Session) -> None:
    student, other = factories.student(db, 1), factories.student(db, 2)
    skill = factories.skill(db)
    submission = AwardSubmission(kind="SHEET")  # the new submission kind is accepted
    db.add(submission)
    db.flush()
    db.add(
        SkillAward(
            student_id=student.student_id,
            skill_id=skill.skill_id,
            date_earned=date(2026, 10, 1),
            submission_id=submission.submission_id,
            source_record_id="REC-0001",
            earned_through="AI Literacy Workshop",
        )
    )
    db.flush()
    db.add(
        SkillAward(
            student_id=other.student_id,
            skill_id=skill.skill_id,
            date_earned=date(2026, 10, 1),
            submission_id=submission.submission_id,
            source_record_id="REC-0001",
        )
    )
    with pytest.raises(IntegrityError, match="uq_skill_awards_source_record_id"):
        db.flush()


def test_earned_through_length(db: Session) -> None:
    student, skill = factories.student(db, 1), factories.skill(db)
    award = factories.award(db, student, skill)
    award.earned_through = "x" * 121
    with pytest.raises(IntegrityError, match="earned_through_length"):
        db.flush()


def test_at_most_one_active_run(db: Session) -> None:
    db.add(SheetSyncRun(trigger="SCHEDULE", status="DONE", source="Google Sheet"))
    db.add(SheetSyncRun(trigger="SCHEDULE", status="RUNNING", source="Google Sheet"))
    db.flush()
    db.add(SheetSyncRun(trigger="MANUAL", status="QUEUED", source="Google Sheet"))
    with pytest.raises(IntegrityError, match="sheet_sync_runs_one_active"):
        db.flush()


def test_outcome_vocabulary(db: Session) -> None:
    db.add(SheetSyncRun(trigger="MANUAL", status="DONE", source="Google Sheet"))
    db.flush()
    with pytest.raises(IntegrityError, match="ck_sheet_records_outcome"):
        db.execute(
            text(
                "INSERT INTO sheet_records (tab, key, row_number, row_hash, outcome, run_id)"
                " VALUES ('Verified Skills', 'REC-0001', 2, 'h', 'SYNCED', 1)"
            )
        )
