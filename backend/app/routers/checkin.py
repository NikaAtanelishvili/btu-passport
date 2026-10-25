"""Check-in (BE-42): any signed-in BTU user. The page reads the state with GET and checks in
with POST; a POST that can't check in returns 409 (404 for NOT_FOUND) with `state`.

A signed-out scan first trades its QR token for a check-in pass (public). The pass lives only
in an HttpOnly cookie scoped to this event's check-in API, so a forwarded link carries nothing;
the same browser sends it back after sign-in, and a successful check-in clears it."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.orm import Session

from app.auth.deps import SignedIn
from app.config import get_settings
from app.db import get_db
from app.schemas.event import CheckinIn, CheckinPass, CheckinPassIn, CheckinResult, CheckinView
from app.services import checkin, qr_tokens

router = APIRouter(prefix="/api/checkin", tags=["check-in"])
DB = Annotated[Session, Depends(get_db)]
PASS_COOKIE = "checkin_pass"
PassCookie = Annotated[str, Cookie(alias=PASS_COOKIE, include_in_schema=False)]


def _cookie_path(event_id: str) -> str:
    return f"/api/checkin/{event_id}"


@router.get("/{event_id}", response_model=CheckinView)
def checkin_view(
    event_id: str, principal: SignedIn, db: DB, t: str = "", checkin_pass: PassCookie = ""
) -> CheckinView:
    return checkin.view(db, principal, event_id, t, checkin_pass)


@router.post("/{event_id}", response_model=CheckinResult)
def checkin_post(
    event_id: str,
    body: CheckinIn,
    principal: SignedIn,
    db: DB,
    response: Response,
    checkin_pass: PassCookie = "",
) -> CheckinResult:
    result = checkin.check_in(db, principal, event_id, body.t, checkin_pass)
    if checkin_pass:  # used (or not needed: already checked in); either way it's done
        response.delete_cookie(
            PASS_COOKIE,
            path=_cookie_path(event_id),
            secure=get_settings().session_secure,
            httponly=True,
            samesite="lax",
        )
    return result


@router.post("/{event_id}/pass", response_model=CheckinPass)
def checkin_pass(event_id: str, body: CheckinPassIn, db: DB, response: Response) -> CheckinPass:
    """Signed-out scan: the QR token is checked now; the pass (cookie) lasts 10 minutes, one
    use. 409 (404 for NOT_FOUND) with `state` when there is nothing to check in to."""
    value, out = checkin.issue_pass(db, event_id, body.t)
    response.set_cookie(
        PASS_COOKIE,
        value,
        max_age=qr_tokens.PASS_SECONDS,
        path=_cookie_path(event_id),
        secure=get_settings().session_secure,
        httponly=True,
        samesite="lax",
    )
    return out
