"""BE-52: admins and roles (FR-01, FR-08, A12). Super admin only. A change or revocation signs
the person out everywhere, and there is always at least one super admin (code and trigger)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import AuditLog, User, UserRole, UserSession

ClientAs = Callable[[str | None], TestClient]
SA = "superadmin@btu.test"


@pytest.fixture
def sa(client_as: ClientAs) -> TestClient:
    return client_as("super_admin")


def _audit(db: Session, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)))


def _sessions(db: Session, email: str) -> int:
    stmt = select(UserSession).join(User, User.user_id == UserSession.user_id)
    return len(db.scalars(stmt.where(User.email == email)).all())


def test_grant_lists_and_audits(db: Session, sa: TestClient) -> None:
    r = sa.put("/api/admin/roles/New.Admin@BTU.test", json={"role": "ADMIN"})
    assert r.status_code == 200, r.text
    row = r.json()
    assert (row["email"], row["role"], row["granted_by_email"]) == (
        "new.admin@btu.test",
        "ADMIN",
        SA,
    )
    assert row["name"] is None and row["last_login_at"] is None  # hasn't signed in yet
    listed = sa.get("/api/admin/roles").json()
    assert [(x["email"], x["role"]) for x in listed] == [
        (SA, "SUPER_ADMIN"),
        ("new.admin@btu.test", "ADMIN"),
    ]
    (entry,) = _audit(db, "role.grant")
    assert (entry.actor_email, entry.entity, entry.entity_id) == (
        SA,
        "user_role",
        "new.admin@btu.test",
    )
    assert (entry.before, entry.after) == (None, {"role": "ADMIN"})


def test_grant_checks_domain_and_role(sa: TestClient) -> None:
    r = sa.put("/api/admin/roles/someone@gmail.com", json={"role": "ADMIN"})
    assert (r.status_code, r.json()["error"]) == (422, "validation_error")
    assert "email" in r.json()["fields"]
    r = sa.put("/api/admin/roles/someone@btu.test", json={"role": "OWNER"})
    assert r.status_code == 422 and "role" in r.json()["fields"]


def test_change_signs_the_person_out(db: Session, client_as: ClientAs, sa: TestClient) -> None:
    admin = client_as("admin")
    assert admin.get("/api/admin/students").status_code == 200
    r = sa.put("/api/admin/roles/admin@btu.test", json={"role": "SUPER_ADMIN"})
    assert (r.status_code, r.json()["role"]) == (200, "SUPER_ADMIN")
    assert _sessions(db, "admin@btu.test") == 0
    assert admin.get("/api/admin/students").status_code == 401  # sign in again for the new role
    (entry,) = _audit(db, "role.grant")
    assert (entry.before, entry.after) == ({"role": "ADMIN"}, {"role": "SUPER_ADMIN"})


def test_same_role_again_changes_nothing(db: Session, client_as: ClientAs, sa: TestClient) -> None:
    admin = client_as("admin")
    assert sa.put("/api/admin/roles/admin@btu.test", json={"role": "ADMIN"}).status_code == 200
    assert admin.get("/api/admin/students").status_code == 200
    assert _audit(db, "role.grant") == []


def test_A12_revoked_admin_is_signed_out_on_next_request(
    db: Session, client_as: ClientAs, sa: TestClient
) -> None:
    admin = client_as("admin")
    assert admin.get("/api/admin/students").status_code == 200
    assert sa.delete("/api/admin/roles/admin@btu.test").status_code == 204
    r = admin.get("/api/admin/students")
    assert (r.status_code, r.json()["error"]) == (401, "unauthenticated")
    assert admin.get("/api/session").json()["authenticated"] is False
    assert db.get(UserRole, "admin@btu.test") is None
    (entry,) = _audit(db, "role.revoke")
    assert (entry.actor_email, entry.before, entry.after) == (SA, {"role": "ADMIN"}, None)
    assert sa.delete("/api/admin/roles/admin@btu.test").status_code == 404


def test_last_super_admin_cant_be_revoked_or_demoted(db: Session, sa: TestClient) -> None:
    r = sa.delete(f"/api/admin/roles/{SA}")
    assert (r.status_code, r.json()["error"]) == (409, "last_super_admin")
    r = sa.put(f"/api/admin/roles/{SA}", json={"role": "ADMIN"})
    assert (r.status_code, r.json()["error"]) == (409, "last_super_admin")
    assert db.get_one(UserRole, SA).role == "SUPER_ADMIN"
    assert _sessions(db, SA) == 1  # nothing happened, still signed in
    # With a second super admin, either may step down.
    assert sa.put("/api/admin/roles/second@btu.test", json={"role": "SUPER_ADMIN"}).is_success
    assert sa.put(f"/api/admin/roles/{SA}", json={"role": "ADMIN"}).status_code == 200
    db.expire_all()
    assert db.get_one(UserRole, SA).role == "ADMIN"


def test_list_marks_the_last_super_admin(sa: TestClient) -> None:
    (only,) = sa.get("/api/admin/roles").json()
    assert only["last_super_admin"] is True
    sa.put("/api/admin/roles/admin2@btu.test", json={"role": "ADMIN"})
    rows = {x["email"]: x["last_super_admin"] for x in sa.get("/api/admin/roles").json()}
    assert rows == {SA: True, "admin2@btu.test": False}


@pytest.mark.parametrize("change", ["delete", "demote"])
def test_trigger_keeps_one_super_admin(db: Session, change: str) -> None:
    db.add(UserRole(email="only@btu.test", role="SUPER_ADMIN"))
    db.commit()
    stmt = (
        delete(UserRole).where(UserRole.email == "only@btu.test")
        if change == "delete"
        else update(UserRole).where(UserRole.email == "only@btu.test").values(role="ADMIN")
    )
    with pytest.raises(DBAPIError, match="last super admin"):
        db.execute(stmt)
    db.rollback()
    db.add(UserRole(email="other@btu.test", role="SUPER_ADMIN"))
    db.commit()
    db.execute(stmt)  # fine once another super admin exists
    db.commit()
