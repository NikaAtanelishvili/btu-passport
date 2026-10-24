"""BE-10: passwordless email-code sign-in (security rules first)."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import LoginCode, User, UserRole, UserSession
from tests import factories as f
from tests.conftest import FakeMailer

STUDENT = "btu-t-0001@example.org"
UNKNOWN = "newcomer@btu.test"


def _client(ip: str = "127.0.0.1") -> TestClient:
    return TestClient(create_app(), client=(ip, 50000))


def _request(client: TestClient, email: str, **headers: str) -> int:
    response = client.post("/auth/request-code", json={"email": email}, headers=headers)
    return int(response.status_code)


def _verify(client: TestClient, email: str, code: str, next_: str | None = None) -> dict[str, Any]:
    body: dict[str, str] = {"email": email, "code": code}
    if next_ is not None:
        body["next"] = next_
    response = client.post("/auth/verify-code", json=body)
    return {"status": response.status_code, **response.json()}


def _wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


@pytest.fixture
def seeded_student(db: Session) -> None:
    f.student(db, 1)
    db.commit()


# --- request-code -----------------------------------------------------------------------


def test_same_response_for_known_and_unknown_email(
    db: Session, fake_mailer: FakeMailer, seeded_student: None
) -> None:
    client = _client()
    known = client.post("/auth/request-code", json={"email": STUDENT})
    unknown = client.post("/auth/request-code", json={"email": UNKNOWN})
    assert known.status_code == unknown.status_code == 204
    assert known.content == unknown.content == b""
    drop = {"date", "content-length"}
    assert {k: v for k, v in known.headers.items() if k not in drop} == {
        k: v for k, v in unknown.headers.items() if k not in drop
    }
    assert [to for to, _ in fake_mailer.sent] == [STUDENT, UNKNOWN]


def test_only_the_code_hash_is_stored(db: Session, fake_mailer: FakeMailer) -> None:
    _request(_client(), UNKNOWN)
    code = fake_mailer.last_code(UNKNOWN)
    assert len(code) == 6 and code.isdigit()
    row = db.scalars(select(LoginCode)).one()
    assert row.code_hash == hashlib.sha256(code.encode()).hexdigest()
    assert code not in row.code_hash
    assert str(row.requested_ip) == "127.0.0.1"
    ttl = row.expires_at - row.created_at
    assert timedelta(minutes=9) < ttl <= timedelta(minutes=10, seconds=5)


def test_email_is_trimmed_and_lower_cased(db: Session, fake_mailer: FakeMailer) -> None:
    assert _request(_client(), "  NewComer@BTU.test ") == 204
    assert fake_mailer.sent[-1][0] == UNKNOWN


def test_domain_not_allowed(db: Session, fake_mailer: FakeMailer) -> None:
    response = _client().post("/auth/request-code", json={"email": "someone@gmail.com"})
    assert response.status_code == 422
    assert response.json()["error"] == "email_domain_not_allowed"
    assert "email" in response.json()["fields"]
    assert fake_mailer.sent == []


def test_rate_limit_per_email(db: Session, fake_mailer: FakeMailer) -> None:
    client = _client()
    assert [_request(client, UNKNOWN) for _ in range(5)] == [204] * 5
    response = client.post("/auth/request-code", json={"email": UNKNOWN})
    assert response.status_code == 429
    assert response.json()["error"] == "rate_limited"
    assert len(fake_mailer.sent) == 5


def test_rate_limit_per_ip(db: Session, fake_mailer: FakeMailer) -> None:
    client = _client("8.8.8.8")
    statuses = [_request(client, f"user{i}@btu.test") for i in range(21)]
    assert statuses == [204] * 20 + [429]
    assert _request(_client("8.8.4.4"), "other@btu.test") == 204  # other IP unaffected


def test_no_ip_limit_when_the_real_ip_is_unknown(db: Session, fake_mailer: FakeMailer) -> None:
    # Through the Next.js dev proxy every caller is 127.0.0.1; an IP limit there would be
    # one shared limit for everybody. The per-email limit still applies.
    client = _client("127.0.0.1")
    assert [_request(client, f"user{i}@btu.test") for i in range(25)] == [204] * 25


def test_old_requests_fall_out_of_the_window(db: Session, fake_mailer: FakeMailer) -> None:
    client = _client()
    for _ in range(5):
        _request(client, UNKNOWN)
    db.execute(update(LoginCode).values(created_at=datetime.now(UTC) - timedelta(minutes=61)))
    db.commit()
    assert _request(client, UNKNOWN) == 204


def test_forwarded_ip_trusted_only_from_a_local_proxy(db: Session, fake_mailer: FakeMailer) -> None:
    # Behind Caddy (a private-network peer) the last X-Forwarded-For hop is the client.
    _request(_client("172.18.0.5"), "a@btu.test", **{"X-Forwarded-For": "6.6.6.6, 203.0.113.9"})
    # A public peer can't choose its own IP.
    _request(_client("8.8.8.8"), "b@btu.test", **{"X-Forwarded-For": "6.6.6.6"})
    ips = dict(db.execute(select(LoginCode.email, LoginCode.requested_ip)).all())
    assert str(ips["a@btu.test"]) == "203.0.113.9"
    assert str(ips["b@btu.test"]) == "8.8.8.8"


# --- verify-code ------------------------------------------------------------------------


def test_right_code_signs_in_and_sets_cookies(
    db: Session, fake_mailer: FakeMailer, seeded_student: None
) -> None:
    client = _client()
    _request(client, STUDENT)
    result = _verify(client, STUDENT, fake_mailer.last_code(STUDENT))
    assert result == {"status": 200, "redirect": "/me"}
    assert client.cookies.get("session") and client.cookies.get("csrf_token")
    user = db.scalars(select(User).where(User.email == STUDENT)).one()
    assert user.display_name == "Nino Test" and user.last_login_at is not None
    assert db.scalars(select(UserSession)).one().user_id == user.user_id


def test_code_cannot_be_reused(db: Session, fake_mailer: FakeMailer) -> None:
    client = _client()
    _request(client, UNKNOWN)
    code = fake_mailer.last_code(UNKNOWN)
    assert _verify(client, UNKNOWN, code)["status"] == 200
    again = _verify(_client(), UNKNOWN, code)
    assert (again["status"], again["error"]) == (400, "code_expired")


def test_wrong_code_counts_attempts(db: Session, fake_mailer: FakeMailer) -> None:
    client = _client()
    _request(client, UNKNOWN)
    wrong = _wrong(fake_mailer.last_code(UNKNOWN))
    first = _verify(client, UNKNOWN, wrong)
    assert (first["status"], first["error"], first["attempts_left"]) == (400, "code_invalid", 4)
    assert db.scalars(select(LoginCode)).one().attempts == 1  # persisted despite the 400


def test_code_dies_after_five_wrong_tries(db: Session, fake_mailer: FakeMailer) -> None:
    client = _client()
    _request(client, UNKNOWN)
    code = fake_mailer.last_code(UNKNOWN)
    lefts = [_verify(client, UNKNOWN, _wrong(code))["attempts_left"] for _ in range(5)]
    assert lefts == [4, 3, 2, 1, 0]
    final = _verify(client, UNKNOWN, code)  # the right code, too late
    assert (final["status"], final["error"]) == (400, "code_expired")
    assert db.scalars(select(UserSession)).first() is None


def test_expired_code_fails(db: Session, fake_mailer: FakeMailer) -> None:
    client = _client()
    _request(client, UNKNOWN)
    db.execute(update(LoginCode).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    result = _verify(client, UNKNOWN, fake_mailer.last_code(UNKNOWN))
    assert (result["status"], result["error"]) == (400, "code_expired")


def test_new_request_kills_older_codes(db: Session, fake_mailer: FakeMailer) -> None:
    client = _client()
    _request(client, UNKNOWN)
    old = fake_mailer.last_code(UNKNOWN)
    _request(client, UNKNOWN)
    new = fake_mailer.last_code(UNKNOWN)
    if old != new:
        assert _verify(client, UNKNOWN, old)["error"] == "code_invalid"
    assert _verify(client, UNKNOWN, new)["status"] == 200


def test_malformed_code_is_422(db: Session, fake_mailer: FakeMailer) -> None:
    response = _client().post("/auth/verify-code", json={"email": UNKNOWN, "code": "12ab"})
    assert response.status_code == 422 and "code" in response.json()["fields"]


@pytest.mark.parametrize(
    ("email", "role", "redirect"),
    [
        ("superadmin@btu.test", "SUPER_ADMIN", "/admin"),
        ("admin@btu.test", "ADMIN", "/admin"),
        (STUDENT, None, "/me"),
        (UNKNOWN, None, "/"),
    ],
)
def test_redirect_by_role(
    db: Session,
    fake_mailer: FakeMailer,
    seeded_student: None,
    email: str,
    role: str | None,
    redirect: str,
) -> None:
    if role:
        db.add(UserRole(email=email, role=role))
        db.commit()
    client = _client()
    _request(client, email)
    assert _verify(client, email, fake_mailer.last_code(email))["redirect"] == redirect


@pytest.mark.parametrize(
    ("next_", "redirect"),
    [
        ("/checkin/abc?t=123", "/checkin/abc?t=123"),
        ("//evil.example/x", "/"),
        ("/\\evil.example", "/"),
        ("https://evil.example", "/"),
        ("javascript:alert(1)", "/"),
    ],
)
def test_next_must_be_a_local_path(
    db: Session, fake_mailer: FakeMailer, next_: str, redirect: str
) -> None:
    client = _client()
    _request(client, UNKNOWN)
    assert _verify(client, UNKNOWN, fake_mailer.last_code(UNKNOWN), next_)["redirect"] == redirect


def test_logout_deletes_session_and_clears_cookies(db: Session, fake_mailer: FakeMailer) -> None:
    client = _client()
    _request(client, UNKNOWN)
    _verify(client, UNKNOWN, fake_mailer.last_code(UNKNOWN))
    csrf = client.cookies.get("csrf_token") or ""
    response = client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 204
    assert db.scalars(select(UserSession)).first() is None
    assert 'session=""' in response.headers.get("set-cookie", "")


def test_dev_log_prints_the_code(
    db: Session, fake_mailer: FakeMailer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="app")
    _request(_client(), UNKNOWN)
    assert fake_mailer.last_code(UNKNOWN) in caplog.text
