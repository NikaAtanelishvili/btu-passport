"""Shared fixtures (Backend tab §9). Integration tests use the real `passport_test` database."""

import os
from collections.abc import Callable, Iterator

from sqlalchemy.engine import make_url

# Point everything at the test database and bucket before any settings are read.
_dev_url = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://passport:passport@localhost:5432/passport"
)
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or make_url(_dev_url).set(
    database="passport_test"
).render_as_string(hide_password=False)
os.environ["S3_BUCKET"] = "passports-test"
os.environ.setdefault("S3_SECRET_KEY", "minio-secret")
os.environ.setdefault("SIGNER_HMAC_SECRET", "test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal, get_engine  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def _migrated() -> None:
    """Fresh schema once per test session: drop everything, then `alembic upgrade head`."""
    from alembic import command
    from alembic.config import Config

    engine = get_engine()
    assert engine.url.database == "passport_test", engine.url
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini")), "head")


@pytest.fixture
def db(_migrated: None) -> Iterator[Session]:
    """A session on a clean database; tables are truncated after each test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        with get_engine().begin() as conn:
            conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
            conn.execute(text("ALTER SEQUENCE passport_number_seq RESTART WITH 1"))


@pytest.fixture(scope="session")
def s3_bucket() -> str:
    """The test bucket in the dev MinIO, created if missing. Keys are content-addressed."""
    from app.config import get_settings
    from app.services import storage

    bucket = get_settings().s3_bucket
    assert bucket == "passports-test"
    storage.ensure_bucket()
    return bucket


ROLE_EMAILS = {
    "super_admin": "superadmin@btu.test",
    "admin": "admin@btu.test",
    "student": "btu-t-0001@example.org",
    "unregistered": "newcomer@btu.test",
}


@pytest.fixture
def client_as(db: Session) -> Callable[[str | None], TestClient]:
    """`client_as("admin")`: a TestClient with a real session row and CSRF cookie + header.

    Skips the email-code flow by inserting the session directly. Roles: super_admin, admin,
    student (BTU-T-0001 with a passport), unregistered (BTU email, no student), None.
    """
    from app.auth import sessions
    from app.config import get_settings
    from app.main import create_app
    from app.models import User, UserRole
    from tests import factories

    def make(role: str | None) -> TestClient:
        client = TestClient(create_app())
        if role is None:
            return client
        email = ROLE_EMAILS[role]
        if role == "student":
            factories.student(db, 1)
        if role in ("super_admin", "admin"):
            db.add(UserRole(email=email, role=role.upper()))
        user = db.query(User).filter_by(email=email).one_or_none() or factories.user(db, email)
        token, row = sessions.create_session(db, user)
        db.commit()
        client.cookies.set(get_settings().session_cookie_name, token)
        client.cookies.set(sessions.CSRF_COOKIE, row.csrf_token)
        client.headers["X-CSRF-Token"] = row.csrf_token
        return client

    return make


class FakeMailer:
    """Records sign-in codes instead of sending email (BE-10 tests)."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_login_code(self, email: str, code: str) -> None:
        self.sent.append((email, code))

    def last_code(self, email: str) -> str:
        return next(code for to, code in reversed(self.sent) if to == email)


@pytest.fixture
def fake_mailer(monkeypatch: pytest.MonkeyPatch) -> FakeMailer:
    from app.services import mailer

    fake = FakeMailer()
    monkeypatch.setattr(mailer, "send_login_code", fake.send_login_code)
    return fake
