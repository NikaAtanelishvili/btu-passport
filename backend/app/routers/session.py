"""GET /api/session: who is signed in, with which role (BE-14)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.db import get_db
from app.models import Passport
from app.schemas.session import SessionInfo, SessionStudent, SessionUser

router = APIRouter(tags=["session"])


@router.get("/api/session", response_model=SessionInfo, response_model_exclude_unset=True)
def get_session(principal: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> SessionInfo:
    if principal is None:
        return SessionInfo(authenticated=False)
    student = None
    if principal.student is not None:
        passport_id = db.scalar(
            select(Passport.passport_id).where(Passport.student_id == principal.student.student_id)
        )
        student = SessionStudent(student_id=principal.student.student_id, passport_id=passport_id)
    return SessionInfo(
        authenticated=True,
        user=SessionUser(email=principal.user.email, name=principal.user.display_name),
        role=principal.role,
        student=student,
    )
