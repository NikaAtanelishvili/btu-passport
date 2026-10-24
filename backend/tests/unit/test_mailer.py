"""BE-10: the SMTP mailer (no network: smtplib is replaced)."""

from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any, ClassVar

import pytest

from app.config import get_settings
from app.services import mailer


class FakeSMTP:
    instances: ClassVar[list["FakeSMTP"]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host, self.port = host, port
        self.calls: list[str] = []
        self.messages: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.calls.append("quit")

    def starttls(self, context: Any = None) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}")

    def send_message(self, msg: EmailMessage) -> None:
        self.messages.append(msg)


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[FakeSMTP]]:
    FakeSMTP.instances = []
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    yield FakeSMTP
    get_settings.cache_clear()


def _configure(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def test_plain_smtp_for_mailpit(smtp: type[FakeSMTP], monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, SMTP_HOST="localhost", SMTP_PORT="1025", SMTP_USER="")
    mailer.send_login_code("newcomer@btu.test", "123456")
    (conn,) = smtp.instances
    assert (conn.host, conn.port) == ("localhost", 1025)
    assert "starttls" not in conn.calls and not any(c.startswith("login") for c in conn.calls)
    (msg,) = conn.messages
    assert msg["To"] == "newcomer@btu.test" and msg["From"] == "passport@btu.test"
    assert "123456" in msg.get_content() and "10 minutes" in msg.get_content()


def test_starttls_and_login_on_587(smtp: type[FakeSMTP], monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(
        monkeypatch, SMTP_HOST="smtp.example.org", SMTP_PORT="587",
        SMTP_USER="sender", SMTP_PASSWORD="pw",
    )  # fmt: skip
    mailer.send_login_code("newcomer@btu.test", "654321")
    (conn,) = smtp.instances
    assert conn.calls[:2] == ["starttls", "login:sender"]
