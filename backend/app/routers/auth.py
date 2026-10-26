"""/auth/*: passwordless email-code sign-in (BE-10), Sign in with Google (BE-15) and
sign-out."""

import logging
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import google, login_codes, sessions
from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.models import Student, User, UserRole
from app.schemas.auth import AuthProvidersOut, RequestCodeIn, VerifyCodeIn, VerifyCodeOut

log = logging.getLogger("app.auth")
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
    return VerifyCodeOut(redirect=_sign_in(db, email, response, body.next))


def _sign_in(db: Session, email: str, response: Response, next_: str | None) -> str:
    """The identity is proven (code or Google): upsert the user, start a session, set its
    cookies on `response` and return where to go."""
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
    return _redirect(next_, role, student is not None)


def _safe_next(next_: str | None) -> str | None:
    """`next` only when it is a path on this site."""
    if (
        next_
        and next_.startswith("/")
        and not next_.startswith("//")
        and "\\" not in next_
        and next_.isprintable()
    ):
        return next_
    return None


def _redirect(next_: str | None, role: str | None, is_student: bool) -> str:
    """`next` when it is safe; otherwise the role's home page."""
    if safe := _safe_next(next_):
        return safe
    if role in ("ADMIN", "SUPER_ADMIN"):
        return "/admin"
    return "/me" if is_student else "/"


@router.post("/logout", status_code=204, response_class=Response)
def logout(request: Request, db: DB) -> Response:
    sessions.delete_session(db, request.cookies.get(get_settings().session_cookie_name))
    response = Response(status_code=204)
    sessions.clear_cookies(response)
    return response


# --- Sign in with Google (BE-15) -------------------------------------------------------------


@router.get("/providers", response_model=AuthProvidersOut)
def providers() -> AuthProvidersOut:
    """Which sign-in buttons /login shows; email codes are always on."""
    return AuthProvidersOut(google=google.enabled())


def _google_enabled() -> None:
    if not google.enabled():
        raise AppError("not_found", "Not found.", 404)


def _to_login(error: str, next_: str | None) -> RedirectResponse:
    """Back to /login with an error code it turns into a message; `next` survives a retry."""
    query = {"error": error} | ({"next": next_} if next_ else {})
    response = RedirectResponse(f"/login?{urlencode(query)}", status_code=303)
    _clear_flow(response)
    return response


def _clear_flow(response: Response) -> None:
    response.delete_cookie(
        google.FLOW_COOKIE, path=google.FLOW_COOKIE_PATH, secure=get_settings().session_secure,
        httponly=True, samesite="lax",
    )  # fmt: skip


@router.get(
    "/google/start",
    status_code=303,
    response_class=RedirectResponse,
    dependencies=[Depends(_google_enabled)],
    responses={303: {"description": "To Google's consent screen, or /login?error="}},
)
def google_start(request: Request, next: str | None = None) -> RedirectResponse:
    next_ = _safe_next(next)
    try:
        google.check_rate("start", login_codes.client_ip(request))
    except google.GoogleSignInError as exc:
        return _to_login(exc.code, next_)
    flow, cookie = google.new_flow(next_)
    response = RedirectResponse(google.authorization_url(flow), status_code=303)
    # SameSite=Lax: sent on Google's top-level redirect back to the callback.
    response.set_cookie(
        google.FLOW_COOKIE, cookie, max_age=google.FLOW_SECONDS, path=google.FLOW_COOKIE_PATH,
        secure=get_settings().session_secure, httponly=True, samesite="lax",
    )  # fmt: skip
    return response


@router.get(
    "/google/callback",
    status_code=303,
    response_class=RedirectResponse,
    dependencies=[Depends(_google_enabled)],
    responses={303: {"description": "Signed in: to `next` or the role's home; else /login"}},
)
def google_callback(
    request: Request,
    db: DB,
    code: str = "",
    state: str = "",
    error: str = "",
    flow_cookie: Annotated[str, Cookie(alias=google.FLOW_COOKIE, include_in_schema=False)] = "",
) -> RedirectResponse:
    flow = google.read_flow(flow_cookie)
    next_ = flow.next if flow else None
    try:
        google.check_rate("callback", login_codes.client_ip(request))
        if error:  # the user pressed Cancel (access_denied) or Google refused
            raise google.GoogleSignInError(
                "google_cancelled" if error == "access_denied" else "google_failed", error
            )
        if flow is None:
            raise google.GoogleSignInError("google_failed", "flow cookie missing or expired")
        email = google.sign_in(code, state, flow)
        response = RedirectResponse("/", status_code=303)
        response.headers["location"] = _sign_in(db, email, response, flow.next)
    except google.GoogleSignInError as exc:
        log.info("Google sign-in refused: %s (%s)", exc.code, exc)
        return _to_login(exc.code, next_)
    except Exception:  # never a raw 500 on a page the user landed on
        db.rollback()
        log.exception("Google sign-in failed")
        return _to_login("google_failed", next_)
    _clear_flow(response)
    return response
