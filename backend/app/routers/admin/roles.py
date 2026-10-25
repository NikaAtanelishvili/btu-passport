"""Admins and roles (BE-52): super admin only."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.deps import SuperAdminUser
from app.db import get_db
from app.schemas.role import RoleIn, RoleRow
from app.services import roles

router = APIRouter(tags=["admin: roles"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/roles", response_model=list[RoleRow])
def list_roles(principal: SuperAdminUser, db: DB) -> list[RoleRow]:
    return roles.list_roles(db)


@router.put("/roles/{email}", response_model=RoleRow)
def grant_role(email: str, body: RoleIn, principal: SuperAdminUser, db: DB) -> RoleRow:
    """Grant or change; BTU domains only. A change signs the person out everywhere.
    409 last_super_admin when it would leave no super admin."""
    return roles.grant(db, principal, email, body.role)


@router.delete("/roles/{email}", status_code=204, response_class=Response)
def revoke_role(email: str, principal: SuperAdminUser, db: DB) -> Response:
    """Signs the person out on their next request (A12). 409 last_super_admin."""
    roles.revoke(db, principal, email)
    return Response(status_code=204)
