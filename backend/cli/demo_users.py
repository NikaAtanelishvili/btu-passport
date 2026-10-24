"""`python -m cli demo-users`: demo accounts with real inboxes (README, "Demo accounts").

Reads DEMO_SUPER_ADMIN_EMAIL, DEMO_ADMIN_EMAIL and DEMO_STUDENT_EMAIL (plus the student's
ID and name) from the environment. Their domains must be in ALLOWED_EMAIL_DOMAINS, which
only the demo env file extends; with the dev domains this command refuses. Re-running
changes nothing.
"""

import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Student
from app.schemas.student import StudentCreate
from app.services import students
from cli.bootstrap import grant


@dataclass(frozen=True)
class DemoAccounts:
    super_admin: str
    admin: str
    student: str
    student_id: str
    student_first_name: str
    student_last_name: str


def from_settings() -> DemoAccounts:
    s = get_settings()
    return DemoAccounts(
        super_admin=s.demo_super_admin_email,
        admin=s.demo_admin_email,
        student=s.demo_student_email,
        student_id=s.demo_student_id,
        student_first_name=s.demo_student_first_name,
        student_last_name=s.demo_student_last_name,
    )


def _check(accounts: DemoAccounts) -> None:
    """Every email given and on an allowed domain, before anything is written."""
    domains = get_settings().allowed_email_domains
    for var, email in (
        ("DEMO_SUPER_ADMIN_EMAIL", accounts.super_admin),
        ("DEMO_ADMIN_EMAIL", accounts.admin),
        ("DEMO_STUDENT_EMAIL", accounts.student),
    ):
        email = email.strip().lower()
        if not email:
            sys.exit(f"{var} is not set; put a real inbox in the demo env file")
        domain = email.rpartition("@")[2]
        if domain not in domains:
            sys.exit(
                f"{var}={email}: domain {domain!r} is not in ALLOWED_EMAIL_DOMAINS; "
                "add it in the demo env file only"
            )


def _student(db: Session, accounts: DemoAccounts) -> bool:
    """Registers the demo student (with their one passport) unless that email exists."""
    email = accounts.student.strip().lower()
    if db.scalar(select(Student).where(Student.email == email)) is not None:
        return False
    existing = db.get(Student, accounts.student_id.strip().upper())
    if existing is not None:
        sys.exit(
            f"DEMO_STUDENT_ID={existing.student_id} already belongs to {existing.email}; "
            "choose a free Student ID"
        )
    body = StudentCreate(
        student_id=accounts.student_id,
        first_name=accounts.student_first_name,
        last_name=accounts.student_last_name,
        email=email,
        program="Information Technologies",
        education_level="BACHELOR",
        status="ACTIVE",
    )
    students.create_student(db, None, body)
    return True


def run(db: Session, accounts: DemoAccounts) -> int:
    """Returns the number of roles and students created or changed."""
    _check(accounts)
    return sum(
        (
            grant(db, accounts.super_admin, "SUPER_ADMIN"),
            grant(db, accounts.admin, "ADMIN"),
            _student(db, accounts),
        )
    )


def main() -> None:
    from app.db import SessionLocal

    accounts = from_settings()
    with SessionLocal() as db, db.begin():
        changed = run(db, accounts)
    print(f"demo-users: {changed} account(s) created or changed")
    print(f"  super admin {accounts.super_admin.lower()}, admin {accounts.admin.lower()}")
    print(f"  student {accounts.student.lower()} ({accounts.student_id.upper()})")
