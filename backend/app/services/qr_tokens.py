"""Rotating check-in tokens (BE-41, FR-28). A token is derived from the event's secret and the
current 30-second window; the current and the previous window are accepted, so a token
lives 30-60 s and a photo of the QR stops working within a minute (A13)."""

import base64
import hashlib
import hmac
import uuid
from datetime import datetime

from app.config import get_settings

WINDOW_SECONDS = 30
TOKEN_LENGTH = 16


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
