"""Job handlers (BE-27, BE-28). Each runs in its own session; the loop commits on success."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import PassportVersion
from app.pdf.render import render_passport
from app.services import codes, storage
from app.services.content import build_content

Payload = dict[str, Any]


@dataclass(frozen=True)
class JobHandler:
    run: Callable[[Session, Payload], None]
    # Called once, in a fresh transaction, when the job fails its last attempt.
    give_up: Callable[[Session, Payload, str], None] | None = None


def _unused_code(db: Session) -> str:
    """50 random bits; on the rare clash with an existing code, draw again."""
    while True:
        code = codes.new_verification_code()
        if not db.scalar(select(exists().where(PassportVersion.verification_code == code))):
            return code


def issue_version(db: Session, payload: Payload) -> None:
    """BE-27: PENDING -> RENDERED. Content is frozen into content_json, the PDF is stored
    under its SHA-256. A repeat run finds the version no longer PENDING and does nothing."""
    version = db.scalars(
        select(PassportVersion)
        .where(PassportVersion.version_id == payload["version_id"])
        .with_for_update()
    ).one_or_none()
    if version is None or version.status != "PENDING":
        return
    code = _unused_code(db)
    issued_at = datetime.now(UTC).replace(microsecond=0)
    content = build_content(db, version, verification_code=code, issued_at=issued_at)
    pdf = render_passport(content)
    sha = hashlib.sha256(pdf).hexdigest()
    storage.put(storage.pdf_key(sha), pdf, "application/pdf")
    version.content_json = content
    version.verification_code = code
    version.pdf_sha256 = sha
    version.pdf_key = storage.pdf_key(sha)
    version.issued_at = issued_at
    version.error = None
    version.status = "RENDERED"


def fail_issue(db: Session, payload: Payload, error: str) -> None:
    version = db.get(PassportVersion, payload["version_id"], with_for_update=True)
    if version is not None and version.status == "PENDING":
        version.status = "FAILED"
        version.error = f"rendering failed: {error}"


HANDLERS: dict[str, JobHandler] = {
    "ISSUE_VERSION": JobHandler(run=issue_version, give_up=fail_issue),
}
