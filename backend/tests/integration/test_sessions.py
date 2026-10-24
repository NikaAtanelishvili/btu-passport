"""BE-11: server-side sessions (NFR-04)."""

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth import sessions
from app.models import UserRole, UserSession
from tests import factories as f


def _age(db: Session, token: str, **delta: float) -> None:
    """Pretend the session was last seen `delta` ago."""
    db.execute(
        update(UserSession)
        .where(UserSession.session_hash == sessions.hash_token(token))
        .values(last_seen_at=datetime.now(UTC) - timedelta(**delta))
    )


def test_only_the_token_hash_is_stored(db: Session) -> None:
    user = f.user(db, "btu-t-0001@example.org")
    token, row = sessions.create_session(db, user)
    assert row.session_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in {row.session_hash, row.csrf_token}
    assert len(token) >= 43 and len(row.csrf_token) >= 43  # 32 random bytes, url-safe


def test_load_returns_session_and_user(db: Session) -> None:
    user = f.user(db, "btu-t-0001@example.org")
    token, _ = sessions.create_session(db, user)
    loaded = sessions.load_session(db, token)
    assert loaded is not None and loaded.user_id == user.user_id
    assert sessions.load_session(db, "not-a-token") is None


def test_absolute_expiry(db: Session) -> None:
    user = f.user(db, "btu-t-0001@example.org")
    token, row = sessions.create_session(db, user)
    assert row.expires_at - row.created_at <= timedelta(hours=8, seconds=5)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert sessions.load_session(db, token) is None


def test_admin_sessions_expire_when_idle(db: Session) -> None:
    admin = f.user(db, "admin@btu.test")
    db.add(UserRole(email="admin@btu.test", role="ADMIN"))
    token, _ = sessions.create_session(db, admin)
    _age(db, token, minutes=29)
    assert sessions.load_session(db, token) is not None
    _age(db, token, minutes=31)
    assert sessions.load_session(db, token) is None


def test_student_sessions_have_no_idle_limit(db: Session) -> None:
    student = f.user(db, "btu-t-0001@example.org")
    token, _ = sessions.create_session(db, student)
    _age(db, token, hours=3)
    assert sessions.load_session(db, token) is not None


def test_last_seen_updates_at_most_once_a_minute(db: Session) -> None:
    user = f.user(db, "btu-t-0001@example.org")
    token, row = sessions.create_session(db, user)
    _age(db, token, seconds=30)
    db.refresh(row)
    before = row.last_seen_at
    sessions.load_session(db, token)
    db.refresh(row)
    assert row.last_seen_at == before
    _age(db, token, seconds=90)
    sessions.load_session(db, token)
    db.refresh(row)
    assert datetime.now(UTC) - row.last_seen_at < timedelta(seconds=5)


def test_revoke_user_sessions(db: Session) -> None:
    admin = f.user(db, "admin@btu.test")
    other = f.user(db, "btu-t-0001@example.org")
    sessions.create_session(db, admin)
    sessions.create_session(db, admin)
    keep, _ = sessions.create_session(db, other)
    assert sessions.revoke_user_sessions(db, "ADMIN@btu.test") == 2
    assert db.scalar(select(func.count()).select_from(UserSession)) == 1
    assert sessions.load_session(db, keep) is not None
