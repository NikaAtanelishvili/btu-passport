"""BE-21: audit rows are written in the caller's transaction, with the actor or NULL."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import Principal
from app.models import AuditLog, UserSession
from app.services import audit
from tests import factories as f


def _principal(db: Session) -> Principal:
    user = f.user(db, "admin@btu.test")
    session = UserSession(
        session_hash="x",
        user_id=user.user_id,
        csrf_token="c",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return Principal(user=user, role="ADMIN", student=None, session=session)


def test_record_with_a_request_actor(db: Session) -> None:
    actor = _principal(db)
    audit.record(db, actor, "award.direct", "award_submission", "abc", after={"n": 1})
    row = db.scalars(select(AuditLog)).one()
    assert (row.actor_user_id, row.actor_email) == (actor.user.user_id, "admin@btu.test")
    assert (row.action, row.entity, row.entity_id, row.after) == (
        "award.direct",
        "award_submission",
        "abc",
        {"n": 1},
    )


def test_system_actor_is_null(db: Session) -> None:
    audit.record(db, None, "bootstrap", "user_role", "superadmin@btu.test")
    row = db.scalars(select(AuditLog)).one()
    assert row.actor_user_id is None and row.actor_email is None


def test_row_rolls_back_with_the_caller(db: Session) -> None:
    audit.record(db, None, "version.retry", "passport_version", "1")
    db.rollback()
    assert db.scalars(select(AuditLog)).first() is None
