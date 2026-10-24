"""`python -m cli bootstrap [--dev-users]`: grant the first super admin (BE-05)."""

import sys

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import UserRole
from app.services import audit

DEV_ADMIN_EMAIL = "admin@btu.test"  # IN-04 test user


def _super_admin_email() -> str:
    return get_settings().bootstrap_super_admin_email


def _grant(db: Session, email: str, role: str) -> bool:
    """Upsert one role; returns True (and writes an audit row) only if something changed."""
    email = email.strip().lower()
    domain = email.rpartition("@")[2]
    if domain not in get_settings().allowed_email_domains:
        sys.exit(f"{email}: domain {domain!r} is not in ALLOWED_EMAIL_DOMAINS")
    existing = db.get(UserRole, email)
    if existing is not None and existing.role == role:
        return False
    before = None if existing is None else {"role": existing.role}
    if existing is None:
        db.add(UserRole(email=email, role=role))
    else:
        existing.role = role
    audit.record(db, None, "role.grant", "user_role", email, before=before, after={"role": role})
    db.flush()
    return True


def run(db: Session, *, dev_users: bool) -> int:
    """Returns the number of roles granted or changed."""
    grants = [(_super_admin_email(), "SUPER_ADMIN")]
    if dev_users:
        grants.append((DEV_ADMIN_EMAIL, "ADMIN"))
    return sum(_grant(db, email, role) for email, role in grants)


def main(*, dev_users: bool) -> None:
    from app.db import SessionLocal

    with SessionLocal() as db, db.begin():
        changed = run(db, dev_users=dev_users)
    print(f"bootstrap: {changed} role(s) granted or changed")
