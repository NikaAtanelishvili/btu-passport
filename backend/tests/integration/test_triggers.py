"""BE-03: rules enforced by database triggers, checked with plain SQL."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import AuditLog
from tests import factories as f


def _raises(db: Session, sql: str, match: str, **params: object) -> None:
    with pytest.raises(DBAPIError, match=match):
        db.execute(text(sql), params)
        db.flush()
    db.rollback()


def test_audit_log_is_append_only(db: Session) -> None:
    db.add(AuditLog(action="test.create", entity="test", entity_id="1"))
    db.commit()
    _raises(db, "UPDATE audit_log SET action = 'x'", "append-only")
    _raises(db, "DELETE FROM audit_log", "append-only")
    assert db.scalar(text("SELECT count(*) FROM audit_log")) == 1


def test_passport_frozen_fields_set_once(db: Session) -> None:
    f.student(db, 1, holder=True)
    db.commit()
    _raises(db, "UPDATE passports SET holder_first_name = 'Other'", "frozen")
    _raises(db, "UPDATE passports SET holder_last_name = NULL", "frozen")
    _raises(db, "UPDATE passports SET first_issued_on = '2026-01-01'", "frozen")
    _raises(db, "UPDATE passports SET passport_id = 'BTU-AI-999999'", "frozen")


def test_passport_frozen_fields_may_be_filled_from_null(db: Session) -> None:
    f.student(db, 1)
    f.student(db, 2)
    db.commit()
    db.execute(
        text(
            "UPDATE passports SET holder_first_name = 'Nino', holder_last_name = 'Test',"
            " first_issued_on = '2026-10-20' WHERE passport_id = 'BTU-AI-000001'"
        )
    )
    db.commit()
    _raises(
        db,
        "UPDATE passports SET student_id = 'BTU-T-0002' WHERE passport_id = 'BTU-AI-000001'",
        "frozen",
    )


def test_event_skill_locked_once_participants_exist(db: Session) -> None:
    creator = f.user(db)
    ev = f.event(db, f.skill(db, "SKL-001"), creator)
    f.skill(db, "SKL-002")
    db.commit()
    db.execute(text("UPDATE events SET skill_id = 'SKL-002'"))  # allowed: nobody checked in
    db.commit()
    f.participant(db, ev)
    db.commit()
    _raises(db, "UPDATE events SET skill_id = 'SKL-001'", "participants")
    db.execute(text("UPDATE events SET name = 'Renamed'"))  # other fields still editable
    db.commit()


def test_completed_event_is_read_only(db: Session) -> None:
    creator = f.user(db)
    f.event(db, f.skill(db), creator, status="COMPLETED")
    db.commit()
    _raises(db, "UPDATE events SET name = 'Changed'", "COMPLETED")
    _raises(db, "UPDATE events SET deleted_at = now()", "COMPLETED")
    _raises(db, "DELETE FROM events", "COMPLETED")  # A16 backstop


def test_skill_awards_cannot_be_deleted(db: Session) -> None:
    f.award(db, f.student(db), f.skill(db))
    db.commit()
    _raises(db, "DELETE FROM skill_awards", "never deleted")
    assert db.scalar(text("SELECT count(*) FROM skill_awards")) == 1


def test_one_passport_per_student(db: Session) -> None:
    f.student(db, 1)
    db.commit()
    _raises(
        db,
        "INSERT INTO passports (passport_id, student_id) VALUES ('BTU-AI-000002', 'BTU-T-0001')",
        "uq_passports_student_id",
    )


def test_passport_number_sequence_exists(db: Session) -> None:
    assert db.scalar(text("SELECT nextval('passport_number_seq')")) == 1
