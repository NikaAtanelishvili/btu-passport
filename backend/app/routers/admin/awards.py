"""Direct awards (BE-24): preview and submit. Both admin roles."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.auth.deps import AdminUser
from app.db import get_db
from app.schemas.award import AwardIn, AwardOut, PreviewOut
from app.services import issuance

router = APIRouter(tags=["admin: awards"])
DB = Annotated[Session, Depends(get_db)]


@router.post("/awards/preview", response_model=PreviewOut)
def preview_award(body: AwardIn, db: DB) -> PreviewOut:
    """What the award would do for each student. No writes."""
    return PreviewOut(rows=issuance.preview_award(db, body))


@router.post("/awards", status_code=202, response_model=AwardOut)
def create_award(
    body: AwardIn,
    principal: AdminUser,
    db: DB,
    idempotency_key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
) -> Any:
    """Award a skill to students. The same Idempotency-Key again returns the stored response."""
    return issuance.create_direct_award(db, principal, body, idempotency_key)
