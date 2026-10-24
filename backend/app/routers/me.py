"""Student portal (/api/me/*). M7 ships My events (BE-46); passport and history are BE-47 (M8)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import StudentUser
from app.db import get_db
from app.schemas.event import MyEvent
from app.services import events

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("/events", response_model=list[MyEvent])
def my_events(principal: StudentUser, db: Annotated[Session, Depends(get_db)]) -> list[MyEvent]:
    assert principal.student is not None
    return events.my_events(db, principal.student.student_id, principal.user.email)
