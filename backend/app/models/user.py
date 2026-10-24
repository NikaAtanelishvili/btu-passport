"""Users, roles, sessions and email login codes (BE-10-BE-12)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ROLES, Base, created_at, lower_email, one_of


class User(Base):
    __tablename__ = "users"
    __table_args__ = (lower_email(),)

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserRole(Base):
    """Keyed by email so a role can be granted before the person first signs in."""

    __tablename__ = "user_roles"
    __table_args__ = (lower_email(), one_of("role", ROLES))

    email: Mapped[str] = mapped_column(Text, primary_key=True)
    role: Mapped[str] = mapped_column(Text)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"))
    granted_at: Mapped[datetime] = created_at()


class UserSession(Base):
    """A signed-in browser. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "sessions"

    session_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"))
    csrf_token: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginCode(Base):
    """A one-time sign-in code. Only its SHA-256 is stored, never the code."""

    __tablename__ = "login_codes"
    __table_args__ = (lower_email(), Index("login_codes_email", "email", "created_at"))

    code_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text)
    code_hash: Mapped[str] = mapped_column(Text)
    requested_ip: Mapped[str | None] = mapped_column(INET)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()
