"""Verification (BE-30): the verdict for a code or a PDF hash, computed from the chain.

The database finds the version and its proof; the chain decides. A version's ANCHORED status
is needed to be found at all (only ANCHORED versions are verifiable, FR-22) but is never
enough: the proof must lead to a root anchored on BTU's registry (dataset rule).
"""

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AnchorBatch, PassportVersion
from app.schemas.verify import (
    Verdict,
    VerifyChain,
    VerifyChecks,
    VerifyProof,
    VerifyResult,
    VerifySkill,
    VerifyVersion,
)
from app.services import chain, merkle
from app.services.codes import normalize_code

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decide(
    *,
    issuer_ok: bool,
    document_ok: bool,
    revoked: bool,
    version_no: int,
    latest_version_no: int,
) -> Verdict:
    """Issuer first: a registry BTU doesn't own proves nothing about the document."""
    if not issuer_ok:
        return "NOT_ISSUED_BY_BTU"
    if not document_ok:
        return "NOT_FOUND"
    if revoked:
        return "REVOKED"
    if version_no < latest_version_no:
        return "SUPERSEDED"
    return "VALID"


def _not_found(verdict: Verdict) -> VerifyResult:
    return VerifyResult(verdict=verdict, checks=VerifyChecks(document=False, issuer=False))


def _anchored(db: Session, *where: object) -> PassportVersion | None:
    return db.scalars(
        select(PassportVersion).where(PassportVersion.status == "ANCHORED", *where)  # type: ignore[arg-type]
    ).one_or_none()


def verify_code(db: Session, text: str) -> VerifyResult:
    try:
        code = normalize_code(text)
    except ValueError:
        return _not_found("UNKNOWN_CODE")
    version = _anchored(db, PassportVersion.verification_code == code)
    return verify_version(db, version) if version else _not_found("UNKNOWN_CODE")


def verify_hash(db: Session, sha256: str) -> VerifyResult:
    pdf_sha256 = sha256.lower().removeprefix("0x")
    if not _HEX64.match(pdf_sha256):
        return _not_found("NOT_FOUND")
    version = _anchored(db, PassportVersion.pdf_sha256 == pdf_sha256)
    return verify_version(db, version) if version else _not_found("NOT_FOUND")


def _same_address(a: str | None, b: str | None) -> bool:
    return bool(a and b and a.lower() == b.lower())


def verify_version(db: Session, version: PassportVersion) -> VerifyResult:
    """Raises chain.ChainUnavailable when the chain can't be read."""
    s = get_settings()
    batch = db.get_one(AnchorBatch, version.batch_id)
    pdf_sha256 = version.pdf_sha256 or ""
    leaf = merkle.leaf(pdf_sha256)
    proof = list(version.merkle_proof or [])
    root = merkle.process_proof(leaf, proof)

    issuer_ok = (
        batch.chain_id == s.chain_id
        and _same_address(batch.contract_address, s.contract_address)
        and _same_address(chain.owner(), s.issuer_address)
    )
    document_ok = root == batch.merkle_root.lower() and chain.anchored_at(root) > 0
    revoked = chain.is_revoked(leaf)
    newest = (
        db.scalars(
            select(PassportVersion)
            .where(
                PassportVersion.passport_id == version.passport_id,
                PassportVersion.status == "ANCHORED",
            )
            .order_by(PassportVersion.version_no.desc())
            .limit(1)
        ).one_or_none()
        or version
    )
    latest = newest.version_no
    verdict = decide(
        issuer_ok=issuer_ok,
        document_ok=document_ok,
        revoked=revoked,
        version_no=version.version_no,
        latest_version_no=latest,
    )
    authentic = issuer_ok and document_ok
    return VerifyResult(
        verdict=verdict,
        checks=VerifyChecks(document=document_ok, issuer=issuer_ok),
        version=_version_data(version) if authentic else None,
        latest_version_no=latest if authentic else None,
        latest_issued_at=newest.issued_at if authentic else None,
        chain=VerifyChain(
            chain_id=batch.chain_id,
            contract_address=batch.contract_address,
            issuer_address=s.issuer_address,
            merkle_root=batch.merkle_root,
            tx_hash=batch.tx_hash or "",
            block_number=batch.block_number or 0,
            anchored_at=batch.anchored_at or version.issued_at,
        ),
        proof=VerifyProof(pdf_sha256="0x" + pdf_sha256, leaf=leaf, proof=proof),
    )


def _version_data(version: PassportVersion) -> VerifyVersion:
    """Official data, from the frozen content snapshot."""
    content = version.content_json or {}
    holder = content.get("holder", {})
    return VerifyVersion(
        passport_id=version.passport_id,
        version_no=version.version_no,
        verification_code=version.verification_code or "",
        issued_at=version.issued_at,
        holder_name=f"{holder.get('first_name', '')} {holder.get('last_name', '')}".strip(),
        skills=[
            VerifySkill(
                name=skill["name"],
                category=skill["category"],
                badge_code=skill["badge_code"],
                stamp_sha256=skill.get("stamp_sha256"),
                date_earned=skill["date_earned"],
            )
            for skill in content.get("skills", [])
        ],
    )
