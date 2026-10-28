"""BE-10: the SMTP mailer (no network: smtplib is replaced)."""

from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any, ClassVar

import httpx
import pytest

from app.config import get_settings
from app.services import mailer

REAL_NOTICE = mailer.send_version_notice  # before the autouse fixture replaces it


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


# --- MAIL_PROVIDER=resend: Resend's HTTP API (M10; Railway blocks outbound SMTP) ---


class FakeResend:
    """Stands in for httpx.post: records each request and answers with `status`."""

    def __init__(self, status: int = 200, body: str = '{"id": "fake-id"}') -> None:
        self.status, self.body = status, body
        self.requests: list[dict[str, Any]] = []

    def __call__(self, url: str, **kwargs: Any) -> httpx.Response:
        self.requests.append({"url": url, **kwargs})
        return httpx.Response(self.status, text=self.body, request=httpx.Request("POST", url))


@pytest.fixture
def resend(monkeypatch: pytest.MonkeyPatch, smtp: type[FakeSMTP]) -> FakeResend:
    fake = FakeResend()
    monkeypatch.setattr("httpx.post", fake)
    _configure(
        monkeypatch, MAIL_PROVIDER="resend", RESEND_API_KEY="re_test_key",
        MAIL_FROM="passport@btuaipassport.space",
    )  # fmt: skip
    return fake


def test_resend_sends_the_code_over_https(resend: FakeResend, smtp: type[FakeSMTP]) -> None:
    mailer.send_login_code("someone@btu.edu.ge", "123456")
    (req,) = resend.requests
    assert req["url"] == "https://api.resend.com/emails"
    assert req["headers"]["Authorization"] == "Bearer re_test_key"
    body = req["json"]
    assert body["from"] == "passport@btuaipassport.space"
    assert body["to"] == ["someone@btu.edu.ge"]
    assert body["subject"].startswith("123456 ")
    assert "123456" in body["text"] and "10 minutes" in body["text"]
    assert smtp.instances == []  # no SMTP connection at all


def test_resend_sends_version_notices(resend: FakeResend) -> None:
    REAL_NOTICE(
        email="s@btu.edu.ge", first_name="Nino", passport_id="BTU-AI-000001",
        version_no=2, skills=["Prompting"], url="https://btuaipassport.space/me",
    )  # fmt: skip
    (req,) = resend.requests
    assert req["json"]["to"] == ["s@btu.edu.ge"] and "Prompting" in req["json"]["text"]


@pytest.mark.parametrize("status", [401, 422, 500])
def test_resend_refusal_raises_oserror(resend: FakeResend, status: int) -> None:
    resend.status, resend.body = status, '{"message": "nope"}'
    with pytest.raises(OSError, match=str(status)):
        mailer.send_login_code("someone@btu.edu.ge", "123456")


def test_resend_network_error_raises_oserror(
    resend: FakeResend, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("no route")

    monkeypatch.setattr("httpx.post", boom)
    with pytest.raises(OSError) as excinfo:
        mailer.send_login_code("someone@btu.edu.ge", "123456")
    assert "re_test_key" not in str(excinfo.value)


def test_smtp_from_still_accepted(smtp: type[FakeSMTP], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAIL_FROM", raising=False)
    _configure(monkeypatch, SMTP_PORT="1025", SMTP_USER="", SMTP_FROM="old@btu.test")
    mailer.send_login_code("newcomer@btu.test", "123456")
    assert smtp.instances[0].messages[0]["From"] == "old@btu.test"
