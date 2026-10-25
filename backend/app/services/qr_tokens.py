"""Rotating check-in tokens (BE-41, FR-28). A token is derived from the event's secret and the
current 30-second window; the current and the previous window are accepted, so a token
lives 30-60 s and a photo of the QR stops working within a minute (A13).

A signed-out scan can't check in, and sign-in takes minutes, so the token is checked at scan
time and swapped for a check-in pass: signed with the same event secret, valid for 10 minutes
and good for one check-in (the nonce is stored on the participant row it creates)."""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime

from app.config import get_settings

WINDOW_SECONDS = 30
TOKEN_LENGTH = 16
PASS_SECONDS = 600


def window(now: datetime) -> int:
    return int(now.timestamp() // WINDOW_SECONDS)


def token(secret: bytes, event_id: uuid.UUID, w: int) -> str:
    digest = hmac.new(secret, f"{event_id}:{w}".encode(), hashlib.sha256).digest()
    return base64.b32encode(digest).decode().rstrip("=")[:TOKEN_LENGTH]


def is_valid(secret: bytes, event_id: uuid.UUID, t: str, now: datetime) -> bool:
    w = window(now)
    given = t.encode()
    # Both windows are always compared, so the timing doesn't reveal which one matched.
    current = hmac.compare_digest(given, token(secret, event_id, w).encode())
    previous = hmac.compare_digest(given, token(secret, event_id, w - 1).encode())
    return current or previous


def checkin_url(secret: bytes, event_id: uuid.UUID, now: datetime) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/checkin/{event_id}?t={token(secret, event_id, window(now))}"


def refresh_in_seconds(now: datetime) -> int:
    return WINDOW_SECONDS - int(now.timestamp()) % WINDOW_SECONDS


def _pass_mac(secret: bytes, event_id: uuid.UUID, exp: int, nonce: str) -> str:
    digest = hmac.new(secret, f"pass:{event_id}:{exp}:{nonce}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def issue_pass(secret: bytes, event_id: uuid.UUID, now: datetime) -> str:
    """`<expiry unix seconds>.<nonce>.<mac>`; URL-safe as is."""
    exp = int(now.timestamp()) + PASS_SECONDS
    nonce = secrets.token_hex(8)
    return f"{exp}.{nonce}.{_pass_mac(secret, event_id, exp, nonce)}"


def read_pass(secret: bytes, event_id: uuid.UUID, p: str, now: datetime) -> str | None:
    """The pass's nonce when it is signed for this event and not expired, else None.
    Whether the nonce was already used is the caller's check (it lives in the database)."""
    parts = p.split(".")
    if len(parts) != 3 or not parts[0].isdigit() or not parts[1]:
        return None
    exp, nonce, mac = int(parts[0]), parts[1], parts[2]
    if not hmac.compare_digest(mac.encode(), _pass_mac(secret, event_id, exp, nonce).encode()):
        return None
    return nonce if now.timestamp() < exp else None
