"""GET /api/session (BE-14)."""

from typing import Literal

from pydantic import BaseModel


class SessionUser(BaseModel):
    email: str
    name: str


class SessionStudent(BaseModel):
    student_id: str
    passport_id: str | None


class SessionInfo(BaseModel):
    """Signed out: only `authenticated: false`. Signed in: all four keys, nulls included."""

    authenticated: bool
    user: SessionUser | None = None
    role: Literal["SUPER_ADMIN", "ADMIN"] | None = None
    student: SessionStudent | None = None
