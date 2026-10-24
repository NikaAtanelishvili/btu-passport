"""Shared fixtures (Backend tab §9). Integration tests use the real `passport_test` database."""

import os
from collections.abc import Iterator

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
