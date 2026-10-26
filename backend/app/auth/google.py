"""Sign in with Google (BE-15): OpenID Connect authorization code flow with PKCE.

The browser carries the flow's secrets (state, nonce, PKCE verifier, `next`) between
/auth/google/start and /auth/google/callback in one signed HttpOnly cookie, so nothing is
stored server side. Google's ID token is verified here with PyJWT against Google's JWKS;
the sign-in itself then follows the email-code path (users row, session, cookies).

Every failure is a GoogleSignInError whose code the /login page turns into a message.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.config import get_settings

log = logging.getLogger("app.auth")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
SCOPES = "openid email profile"
CALLBACK_PATH = "/auth/google/callback"

FLOW_COOKIE = "google_flow"
FLOW_COOKIE_PATH = "/auth/google"
FLOW_SECONDS = 10 * 60
JWKS_TTL_SECONDS = 60 * 60
HTTP_TIMEOUT = 10.0

# Domains whose mail Google Workspace hosts: an account with such an address must come from
# that Workspace (`hd` claim), not a consumer Google account registered with the address.
# btu.edu.ge's MX records point at aspmx.l.google.com (checked 2026-10-26).
WORKSPACE_DOMAINS = {"btu.edu.ge"}


class GoogleSignInError(Exception):
    """`code` is what /login?error= receives: google_cancelled, google_not_allowed,
    google_unavailable, google_failed or google_rate_limited."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class Flow:
    state: str
    nonce: str
    verifier: str
    next: str | None


def enabled() -> bool:
    return bool(get_settings().google_client_id)


def redirect_uri() -> str:
    return get_settings().public_base_url.rstrip("/") + CALLBACK_PATH


# --- The signed flow cookie -----------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _cookie_key() -> bytes:
    """Derived from the client secret, so no extra secret to configure; a different label
    keeps it from being the secret itself."""
    secret = get_settings().google_client_secret.get_secret_value()
    return hashlib.sha256(b"btu-passport google flow cookie\0" + secret.encode()).digest()


def _sign(payload: bytes) -> str:
    return _b64(hmac.new(_cookie_key(), payload, hashlib.sha256).digest())


def new_flow(next_: str | None) -> tuple[Flow, str]:
    """A fresh flow and its cookie value (expires FLOW_SECONDS from now)."""
    flow = Flow(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        verifier=secrets.token_urlsafe(64),  # 86 characters, within PKCE's 43-128
        next=next_,
    )
    payload = json.dumps(
        {"s": flow.state, "n": flow.nonce, "v": flow.verifier, "x": flow.next,
         "e": int(time.time()) + FLOW_SECONDS},
        separators=(",", ":"),
    ).encode()  # fmt: skip
    return flow, f"{_b64(payload)}.{_sign(payload)}"


def read_flow(cookie: str | None) -> Flow | None:
    """The flow from a cookie this server signed, or None if missing, forged or expired."""
    if not cookie or "." not in cookie:
        return None
    body, _, signature = cookie.partition(".")
    try:
        payload = _unb64(body)
        if not hmac.compare_digest(signature, _sign(payload)):
            return None
        data = json.loads(payload)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or int(data.get("e", 0)) < time.time():
        return None
    return Flow(state=data["s"], nonce=data["n"], verifier=data["v"], next=data.get("x"))


