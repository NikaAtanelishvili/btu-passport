"""Outgoing email: sign-in codes (BE-10) and version notices (SH-10). MAIL_PROVIDER=smtp
(dev: Mailpit on localhost:1025) or resend (Resend's HTTP API, for hosts that block SMTP)."""

import smtplib
import ssl
from email.message import EmailMessage

import httpx

from app.config import get_settings

RESEND_URL = "https://api.resend.com/emails"


class MailError(OSError):
    """Sending failed. An OSError like smtplib's errors, so callers handle both the same way."""


def send_login_code(email: str, code: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.mail_from
    msg["To"] = email
    msg["Subject"] = f"{code} is your BTU AI Skills Passport sign-in code"
    msg.set_content(
        f"Your sign-in code is {code}\n\n"
        f"It expires in {s.login_code_ttl_minutes} minutes and works once.\n"
        "If you didn't ask for it, ignore this email: nobody can sign in without the code.\n"
    )
    _send(msg)


def send_version_notice(
    *, email: str, first_name: str, passport_id: str, version_no: int, skills: list[str], url: str
) -> None:
    """SH-10: a new version with new skills is anchored and can be downloaded."""
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.mail_from
    msg["To"] = email
    msg["Subject"] = f"Your AI Skills Passport was updated to version {version_no}"
    added = "\n".join(f"  - {name}" for name in skills)
    msg.set_content(
        f"Hello {first_name},\n\n"
        f"BTU added new verified skills to your AI Skills Passport {passport_id}. "
        f"Version {version_no} is issued and recorded on the blockchain.\n\n"
        f"New skills:\n{added}\n\n"
        f"View and download your passport: {url}\n"
    )
    _send(msg)


def _send(msg: EmailMessage) -> None:
    if get_settings().mail_provider == "resend":
        _send_resend(msg)
    else:
        _send_smtp(msg)


def _send_resend(msg: EmailMessage) -> None:
    s = get_settings()
    try:
        response = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {s.resend_api_key.get_secret_value()}"},
            json={
                "from": msg["From"],
                "to": [msg["To"]],
                "subject": msg["Subject"],
                "text": msg.get_content(),
            },
            timeout=15,
        )
    except httpx.HTTPError as exc:
        # The exception text never holds the request headers, so the key can't leak here.
        raise MailError(f"Resend request failed: {type(exc).__name__}: {exc}") from exc
    if response.is_error:
        raise MailError(
            f"Resend refused the email: HTTP {response.status_code} {response.text[:200]}"
        )


def _send_smtp(msg: EmailMessage) -> None:
    s = get_settings()
    smtp_class = smtplib.SMTP_SSL if s.smtp_port == 465 else smtplib.SMTP
    with smtp_class(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        if s.smtp_port == 587:
            smtp.starttls(context=ssl.create_default_context())
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password.get_secret_value())
        smtp.send_message(msg)
