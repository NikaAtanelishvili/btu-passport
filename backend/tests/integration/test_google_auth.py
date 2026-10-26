"""BE-15: Sign in with Google (OIDC code flow + PKCE) against a fake Google: the token
endpoint and JWKS are patched in-process, so no request leaves the machine."""

import base64
import hashlib
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
import time_machine
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import google
from app.config import Settings, get_settings
from app.main import create_app
from app.models import EventParticipant, User, UserRole, UserSession
from tests import factories

CLIENT_ID = "test-client.apps.googleusercontent.com"
STAFF = "nino@btu.edu.ge"
GMAIL = "someone@gmail.com"
NOW = datetime(2026, 10, 21, 11, 45, 0, tzinfo=UTC)  # inside the check-in event's window


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeGoogle:
    """Google's token endpoint and JWKS. The ID token carries `claims` (plus iss, aud, exp,
    iat, sub and the nonce sent to /authorize), signed with `key` under kid "k1"."""

    def __init__(self) -> None:
        self.key = _key()
        self.claims: dict[str, Any] = {"email": STAFF, "email_verified": True, "hd": "btu.edu.ge"}
        self.nonce = ""
        self.challenge = ""
        self.sign_with: rsa.RSAPrivateKey | None = None  # a key Google doesn't publish
        self.down = False
        self.token_requests: list[dict[str, str]] = []

    def authorize(self, location: str) -> str:
        """What the browser does at Google: returns `state`, remembers nonce and challenge."""
        url = urlsplit(location)
        assert f"{url.scheme}://{url.netloc}{url.path}" == google.AUTH_URL
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        assert q["client_id"] == CLIENT_ID
        assert q["redirect_uri"] == "http://localhost:3000/auth/google/callback"
        assert (q["response_type"], q["scope"]) == ("code", "openid email profile")
        assert q["code_challenge_method"] == "S256"
        self.nonce, self.challenge = q["nonce"], q["code_challenge"]
        return q["state"]

    def id_token(self, **overrides: Any) -> str:
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "sub": "1234567890",
            "iat": now,
            "exp": now + 3600,
            "nonce": self.nonce,
            **self.claims,
            **overrides,
        }
        claims = {k: v for k, v in claims.items() if v is not None}
        key = self.sign_with or self.key
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})

    def post(self, url: str, *, data: dict[str, str], **_: Any) -> httpx.Response:
        assert url == google.TOKEN_URL
        if self.down:
            raise httpx.ConnectError("connection refused")
        self.token_requests.append(data)
        request = httpx.Request("POST", url)
        verifier = data["code_verifier"]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        if challenge.rstrip(b"=").decode() != self.challenge or data["code"] != "good-code":
            return httpx.Response(400, json={"error": "invalid_grant"}, request=request)
        body = {"id_token": self.id_token(), "token_type": "Bearer"}
        return httpx.Response(200, json=body, request=request)

    def get(self, url: str, **_: Any) -> httpx.Response:
        assert url == google.JWKS_URL
        if self.down:
            raise httpx.ConnectError("connection refused")
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        keys = {"keys": [{**jwk, "kid": "k1", "alg": "RS256"}]}
        return httpx.Response(200, json=keys, request=httpx.Request("GET", url))


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(s, "google_client_secret", type(s.google_client_secret)("shh"))
    monkeypatch.setattr(s, "public_base_url", "http://localhost:3000")
    monkeypatch.setattr(s, "allowed_email_domains", ["btu.edu.ge", "btu.test", "example.org"])
    monkeypatch.setattr(s, "allowed_emails", [])
    return s


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Iterator[FakeGoogle]:
    fake = FakeGoogle()
    monkeypatch.setattr(httpx, "post", fake.post)
    monkeypatch.setattr(httpx, "get", fake.get)
    google.reset_jwks_cache()
    google.reset_rate_limits()
    yield fake
    google.reset_jwks_cache()
    google.reset_rate_limits()


def _client(ip: str = "127.0.0.1") -> TestClient:
    return TestClient(create_app(), client=(ip, 50000), follow_redirects=False)


def _start(client: TestClient, next_: str | None = None) -> httpx.Response:
    r: httpx.Response = client.get("/auth/google/start", params={"next": next_} if next_ else {})
    return r


def _login(
    client: TestClient, fake: FakeGoogle, next_: str | None = None, code: str = "good-code"
) -> httpx.Response:
    """Start, consent at the fake Google, come back to the callback."""
    started = _start(client, next_)
    assert started.status_code == 303, started.text
    state = fake.authorize(started.headers["location"])
    r: httpx.Response = client.get("/auth/google/callback", params={"code": code, "state": state})
    return r


