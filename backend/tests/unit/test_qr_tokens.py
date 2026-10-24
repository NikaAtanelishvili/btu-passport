"""BE-41: rotating check-in tokens (FR-28, A13)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.services import qr_tokens

SECRET = bytes(range(32))
EVENT = uuid.UUID("6b1f5d1e-6a43-4e0e-9d6c-2f1f5c3b9a10")
T0 = datetime(2026, 10, 21, 11, 45, 0, tzinfo=UTC)  # unix seconds divisible by 30


def test_window_is_30_seconds() -> None:
    assert T0.timestamp() % 30 == 0
    w = qr_tokens.window(T0)
    assert qr_tokens.window(T0 + timedelta(seconds=29.9)) == w
    assert qr_tokens.window(T0 + timedelta(seconds=30)) == w + 1


def test_token_shape_and_determinism() -> None:
    t = qr_tokens.token(SECRET, EVENT, 100)
    assert len(t) == 16 and t.isalnum() and t == t.upper() and "=" not in t
    assert t == qr_tokens.token(SECRET, EVENT, 100)
    assert t != qr_tokens.token(SECRET, EVENT, 101)
    assert t != qr_tokens.token(bytes(32), EVENT, 100)
    assert t != qr_tokens.token(SECRET, uuid.uuid4(), 100)


@pytest.mark.parametrize(
    ("issued", "checked", "valid"),
    [
        (T0, T0, True),
        (T0, T0 + timedelta(seconds=29), True),
        (T0 + timedelta(seconds=29), T0 + timedelta(seconds=59), True),  # previous window
        (T0, T0 + timedelta(seconds=60), False),  # two windows ago (A13)
        (T0, T0 + timedelta(minutes=2), False),
        (T0 + timedelta(seconds=30), T0, False),  # a future window
    ],
)
def test_current_and_previous_window_only(issued: datetime, checked: datetime, valid: bool) -> None:
    t = qr_tokens.token(SECRET, EVENT, qr_tokens.window(issued))
    assert qr_tokens.is_valid(SECRET, EVENT, t, checked) is valid


def test_garbage_is_invalid() -> None:
    for t in ("", "x", "A" * 16, "a" * 200):
        assert qr_tokens.is_valid(SECRET, EVENT, t, T0) is False


def test_checkin_url_and_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "public_base_url", "http://192.168.1.27:3000/")
    url = qr_tokens.checkin_url(SECRET, EVENT, T0 + timedelta(seconds=5))
    assert url == (
        f"http://192.168.1.27:3000/checkin/{EVENT}?t="
        f"{qr_tokens.token(SECRET, EVENT, qr_tokens.window(T0))}"
    )
    assert qr_tokens.refresh_in_seconds(T0 + timedelta(seconds=5)) == 25
    assert qr_tokens.refresh_in_seconds(T0) == 30
