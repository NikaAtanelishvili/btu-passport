"""Email-code sign-in (BE-10): issue, rate-limit and check one-time 6-digit codes.

Only the SHA-256 of a code is stored. The same thing happens for every allowed address,
whether or not it belongs to a student, so request-code reveals nothing.
"""

import hashlib
import hmac
import ipaddress
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import LoginCode
from app.services import mailer

log = logging.getLogger("app.auth")

# Where a forwarding proxy can sit: Next.js on this host (dev), Caddy on the Docker network.
TRUSTED_PROXY_NETS = [
    ipaddress.ip_network(n)
    for n in ("127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
]


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def normalise_email(email: str) -> str:
    return email.strip().lower()


def check_domain(email: str) -> None:
    domain = email.rpartition("@")[2]
    if "@" not in email or domain not in get_settings().allowed_email_domains:
        raise AppError(
            "email_domain_not_allowed",
            "Use your BTU email address.",
            422,
            {"email": "Use your BTU email"},
        )


def client_ip(request: Request) -> str | None:
    """The caller's IP. X-Forwarded-For is trusted only when the direct peer is a local proxy
    (TRUSTED_PROXY_NETS), and then only its last hop, which that proxy wrote; earlier hops
    can be supplied by the client."""
    peer = request.client.host if request.client else None
    try:
        peer_ip = ipaddress.ip_address(peer) if peer else None
    except ValueError:
        return None
    if peer_ip is not None and any(peer_ip in net for net in TRUSTED_PROXY_NETS):
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return str(peer_ip) if peer_ip else None


def request_code(db: Session, email: str, ip: str | None) -> None:
    s = get_settings()
    now = datetime.now(UTC)
    window = now - timedelta(hours=1)

    def recent(*where: object) -> int:
        stmt = select(func.count()).select_from(LoginCode).where(LoginCode.created_at > window)
        return db.scalar(stmt.where(*where)) or 0  # type: ignore[arg-type]

    # A loopback address means "real IP unknown" (dev, behind the Next.js proxy): limiting it
    # would be one shared limit for everybody, so only the per-email limit applies there.
    ip_known = ip is not None and not ipaddress.ip_address(ip).is_loopback
    if recent(LoginCode.email == email) >= s.login_rate_per_email_hour or (
        ip_known and recent(LoginCode.requested_ip == ip) >= s.login_rate_per_ip_hour
    ):
        raise AppError("rate_limited", "Too many codes requested, try again later.", 429)

    db.execute(
        update(LoginCode)
        .where(LoginCode.email == email, LoginCode.used_at.is_(None))
        .values(used_at=now)
    )
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(
        LoginCode(
            email=email,
            code_hash=_hash(code),
            requested_ip=ip,
            expires_at=now + timedelta(minutes=s.login_code_ttl_minutes),
            created_at=now,
        )
    )
    db.flush()
    if s.dev_log_login_codes:  # refused at startup unless ENV is dev or test
        log.info("DEV_LOG_LOGIN_CODES: sign-in code for %s is %s", email, code)
    try:
        mailer.send_login_code(email, code)
    except OSError as exc:
        log.error("sending the sign-in email to %s failed: %s", email, exc)
        raise AppError(
            "email_unavailable", "Couldn't send the email, try again shortly.", 503
        ) from exc


def check_code(db: Session, email: str, code: str) -> None:
    """Consume the code or raise. A wrong guess is committed before the error is raised,
    so the attempt counts even though the request fails."""
    s = get_settings()
    now = datetime.now(UTC)
    row = db.scalars(
        select(LoginCode)
        .where(
            LoginCode.email == email,
            LoginCode.used_at.is_(None),
            LoginCode.expires_at > now,
            LoginCode.attempts < s.login_code_max_attempts,
        )
        .order_by(LoginCode.created_at.desc(), LoginCode.code_id.desc())
        .limit(1)
        .with_for_update()
    ).first()
    if row is None:
        raise AppError("code_expired", "Code expired, send a new one.", 400)
    if not hmac.compare_digest(row.code_hash, _hash(code)):
        row.attempts += 1
        attempts_left = s.login_code_max_attempts - row.attempts
        db.commit()
        raise AppError(
            "code_invalid",
            f"Wrong code, {attempts_left} tries left.",
            400,
            {"code": "Wrong code"},
            {"attempts_left": attempts_left},
        )
    row.used_at = now
    db.flush()