def _error(response: httpx.Response) -> str | None:
    assert response.status_code == 303, response.text
    url = urlsplit(response.headers["location"])
    assert url.path == "/login", response.headers["location"]
    return parse_qs(url.query).get("error", [None])[0]


def _sessions(db: Session) -> int:
    return len(db.scalars(select(UserSession)).all())


# --- the happy path ---------------------------------------------------------------------


def test_valid_login_signs_in_like_verify_code(db: Session, fake: FakeGoogle) -> None:
    db.add(UserRole(email=STAFF, role="ADMIN"))
    db.commit()
    client = _client()
    r = _login(client, fake)
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/admin"
    assert client.cookies.get("session") and client.cookies.get("csrf_token")
    assert client.get("/api/session").json()["user"]["email"] == STAFF
    user = db.scalars(select(User).where(User.email == STAFF)).one()
    assert user.last_login_at is not None
    # PKCE: the verifier went to the token endpoint, never in a URL
    assert fake.token_requests[0]["code_verifier"]
    assert fake.token_requests[0]["client_secret"] == "shh"


def test_start_sets_a_short_lived_signed_httponly_cookie(fake: FakeGoogle) -> None:
    r = _start(_client(), "/me")
    cookie = r.headers["set-cookie"].lower()
    assert cookie.startswith(f"{google.FLOW_COOKIE}=")
    for part in ("httponly", "samesite=lax", "path=/auth/google", "max-age=600"):
        assert part in cookie, (part, cookie)
    value = r.cookies[google.FLOW_COOKIE]
    flow = google.read_flow(value)
    assert flow is not None and flow.next == "/me"
    assert google.read_flow(value + "x") is None  # tampered signature


def test_next_is_honoured_and_validated(db: Session, fake: FakeGoogle) -> None:
    assert _login(_client(), fake, "/checkin/abc").headers["location"] == "/checkin/abc"
    for bad in ("//evil.example", "https://evil.example", "/\\evil"):
        assert _login(_client(), fake, bad).headers["location"] == "/"  # unknown user, no role


def test_cancel_on_google(fake: FakeGoogle) -> None:
    client = _client()
    _start(client, "/me")
    r = client.get("/auth/google/callback", params={"error": "access_denied"})
    assert _error(r) == "google_cancelled"
    assert parse_qs(urlsplit(r.headers["location"]).query)["next"] == ["/me"]


# --- the security checks ----------------------------------------------------------------


def test_bad_state(db: Session, fake: FakeGoogle) -> None:
    client = _client()
    fake.authorize(_start(client).headers["location"])
    r = client.get("/auth/google/callback", params={"code": "good-code", "state": "forged"})
    assert _error(r) == "google_failed"
    assert fake.token_requests == []  # refused before the code is spent
    assert _sessions(db) == 0


def test_callback_without_the_flow_cookie(db: Session, fake: FakeGoogle) -> None:
    state = fake.authorize(_start(_client()).headers["location"])
    r = _client().get("/auth/google/callback", params={"code": "good-code", "state": state})
    assert _error(r) == "google_failed"
    assert _sessions(db) == 0


def test_flow_cookie_expires_after_10_minutes(db: Session, fake: FakeGoogle) -> None:
    client = _client()
    with time_machine.travel(time.time(), tick=False) as clock:
        state = fake.authorize(_start(client).headers["location"])
        clock.shift(timedelta(minutes=10, seconds=1))
        r = client.get("/auth/google/callback", params={"code": "good-code", "state": state})
    assert _error(r) == "google_failed"


def test_bad_code(db: Session, fake: FakeGoogle) -> None:
    assert _error(_login(_client(), fake, code="used-code")) == "google_failed"
    assert _sessions(db) == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "someone-elses-client.apps.googleusercontent.com"},
        {"iss": "https://evil.example"},
        {"exp": 1},
        {"nonce": "replayed"},
        {"exp": None},
    ],
    ids=["foreign-aud", "foreign-iss", "expired", "wrong-nonce", "no-exp"],
)
def test_bad_id_token(db: Session, fake: FakeGoogle, overrides: dict[str, Any]) -> None:
    fake.claims.update(overrides)
    assert _error(_login(_client(), fake)) == "google_failed"
    assert _sessions(db) == 0


def test_id_token_signed_with_another_key(db: Session, fake: FakeGoogle) -> None:
    fake.sign_with = _key()
    assert _error(_login(_client(), fake)) == "google_failed"
    assert _sessions(db) == 0


def test_email_not_verified(db: Session, fake: FakeGoogle) -> None:
    fake.claims["email_verified"] = False
    assert _error(_login(_client(), fake)) == "google_not_allowed"
    assert _sessions(db) == 0


def test_disallowed_domain(db: Session, fake: FakeGoogle) -> None:
    fake.claims = {"email": GMAIL, "email_verified": True}
    assert _error(_login(_client(), fake)) == "google_not_allowed"
    assert _sessions(db) == 0


