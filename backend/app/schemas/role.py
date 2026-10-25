"""Admins and roles schemas (BE-52)."""

from datetime import datetime

from pydantic import BaseModel


class RoleRow(BaseModel):
    email: str
    role: str  # "SUPER_ADMIN" | "ADMIN"
    name: str | None  # None until the person first signs in
    granted_by_email: str | None  # None for bootstrap / the CLI
    granted_at: datetime
    last_login_at: datetime | None
    last_super_admin: bool  # the page disables Revoke and demotion for this row


class RoleIn(BaseModel):
    role: str
