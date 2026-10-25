"""Check-in (BE-42): any signed-in BTU user. The page reads the state with GET and checks in
with POST; a POST that can't check in returns 409 (404 for NOT_FOUND) with `state`. A signed-out
scan first trades its QR token for a check-in pass (public), used as `p` after sign-in."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import SignedIn
from app.db import get_db
from app.schemas.event import CheckinIn, CheckinPass, CheckinPassIn, CheckinResult, CheckinView
from app.services import checkin

router = APIRouter(prefix="/api/checkin", tags=["check-in"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/{event_id}", response_model=CheckinView)
def checkin_view(
    event_id: str, principal: SignedIn, db: DB, t: str = "", p: str = ""
) -> CheckinView:
    return checkin.view(db, principal, event_id, t, p)


@router.post("/{event_id}", response_model=CheckinResult)
def checkin_post(event_id: str, body: CheckinIn, principal: SignedIn, db: DB) -> CheckinResult:
    return checkin.check_in(db, principal, event_id, body.t, body.p)


@router.post("/{event_id}/pass", response_model=CheckinPass)
def checkin_pass(event_id: str, body: CheckinPassIn, db: DB) -> CheckinPass:
    """Signed-out scan: the QR token is checked now; the pass lasts 10 minutes, one use.
    409 (404 for NOT_FOUND) with `state` when there is nothing to check in to."""
    return checkin.issue_pass(db, event_id, body.t)
