"""Public verification (BE-32): verdict by code or by PDF hash, the official PDF and the
proof file. No sign-in; only ANCHORED versions are ever found (FR-22)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.models import AnchorBatch, PassportVersion
from app.schemas.verify import HashQuery, ProofFile, VerifyResult
from app.services import merkle, storage, verification
from app.services.chain import ChainUnavailable
from app.services.codes import normalize_code
from app.services.content import iso_utc

router = APIRouter(prefix="/api/verify", tags=["verify"])
DB = Annotated[Session, Depends(get_db)]


def _chain_unavailable(exc: ChainUnavailable) -> AppError:
    return AppError("chain_unavailable", f"The blockchain can't be reached right now ({exc}).", 503)


@router.post("/hash", response_model=VerifyResult)
def verify_hash(body: HashQuery, db: DB) -> VerifyResult:
    """The browser hashes the PDF itself and sends only this fingerprint (FE-10)."""
    try:
        return verification.verify_hash(db, body.sha256)
    except ChainUnavailable as exc:
        raise _chain_unavailable(exc) from exc


@router.get("/{code}", response_model=VerifyResult)
def verify_code(code: str, db: DB) -> VerifyResult:
    try:
        return verification.verify_code(db, code)
    except ChainUnavailable as exc:
        raise _chain_unavailable(exc) from exc


def _issued(db: Session, code: str) -> PassportVersion:
    try:
        normalized = normalize_code(code)
    except ValueError:
        normalized = ""
    version = db.scalars(
        select(PassportVersion).where(
            PassportVersion.verification_code == normalized,
            PassportVersion.status == "ANCHORED",
        )
    ).one_or_none()
    if version is None or not version.pdf_key:
        raise AppError("not_found", "No issued passport has this code.", 404)
    return version


@router.get(
    "/{code}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def official_pdf(code: str, db: DB) -> Response:
    """The stored bytes, to compare against the copy the verifier received."""
    return pdf_response(_issued(db, code))


def pdf_response(version: PassportVersion) -> Response:
    """Also served to students for their own versions (BE-47)."""
    filename = f"{version.passport_id}-v{version.version_no}.pdf"
    return Response(
        storage.get(version.pdf_key or ""),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{code}/proof.json", response_model=ProofFile, response_model_by_alias=True)
def proof_file(code: str, db: DB, response: Response) -> ProofFile:
    version = _issued(db, code)
    set_proof_filename(response, version)
    return build_proof_file(db, version)


def set_proof_filename(response: Response, version: PassportVersion) -> None:
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{version.passport_id}-v{version.version_no}-proof.json"'
    )


def build_proof_file(db: Session, version: PassportVersion) -> ProofFile:
    """Also served to students for their own versions (BE-47)."""
    s = get_settings()
    batch = db.get_one(AnchorBatch, version.batch_id)
    pdf_sha256 = version.pdf_sha256 or ""
    return ProofFile(
        passport_id=version.passport_id,
        version_no=version.version_no,
        verification_code=version.verification_code or "",
        pdf_sha256="0x" + pdf_sha256,
        leaf=merkle.leaf(pdf_sha256),
        proof=list(version.merkle_proof or []),
        merkle_root=batch.merkle_root,
        chain_id=batch.chain_id,
        contract_address=batch.contract_address,
        issuer_address=s.issuer_address,
        tx_hash=batch.tx_hash or "",
        block_number=batch.block_number or 0,
        anchored_at=iso_utc(batch.anchored_at) if batch.anchored_at else "",
        issuer_file_url=f"{s.public_base_url.rstrip('/')}/.well-known/ai-passport-issuer.json",
    )
