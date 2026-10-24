"""Server-side sessions (BE-11, NFR-04). The cookie holds a random token; the table holds
only its SHA-256, so a database leak doesn't hand out live sessions."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, UserRole, UserSession

CSRF_COOKIE = "csrf_token"
TOUCH_INTERVAL = timedelta(minutes=1)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def create_session(db: Session, user: User) -> tuple[str, UserSession]:
    """Returns (cookie token, row). The token is never stored."""
    token = secrets.token_urlsafe(32)
    now = _now()
    row = UserSession(
        session_hash=hash_token(token),
        user_id=user.user_id,
        csrf_token=secrets.token_urlsafe(32),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=get_settings().session_absolute_hours),
    )
    db.add(row)
    db.flush()
    return token, row


def load_session(db: Session, token: str | None) -> UserSession | None:
    """The live session for this token, or None if unknown, expired or idle too long."""
    if not token:
        return None
    row = db.get(UserSession, hash_token(token))
    if row is None:
        return None
    now = _now()
    if row.expires_at <= now or _idle_expired(db, row, now):
        db.delete(row)
        db.flush()
        return None
    if now - row.last_seen_at >= TOUCH_INTERVAL:
        row.last_seen_at = now
        db.flush()
    return row


def _idle_expired(db: Session, row: UserSession, now: datetime) -> bool:
    """Users with a role (admins) also expire after ADMIN_IDLE_MINUTES without a request."""
    idle_limit = timedelta(minutes=get_settings().admin_idle_minutes)
    if now - row.last_seen_at <= idle_limit:
        return False
    has_role = db.scalar(
        select(
            exists().where(
                UserRole.email
                == select(User.email).where(User.user_id == row.user_id).scalar_subquery()
            )
        )
    )
    return bool(has_role)


def delete_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(UserSession).where(UserSession.session_hash == hash_token(token)))


def revoke_user_sessions(db: Session, email: str) -> int:
    """Sign a person out everywhere; called when their role is revoked or changed (FR-08)."""
    user_ids = select(User.user_id).where(User.email == email.strip().lower())
    result = db.execute(delete(UserSession).where(UserSession.user_id.in_(user_ids)))
    return int(getattr(result, "rowcount", 0) or 0)


def set_cookies(response: Response, token: str, row: UserSession) -> None:
    """Session cookie (HttpOnly) plus the readable CSRF cookie for double-submit (BE-13)."""
    s = get_settings()
    max_age = int((row.expires_at - _now()).total_seconds())
    for name, value, httponly in (
        (s.session_cookie_name, token, True),
        (CSRF_COOKIE, row.csrf_token, False),
    ):
        response.set_cookie(
            name, value, max_age=max_age, path="/", secure=s.session_secure,
            httponly=httponly, samesite="lax",
        )  # fmt: skip


def clear_cookies(response: Response) -> None:
    s = get_settings()
    for name in (s.session_cookie_name, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=s.session_secure, samesite="lax")
