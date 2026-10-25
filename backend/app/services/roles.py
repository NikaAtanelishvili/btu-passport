"""Admins and roles (BE-52; FR-01, FR-08). A grant, change or revocation signs the person out
everywhere, so their next request runs with the new role or none (A12). There is always at
least one super admin: checked here (409 last_super_admin) and by the keep_a_super_admin
trigger, both after locking every SUPER_ADMIN row so concurrent revocations take turns."""

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.auth import sessions
from app.config import get_settings
from app.errors import AppError
from app.models import User, UserRole
from app.models.base import ROLES
from app.schemas.role import RoleRow
from app.services import audit

if TYPE_CHECKING:
    from app.auth.deps import Principal


def _lock_super_admins(db: Session) -> list[str]:
    stmt = (
        select(UserRole.email)
        .where(UserRole.role == "SUPER_ADMIN")
        .order_by(UserRole.email)
        .with_for_update()
    )
    return list(db.scalars(stmt))


def _last_super_admin() -> AppError:
    return AppError(
        "last_super_admin",
        "This is the last super admin. Make someone else a super admin first.",
        409,
    )


def list_roles(db: Session) -> list[RoleRow]:
    granter = aliased(User)
    rows = db.execute(
        select(UserRole, User, granter.email)
        .outerjoin(User, User.email == UserRole.email)
        .outerjoin(granter, granter.user_id == UserRole.granted_by)
        .order_by(UserRole.role.desc(), UserRole.email)  # SUPER_ADMIN first
    ).all()
    supers = sum(1 for role, _, _ in rows if role.role == "SUPER_ADMIN")
    return [
        RoleRow(
            email=role.email,
            role=role.role,
            name=user.display_name if user else None,
            granted_by_email=granted_by,
            granted_at=role.granted_at,
            last_login_at=user.last_login_at if user else None,
            last_super_admin=role.role == "SUPER_ADMIN" and supers == 1,
        )
        for role, user, granted_by in rows
    ]


def _row(db: Session, email: str) -> RoleRow:
    return next(r for r in list_roles(db) if r.email == email)


def grant(db: Session, actor: "Principal", raw_email: str, role: str) -> RoleRow:
    email = raw_email.strip().lower()
    fields = {}
    domain = email.rpartition("@")[2]
    if "@" not in email or domain not in get_settings().allowed_email_domains:
        fields["email"] = "Use a BTU email address."
    if role not in ROLES:
        fields["role"] = "Choose Admin or Super admin."
    if fields:
        raise AppError("validation_error", "Some fields are invalid.", 422, fields)

    supers = _lock_super_admins(db)
    existing = db.get(UserRole, email)
    if existing is not None and existing.role == role:
        return _row(db, email)
    if existing is not None and existing.role == "SUPER_ADMIN" and supers == [email]:
        raise _last_super_admin()
    before = None if existing is None else {"role": existing.role}
    if existing is None:
        db.add(UserRole(email=email, role=role, granted_by=actor.user.user_id))
    else:
        existing.role, existing.granted_by = role, actor.user.user_id
        existing.granted_at = func.now()
    db.flush()
    sessions.revoke_user_sessions(db, email)  # next request runs with the new role
    audit.record(db, actor, "role.grant", "user_role", email, before, {"role": role})
    db.flush()
    db.expire_all()
    return _row(db, email)


def revoke(db: Session, actor: "Principal", raw_email: str) -> None:
    email = raw_email.strip().lower()
    supers = _lock_super_admins(db)
    existing = db.get(UserRole, email)
    if existing is None:
        raise AppError("not_found", "This person has no admin role.", 404)
    if existing.role == "SUPER_ADMIN" and supers == [email]:
        raise _last_super_admin()
    before = {"role": existing.role}
    db.delete(existing)
    db.flush()
    sessions.revoke_user_sessions(db, email)  # signed out on their next request (A12)
    audit.record(db, actor, "role.revoke", "user_role", email, before=before)
    db.flush()