def test_btu_address_without_hd(db: Session, fake: FakeGoogle) -> None:
    """A consumer Google account registered with a btu.edu.ge address isn't BTU's."""
    fake.claims.pop("hd")
    assert _error(_login(_client(), fake)) == "google_not_allowed"
    fake.claims["hd"] = "other.edu"
    assert _error(_login(_client(), fake)) == "google_not_allowed"
    assert _sessions(db) == 0


def test_other_allowed_domain_needs_no_hd(db: Session, fake: FakeGoogle) -> None:
    fake.claims = {"email": "Admin@BTU.test", "email_verified": True}
    assert _login(_client(), fake).headers["location"] == "/"
    assert db.scalars(select(User.email)).all() == ["admin@btu.test"]


def test_allowed_emails_exception(
    db: Session, fake: FakeGoogle, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.claims = {"email": GMAIL, "email_verified": True}
    assert _error(_login(_client(), fake)) == "google_not_allowed"
    monkeypatch.setattr(settings, "allowed_emails", [GMAIL])
    db.add(UserRole(email=GMAIL, role="SUPER_ADMIN"))
    db.commit()
    client = _client()
    assert _login(client, fake).headers["location"] == "/admin"
    assert client.get("/api/session").json()["role"] == "SUPER_ADMIN"
    # the exception is the exact address only, and still needs a verified email
    fake.claims = {"email": "someone.else@gmail.com", "email_verified": True}
    assert _error(_login(_client(), fake)) == "google_not_allowed"
    fake.claims = {"email": GMAIL, "email_verified": False}
    assert _error(_login(_client(), fake)) == "google_not_allowed"


def test_google_unavailable(db: Session, fake: FakeGoogle) -> None:
    fake.down = True
    assert _error(_login(_client(), fake)) == "google_unavailable"
    assert _sessions(db) == 0


def test_unexpected_failure_is_not_a_500(
    db: Session, fake: FakeGoogle, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_: object) -> str:
        raise RuntimeError("bug")

    monkeypatch.setattr(google, "allowed_email", boom)
    assert _error(_login(_client(), fake)) == "google_failed"


def test_rate_limited_per_ip(
    fake: FakeGoogle, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "login_rate_per_ip_hour", 2)
    client = _client("203.0.113.7")
    assert _start(client).headers["location"].startswith(google.AUTH_URL)
    assert _start(client).headers["location"].startswith(google.AUTH_URL)
    assert _error(_start(client)) == "google_rate_limited"
    assert _start(_client("203.0.113.8")).headers["location"].startswith(google.AUTH_URL)
    for _ in range(2):
        _client("203.0.113.9").get("/auth/google/callback", params={"error": "access_denied"})
    r = _client("203.0.113.9").get("/auth/google/callback", params={"error": "access_denied"})
    assert _error(r) == "google_rate_limited"


# --- check-in pass and the disabled state -----------------------------------------------


def test_checkin_pass_completes_after_google_sign_in(db: Session, fake: FakeGoogle) -> None:
    from app.services import qr_tokens

    skill = factories.skill(db, "SKL-001")
    event = factories.event(db, skill, factories.user(db, "org@btu.test"), status="CHECKIN_OPEN")
    db.commit()
    url = f"/api/checkin/{event.event_id}"
    browser = _client()
    t = qr_tokens.token(event.qr_secret, event.event_id, qr_tokens.window(NOW))
    with time_machine.travel(NOW, tick=False) as clock:
        assert browser.post(f"{url}/pass", json={"t": t}).status_code == 200
        clock.shift(timedelta(minutes=3))  # the QR token is long dead; the pass isn't
        landed = _login(browser, fake, f"/checkin/{event.event_id}")
        assert landed.headers["location"] == f"/checkin/{event.event_id}"
        browser.headers["X-CSRF-Token"] = browser.cookies["csrf_token"]
        assert browser.get(url).json()["state"] == "CONFIRM"
        done = browser.post(url, json={})
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "CHECKED_IN"
    row = db.scalars(select(EventParticipant)).one()
    assert (row.email, row.method) == (STAFF, "QR")


def test_disabled_without_client_id(db: Session) -> None:
    assert get_settings().google_client_id == ""
    client = _client()
    assert client.get("/auth/providers").json() == {"google": False}
    assert client.get("/auth/google/start").status_code == 404
    assert client.get("/auth/google/callback", params={"code": "x"}).status_code == 404


def test_providers_when_enabled(fake: FakeGoogle) -> None:
    assert _client().get("/auth/providers").json() == {"google": True}


def test_settings_refuse_a_client_id_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    with pytest.raises(ValueError, match="GOOGLE_CLIENT_SECRET"):
        Settings()
