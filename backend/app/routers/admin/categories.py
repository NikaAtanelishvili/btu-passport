"""Categories and stamps: both admin roles read; writes are super admin only (BE-51)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import SuperAdminUser
from app.db import get_db
from app.models import SkillCategory
from app.schemas.catalog import CategoryCreate, CategoryPatch, CategoryRow
from app.services import catalog, stamps

router = APIRouter(tags=["admin: catalog"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/categories", response_model=list[CategoryRow])
def list_categories(db: DB, include_archived: bool = False) -> list[CategoryRow]:
    stmt = select(SkillCategory).order_by(SkillCategory.badge_code)
    if not include_archived:
        stmt = stmt.where(SkillCategory.archived_at.is_(None))
    return [catalog.category_row(db, c) for c in db.scalars(stmt)]


@router.post("/categories", status_code=201, response_model=CategoryRow)
def create_category(body: CategoryCreate, principal: SuperAdminUser, db: DB) -> CategoryRow:
    """The next BDG-AI-nnn badge code. 409 duplicate_name."""
    return catalog.category_row(db, catalog.create_category(db, principal, body))


@router.patch("/categories/{category_id}", response_model=CategoryRow)
def rename_category(
    category_id: int, body: CategoryPatch, principal: SuperAdminUser, db: DB
) -> CategoryRow:
    return catalog.category_row(db, catalog.rename_category(db, principal, category_id, body))


@router.post("/categories/{category_id}/archive", response_model=CategoryRow)
def archive_category(category_id: int, principal: SuperAdminUser, db: DB) -> CategoryRow:
    category = catalog.set_category_archived(db, principal, category_id, True)
    return catalog.category_row(db, category)


@router.post("/categories/{category_id}/unarchive", response_model=CategoryRow)
def unarchive_category(category_id: int, principal: SuperAdminUser, db: DB) -> CategoryRow:
    category = catalog.set_category_archived(db, principal, category_id, False)
    return catalog.category_row(db, category)


@router.delete("/categories/{category_id}", status_code=204, response_class=Response)
def delete_category(category_id: int, principal: SuperAdminUser, db: DB) -> Response:
    """409 in_use while any skill (archived ones too) is in the category."""
    catalog.delete_category(db, principal, category_id)
    return Response(status_code=204)


@router.post("/categories/{category_id}/stamp", response_model=CategoryRow)
def upload_stamp(
    category_id: int, file: UploadFile, principal: SuperAdminUser, db: DB
) -> CategoryRow:
    """PNG (any shape, longest side at least 300 px) or SVG, at most 1 MB; stored by
    SHA-256. A new stamp appears on future versions only. 422 with `fields.file` otherwise."""
    data = file.file.read(stamps.MAX_BYTES + 1)  # one byte more is enough to say "too big"
    return catalog.category_row(db, catalog.set_stamp(db, principal, category_id, data))
