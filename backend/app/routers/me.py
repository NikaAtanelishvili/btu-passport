"""Student portal (/api/me/*): passport, history and downloads (BE-47), My events (BE-46).
Every route works on the signed-in student's own passport; none takes an ID that names it."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.deps import StudentUser
from app.db import get_db
from app.routers.verify import build_proof_file, pdf_response, set_proof_filename
from app.schemas.event import MyEvent
from app.schemas.me import MyPassport, VersionSummary
from app.schemas.verify import ProofFile
from app.services import events, portal

router = APIRouter(prefix="/api/me", tags=["me"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/passport", response_model=MyPassport)
def my_passport(principal: StudentUser, db: DB) -> MyPassport:
    assert principal.student is not None
    return portal.passport(db, principal.student)


@router.get("/versions", response_model=list[VersionSummary])
def my_versions(principal: StudentUser, db: DB) -> list[VersionSummary]:
    """Newest first, including LEGACY."""
    assert principal.student is not None
    return portal.versions(db, principal.student)


@router.get(
    "/versions/{version_no}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def my_pdf(version_no: int, principal: StudentUser, db: DB) -> Response:
    """Own ANCHORED versions only, else 404."""
    assert principal.student is not None
    return pdf_response(portal.anchored_version(db, principal.student, version_no))


@router.get(
    "/versions/{version_no}/proof.json", response_model=ProofFile, response_model_by_alias=True
)
def my_proof(version_no: int, principal: StudentUser, db: DB, response: Response) -> ProofFile:
    """Own ANCHORED versions only, else 404."""
    assert principal.student is not None
    version = portal.anchored_version(db, principal.student, version_no)
    set_proof_filename(response, version)
    return build_proof_file(db, version)


@router.get("/events", response_model=list[MyEvent])
def my_events(principal: StudentUser, db: DB) -> list[MyEvent]:
    assert principal.student is not None
    return events.my_events(db, principal.student.student_id, principal.user.email)
