"""Issuance page (BE-29): version list, retry, and any ANCHORED version's PDF. Both admin roles."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.auth.deps import AdminUser
from app.db import get_db
from app.errors import AppError
from app.models import Passport, PassportVersion, Student
from app.schemas.common import Page
from app.schemas.version import RetryCount, VersionRow, version_row
from app.services import issuance, storage

router = APIRouter(tags=["admin: versions"])
DB = Annotated[Session, Depends(get_db)]


def _rows() -> Select[PassportVersion, Student]:
    return (
        select(PassportVersion, Student)
        .join(Passport, Passport.passport_id == PassportVersion.passport_id)
        .join(Student, Student.student_id == Passport.student_id)
    )


def _one(db: Session, version_id: int) -> VersionRow:
    found = db.execute(_rows().where(PassportVersion.version_id == version_id)).one_or_none()
    if found is None:
        raise AppError("not_found", "No such version.", 404)
    version, student = found
    return version_row(version, student)


@router.get("/versions", response_model=Page[VersionRow])
def list_versions(
    db: DB,
    status: Annotated[str | None, Query(description="Comma-separated statuses")] = None,
    passport_id: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[VersionRow]:
    stmt = _rows()
    if status:
        stmt = stmt.where(
            PassportVersion.status.in_([s.strip().upper() for s in status.split(",")])
        )
    if passport_id:
        stmt = stmt.where(PassportVersion.passport_id == passport_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(PassportVersion.created_at.desc(), PassportVersion.version_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        items=[version_row(v, s) for v, s in rows], total=total, page=page, page_size=page_size
    )


@router.post("/versions/retry-failed", response_model=RetryCount)
def retry_failed(principal: AdminUser, db: DB) -> RetryCount:
    return RetryCount(count=issuance.retry_failed(db, principal))


@router.post("/versions/{version_id}/retry", status_code=202, response_model=VersionRow)
def retry_version(version_id: int, principal: AdminUser, db: DB) -> VersionRow:
    issuance.retry_version(db, principal, version_id)
    return _one(db, version_id)


@router.get(
    "/versions/{version_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def version_pdf(version_id: int, db: DB) -> Response:
    """Only ANCHORED versions are downloadable."""
    version = db.get(PassportVersion, version_id)
    if version is None or version.status != "ANCHORED" or not version.pdf_key:
        raise AppError("not_found", "No issued PDF for this version.", 404)
    filename = f"{version.passport_id}-v{version.version_no}.pdf"
    return Response(
        storage.get(version.pdf_key),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