def authorization_url(flow: Flow) -> str:
    challenge = _b64(hashlib.sha256(flow.verifier.encode()).digest())
    query = {
        "client_id": get_settings().google_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "state": flow.state,
        "nonce": flow.nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{AUTH_URL}?{urlencode(query)}"


# --- Rate limit -----------------------------------------------------------------------------

_hits: dict[tuple[str, str], deque[float]] = {}
_hits_lock = threading.Lock()


def check_rate(route: str, ip: str | None) -> None:
    """BE-10's per-IP rule (LOGIN_RATE_PER_IP_HOUR per hour, per route), kept in memory as
    there is no table to count. Like BE-10, an unknown or loopback IP isn't limited."""
    if ip is None or ip.startswith("127.") or ip == "::1":
        return
    limit = get_settings().login_rate_per_ip_hour
    now = time.monotonic()
    with _hits_lock:
        hits = _hits.setdefault((route, ip), deque())
        while hits and hits[0] <= now - 3600:
            hits.popleft()
        if len(hits) >= limit:
            raise GoogleSignInError("google_rate_limited")
        hits.append(now)


def reset_rate_limits() -> None:
    with _hits_lock:
        _hits.clear()


# --- Token exchange and ID token check ------------------------------------------------------

_jwks: dict[str, Any] = {"keys": {}, "fetched": 0.0}
_jwks_lock = threading.Lock()


def _fetch_jwks() -> dict[str, jwt.PyJWK]:
    try:
        response = httpx.get(JWKS_URL, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        keys = jwt.PyJWKSet.from_dict(response.json()).keys
    except (httpx.HTTPError, ValueError, jwt.PyJWKSetError) as exc:
        raise GoogleSignInError("google_unavailable", f"JWKS: {exc}") from exc
    return {k.key_id: k for k in keys if k.key_id}


def _signing_key(kid: str) -> jwt.PyJWK:
    """Google's key for `kid`, from a JWKS cached for an hour; an unknown kid refetches once
    (Google rotates keys)."""
    with _jwks_lock:
        fresh = time.monotonic() - _jwks["fetched"] < JWKS_TTL_SECONDS
        if not fresh or kid not in _jwks["keys"]:
            _jwks["keys"] = _fetch_jwks()
            _jwks["fetched"] = time.monotonic()
        key: jwt.PyJWK | None = _jwks["keys"].get(kid)
    if key is None:
        raise GoogleSignInError("google_failed", f"unknown signing key {kid!r}")
    return key


def reset_jwks_cache() -> None:
    with _jwks_lock:
        _jwks.update(keys={}, fetched=0.0)


def exchange_code(code: str, flow: Flow) -> str:
    """Trades the authorization code (with the PKCE verifier) for Google's ID token."""
    s = get_settings()
    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret.get_secret_value(),
                "redirect_uri": redirect_uri(),
                "code_verifier": flow.verifier,
            },
            timeout=HTTP_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise GoogleSignInError("google_unavailable", f"token endpoint: {exc}") from exc
    if response.status_code >= 500:
        raise GoogleSignInError("google_unavailable", f"token endpoint {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200 or not isinstance(body.get("id_token"), str):
        # e.g. invalid_grant: the code was used, expired or doesn't match the verifier
        raise GoogleSignInError(
            "google_failed", f"token endpoint {response.status_code}: {body.get('error')}"
        )
    return str(body["id_token"])


def verify_id_token(id_token: str, nonce: str) -> dict[str, Any]:
    """Signature (Google's JWKS, RS256), iss, aud = our client ID, exp and nonce."""
    try:
        kid = jwt.get_unverified_header(id_token).get("kid", "")
        claims: dict[str, Any] = jwt.decode(
            id_token,
            _signing_key(kid),
            algorithms=["RS256"],
            audience=get_settings().google_client_id,
            issuer=ISSUERS,
            options={"require": ["iss", "aud", "exp", "iat", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise GoogleSignInError("google_failed", f"ID token: {exc}") from exc
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise GoogleSignInError("google_failed", "ID token: nonce mismatch")
    return claims


def allowed_email(claims: dict[str, Any]) -> str:
    """The verified, lower-cased email when this account may sign in, else google_not_allowed.

    Allowed: (a) the domain is in ALLOWED_EMAIL_DOMAINS, and for a Workspace domain the
    account belongs to that Workspace (hd); or (b) the exact address is in ALLOWED_EMAILS."""
    s = get_settings()
    email = str(claims.get("email", "")).strip().lower()
    if not email or claims.get("email_verified") is not True:
        raise GoogleSignInError("google_not_allowed", "email missing or not verified")
    if email in s.allowed_emails:
        return email
    domain = email.rpartition("@")[2]
    if domain not in s.allowed_email_domains:
        raise GoogleSignInError("google_not_allowed", f"domain {domain!r} not allowed")
    if domain in WORKSPACE_DOMAINS and claims.get("hd") != domain:
        raise GoogleSignInError("google_not_allowed", f"{domain} account without hd={domain}")
    return email


def sign_in(code: str, state: str, flow: Flow) -> str:
    """Callback steps after the cookie is read: state, code exchange, ID token, allow-list."""
    if not hmac.compare_digest(state, flow.state):
        raise GoogleSignInError("google_failed", "state mismatch")
    claims = verify_id_token(exchange_code(code, flow), flow.nonce)
    return allowed_email(claims)
