"""Demo accounts with real inboxes: `python -m cli demo-users` (README, demo setup)."""

import dataclasses

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Passport, Student, UserRole
from cli import demo_users

ACCOUNTS = demo_users.DemoAccounts(
    super_admin="Nika.Boss@realmail.example",
    admin="ops@realmail.example",
    student="learner@uni.example",
    student_id="BTU-T-0900",
    student_first_name="Demo",
    student_last_name="Student",
)
DOMAINS = ["btu.edu.ge", "btu.test", "example.org", "realmail.example", "uni.example"]


@pytest.fixture
def demo_domains(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "allowed_email_domains", DOMAINS)


def _roles(db: Session) -> dict[str, str]:
    return {r.email: r.role for r in db.scalars(select(UserRole))}


def test_creates_roles_and_a_student_with_one_passport(db: Session, demo_domains: None) -> None:
    assert demo_users.run(db, ACCOUNTS) == 3
    assert _roles(db) == {
        "nika.boss@realmail.example": "SUPER_ADMIN",
        "ops@realmail.example": "ADMIN",
    }
    student = db.get(Student, "BTU-T-0900")
    assert student is not None and student.email == "learner@uni.example"
    passports = db.scalars(select(Passport).where(Passport.student_id == "BTU-T-0900")).all()
    assert len(passports) == 1
    actions = sorted(a.action for a in db.scalars(select(AuditLog)))
    assert actions == ["role.grant", "role.grant", "student.create"]
    assert all(a.actor_email is None for a in db.scalars(select(AuditLog)))  # the system


def test_rerun_changes_nothing(db: Session, demo_domains: None) -> None:
    demo_users.run(db, ACCOUNTS)
    db.commit()
    audit_rows = db.scalar(select(func.count()).select_from(AuditLog))
    assert demo_users.run(db, ACCOUNTS) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == audit_rows


def test_domain_must_be_allowed(db: Session) -> None:
    # The dev domains only: real inboxes are allowed in the demo env, not here.
    with pytest.raises(SystemExit, match="ALLOWED_EMAIL_DOMAINS"):
        demo_users.run(db, ACCOUNTS)
    assert _roles(db) == {} and db.get(Student, "BTU-T-0900") is None


def test_every_account_is_required(db: Session, demo_domains: None) -> None:
    with pytest.raises(SystemExit, match="DEMO_ADMIN_EMAIL"):
        demo_users.run(db, dataclasses.replace(ACCOUNTS, admin=""))


def test_student_id_taken_by_someone_else(db: Session, demo_domains: None) -> None:
    from tests import factories

    factories.student(db, 900)  # BTU-T-0900 with another email
    with pytest.raises(SystemExit, match="BTU-T-0900"):
        demo_users.run(db, ACCOUNTS)
