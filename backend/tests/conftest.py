"""Shared fixtures (Backend tab §9). Integration tests use the real `passport_test` database."""

import os
from collections.abc import Callable, Iterator
from typing import Any

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
# Sign in with Google off and no exceptions, whatever .env says; BE-15 tests switch it on.
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""
os.environ["ALLOWED_EMAILS"] = ""
os.environ["DEV_SUPER_ADMIN_EMAILS"] = ""
# No Google Sheet and no write-back, whatever .env says; the live smoke test (SH-13) reads the
# real Sheet ID from .env itself and runs only when it is set.
os.environ["GOOGLE_SHEETS_ID"] = ""
os.environ["SHEET_WRITEBACK"] = "false"

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


@pytest.fixture
def seeded(db: Session, s3_bucket: str) -> Session:
    """The real seed CSV imported: 18 students, 60 awards, 8 LEGACY versions."""
    from cli import seed

    seed.run(db)
    db.commit()
    return db


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


@pytest.fixture
def boss(db: Session) -> Any:
    """A super admin Principal for calling services directly (actor of audit rows)."""
    from app.auth import sessions
    from app.auth.deps import Principal
    from app.models import UserRole
    from tests import factories

    user = factories.user(db, "superadmin@btu.test")
    db.add(UserRole(email=user.email, role="SUPER_ADMIN"))
    _, row = sessions.create_session(db, user)
    db.flush()
    return Principal(user=user, role="SUPER_ADMIN", student=None, session=row)


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


@pytest.fixture
def run_jobs() -> Callable[[], int]:
    """Drain the job queue: run ready jobs (and the anchor tick) until nothing is left to do.
    Jobs backing off after a failure wait for their run_after, so this stops there."""
    from worker import loop, ticks

    def drain() -> int:
        ran = 0
        while True:
            with SessionLocal() as session:
                ticks.anchor_tick(session)
                session.commit()
            if not loop.run_once():
                return ran
            ran += 1

    return drain


class FakeSigner:
    """In-process stand-in for the signer (BE-28 tests): records roots and returns a fake
    receipt, or fails while `fail` is set. A root seen before returns the first receipt."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.fail = False
        self.receipts: dict[str, Any] = {}

    def anchor_root(self, root: str, leaf_count: int) -> Any:
        import dataclasses
        import hashlib
        from datetime import UTC, datetime

        from app.services.anchoring import AnchorError, AnchorReceipt

        self.calls.append((root, leaf_count))
        if self.fail:
            raise AnchorError("signer unreachable: connection refused")
        if root in self.receipts:
            return dataclasses.replace(self.receipts[root], already_anchored=True)
        receipt = AnchorReceipt(
            tx_hash="0x" + hashlib.sha256(root.encode()).hexdigest(),
            block_number=len(self.receipts) + 1,
            anchored_at=datetime.now(UTC).replace(microsecond=0),
            already_anchored=False,
        )
        self.receipts[root] = receipt
        return receipt


@pytest.fixture
def fake_signer(monkeypatch: pytest.MonkeyPatch) -> FakeSigner:
    from app.services import anchoring

    fake = FakeSigner()
    monkeypatch.setattr(anchoring, "anchor_root", fake.anchor_root)
    return fake


class FakeChain:
    """Stand-in for app/services/chain.py (BE-30 tests): a root is anchored when the fake
    signer anchored it (or it was added to `roots`); `owner` and `revoked` can be changed."""

    def __init__(self, signer: FakeSigner) -> None:
        from app.config import get_settings

        self.signer = signer
        self.roots: dict[str, int] = {}
        self.owner_address: str | None = get_settings().issuer_address
        self.revoked: set[str] = set()
        self.down = False

    def _up(self) -> None:
        from app.services.chain import ChainUnavailable

        if self.down:
            raise ChainUnavailable("RPC unreachable: connection refused")

    def anchored_at(self, root: str) -> int:
        self._up()
        if root in self.roots:
            return self.roots[root]
        receipt = self.signer.receipts.get(root)
        return int(receipt.anchored_at.timestamp()) if receipt else 0

    def owner(self) -> str | None:
        self._up()
        return self.owner_address

    def is_revoked(self, leaf: str) -> bool:
        self._up()
        return leaf in self.revoked


@pytest.fixture
def fake_chain(monkeypatch: pytest.MonkeyPatch, fake_signer: FakeSigner) -> FakeChain:
    from app.services import chain

    fake = FakeChain(fake_signer)
    monkeypatch.setattr(chain, "anchored_at", fake.anchored_at)
    monkeypatch.setattr(chain, "owner", fake.owner)
    monkeypatch.setattr(chain, "is_revoked", fake.is_revoked)
    return fake
