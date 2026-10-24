"""/auth/*: passwordless email-code sign-in and sign-out (BE-10)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import login_codes, sessions
from app.config import get_settings
from app.db import get_db
from app.models import Student, User, UserRole
from app.schemas.auth import RequestCodeIn, VerifyCodeIn, VerifyCodeOut

router = APIRouter(prefix="/auth", tags=["auth"])
DB = Annotated[Session, Depends(get_db)]


@router.post("/request-code", status_code=204, response_class=Response)
def request_code(body: RequestCodeIn, request: Request, db: DB) -> Response:
    """Emails a code. Same 204 whether or not the address belongs to a student."""
    email = login_codes.normalise_email(body.email)
    login_codes.check_domain(email)
    login_codes.request_code(db, email, login_codes.client_ip(request))
    return Response(status_code=204)


@router.post("/verify-code", response_model=VerifyCodeOut)
def verify_code(body: VerifyCodeIn, response: Response, db: DB) -> VerifyCodeOut:
    email = login_codes.normalise_email(body.email)
    login_codes.check_code(db, email, body.code)

    student = db.scalar(select(Student).where(Student.email == email))
    display_name = f"{student.first_name} {student.last_name}" if student else email.split("@")[0]
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, display_name=display_name)
        db.add(user)
    user.display_name = display_name
    user.last_login_at = datetime.now(UTC)
    db.flush()

    token, row = sessions.create_session(db, user)
    sessions.set_cookies(response, token, row)
    role = db.scalar(select(UserRole.role).where(UserRole.email == email))
    return VerifyCodeOut(redirect=_redirect(body.next, role, student is not None))


def _redirect(next_: str | None, role: str | None, is_student: bool) -> str:
    """`next` only when it is a path on this site; otherwise the role's home page."""
    if (
        next_
        and next_.startswith("/")
        and not next_.startswith("//")
        and "\\" not in next_
        and next_.isprintable()
    ):
        return next_
    if role in ("ADMIN", "SUPER_ADMIN"):
        return "/admin"
    return "/me" if is_student else "/"


@router.post("/logout", status_code=204, response_class=Response)
def logout(request: Request, db: DB) -> Response:
    sessions.delete_session(db, request.cookies.get(get_settings().session_cookie_name))
    response = Response(status_code=204)
    sessions.clear_cookies(response)
    return response
