"""Job handlers (BE-27, BE-28). Each runs in its own session; the loop commits on success."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AnchorBatch, Passport, PassportVersion
from app.pdf.render import render_passport
from app.services import anchoring, codes, merkle, storage
from app.services.content import build_content
from app.sheets import service as sheets

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


def _pick_batch(db: Session) -> AnchorBatch | None:
    """An unfinished SUBMITTING batch (a retry keeps the same root), else a new batch from up
    to BATCH_MAX_LEAVES RENDERED versions, oldest first. None when there is nothing to do."""
    s = get_settings()
    batch = db.scalars(
        select(AnchorBatch)
        .where(AnchorBatch.status == "SUBMITTING")
        .order_by(AnchorBatch.batch_id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if batch is not None:
        return batch
    versions = list(
        db.scalars(
            select(PassportVersion)
            .where(PassportVersion.status == "RENDERED")
            .order_by(PassportVersion.version_id)
            .limit(s.batch_max_leaves)
            .with_for_update(skip_locked=True)
        )
    )
    if not versions:
        return None
    root, proofs = merkle.build_tree([v.pdf_sha256 or "" for v in versions])
    # Retried versions can rebuild exactly the leaves of a FAILED batch: reuse that row.
    batch = db.scalars(select(AnchorBatch).where(AnchorBatch.merkle_root == root)).one_or_none()
    if batch is None:
        batch = AnchorBatch(merkle_root=root, leaf_count=len(versions))
        db.add(batch)
    batch.chain_id = s.chain_id
    batch.contract_address = s.contract_address
    batch.status = "SUBMITTING"
    batch.attempts = 0
    batch.last_error = None
    db.flush()
    for v in versions:
        v.status = "ANCHORING"
        v.batch_id = batch.batch_id
        v.merkle_proof = proofs["0x" + (v.pdf_sha256 or "")]
    return batch


def anchor_batch(db: Session, payload: Payload) -> None:
    """BE-28: one Merkle tree, one transaction. The batch is committed before the signer is
    called, so a crash can't lose it; a retry sends the same root, and the signer answers
    `already_anchored` if the first call got through."""
    batch = _pick_batch(db)
    if batch is None:
        return
    db.commit()

    try:
        receipt = anchoring.anchor_root(batch.merkle_root, batch.leaf_count)
    except anchoring.AnchorError as exc:
        batch = db.get_one(AnchorBatch, batch.batch_id, with_for_update=True)
        batch.attempts += 1
        batch.last_error = str(exc)
        if batch.attempts < get_settings().anchor_max_attempts:
            db.commit()
            raise  # the job loop backs off and retries the same batch
        batch.status = "FAILED"
        for v in _batch_versions(db, batch.batch_id):
            v.status = "FAILED"
            v.error = f"anchoring failed: {exc}"
        return

    batch.status = "ANCHORED"
    batch.tx_hash = receipt.tx_hash
    batch.block_number = receipt.block_number
    batch.anchored_at = receipt.anchored_at
    batch.last_error = None
    for v in _batch_versions(db, batch.batch_id):
        v.status = "ANCHORED"
        v.error = None
        _advance_latest(db, v)


def _batch_versions(db: Session, batch_id: int) -> list[PassportVersion]:
    stmt = (
        select(PassportVersion)
        .where(PassportVersion.batch_id == batch_id)
        .order_by(PassportVersion.version_id)
        .with_for_update()
    )
    return list(db.scalars(stmt))


def _advance_latest(db: Session, version: PassportVersion) -> None:
    """latest_version_id only moves to a higher version_no."""
    passport = db.get_one(Passport, version.passport_id, with_for_update=True)
    current = (
        db.get(PassportVersion, passport.latest_version_id) if passport.latest_version_id else None
    )
    if current is None or version.version_no > current.version_no:
        passport.latest_version_id = version.version_id


def sheet_sync(db: Session, payload: Payload) -> None:
    """SH-05: one Sheet sync run; it uses its own transactions (one per student)."""
    sheets.run_job(payload["run_id"])


def fail_sheet_sync(db: Session, payload: Payload, error: str) -> None:
    sheets.give_up(payload["run_id"], error)


HANDLERS: dict[str, JobHandler] = {
    "ISSUE_VERSION": JobHandler(run=issue_version, give_up=fail_issue),
    "ANCHOR_BATCH": JobHandler(run=anchor_batch),
    "SHEET_SYNC": JobHandler(run=sheet_sync, give_up=fail_sheet_sync),
}
