"""Guards (BE-12), applied per router. The role is read from user_roles on every request,
so a revocation takes effect on the next request (FR-08, A12)."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import sessions
from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.models import Student, User, UserRole, UserSession


@dataclass(frozen=True)
class Principal:
    user: User
    role: str | None  # "SUPER_ADMIN" | "ADMIN" | None
    student: Student | None
    session: UserSession

    @property
    def is_admin(self) -> bool:
        return self.role in ("ADMIN", "SUPER_ADMIN")


_UNSET = object()


def current_user_optional(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> Principal | None:
    cached = getattr(request.state, "principal", _UNSET)  # once per request (CSRF reuses it)
    if cached is not _UNSET:
        assert cached is None or isinstance(cached, Principal)
        return cached
    principal = None
    row = sessions.load_session(db, request.cookies.get(get_settings().session_cookie_name))
    if row is not None:
        user = db.get(User, row.user_id)
        if user is not None:
            role = db.scalar(select(UserRole.role).where(UserRole.email == user.email))
            student = db.scalar(select(Student).where(Student.email == user.email))
            principal = Principal(user=user, role=role, student=student, session=row)
    request.state.principal = principal
    return principal


def require_user(
    principal: Annotated[Principal | None, Depends(current_user_optional)],
) -> Principal:
    if principal is None:
        raise AppError("unauthenticated", "Sign in to continue.", 401)
    return principal


def require_student(principal: Annotated[Principal, Depends(require_user)]) -> Principal:
    if principal.student is None:
        raise AppError("not_a_student", "This page is for registered BTU students.", 403)
    return principal


def require_admin(principal: Annotated[Principal, Depends(require_user)]) -> Principal:
    if not principal.is_admin:
        raise AppError("forbidden", "You don't have access to this page.", 403)
    return principal


def require_super_admin(principal: Annotated[Principal, Depends(require_user)]) -> Principal:
    if principal.role != "SUPER_ADMIN":
        raise AppError("forbidden", "Only super admins can do this.", 403)
    return principal


CurrentUser = Annotated[Principal | None, Depends(current_user_optional)]
SignedIn = Annotated[Principal, Depends(require_user)]
StudentUser = Annotated[Principal, Depends(require_student)]
AdminUser = Annotated[Principal, Depends(require_admin)]
SuperAdminUser = Annotated[Principal, Depends(require_super_admin)]
