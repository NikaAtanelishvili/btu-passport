"""BE-05: `python -m cli bootstrap [--dev-users]`."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, UserRole
from cli import bootstrap


def _roles(db: Session) -> dict[str, str]:
    return {r.email: r.role for r in db.scalars(select(UserRole))}


def test_grants_super_admin_and_audits_with_null_actor(db: Session) -> None:
    assert bootstrap.run(db, dev_users=False) == 1
    assert _roles(db) == {"superadmin@btu.test": "SUPER_ADMIN"}
    row = db.scalars(select(AuditLog)).one()
    assert (row.actor_user_id, row.actor_email) == (None, None)
    assert (row.action, row.entity, row.entity_id) == (
        "role.grant",
        "user_role",
        "superadmin@btu.test",
    )
    assert (row.before, row.after) == (None, {"role": "SUPER_ADMIN"})


def test_dev_users_adds_admin(db: Session) -> None:
    bootstrap.run(db, dev_users=True)
    assert _roles(db) == {"superadmin@btu.test": "SUPER_ADMIN", "admin@btu.test": "ADMIN"}


def test_rerun_changes_nothing(db: Session) -> None:
    bootstrap.run(db, dev_users=True)
    db.commit()
    assert bootstrap.run(db, dev_users=True) == 0
    assert len(db.scalars(select(AuditLog)).all()) == 2


def test_upsert_restores_a_changed_role(db: Session) -> None:
    db.add(UserRole(email="superadmin@btu.test", role="ADMIN"))
    db.commit()
    assert bootstrap.run(db, dev_users=False) == 1
    assert _roles(db)["superadmin@btu.test"] == "SUPER_ADMIN"
    row = db.scalars(select(AuditLog)).one()
    assert (row.before, row.after) == ({"role": "ADMIN"}, {"role": "SUPER_ADMIN"})


def test_email_is_lower_cased_and_domain_checked(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "_super_admin_email", lambda: "Boss@BTU.test")
    bootstrap.run(db, dev_users=False)
    assert _roles(db) == {"boss@btu.test": "SUPER_ADMIN"}

    monkeypatch.setattr(bootstrap, "_super_admin_email", lambda: "boss@gmail.com")
    with pytest.raises(SystemExit, match="ALLOWED_EMAIL_DOMAINS"):
        bootstrap.run(db, dev_users=False)
