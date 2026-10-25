"""Public, no sign-in: BTU's issuer file (BE-31) and stamp images (BE-32)."""

import re

from fastapi import APIRouter, Response

from app.config import get_settings
from app.errors import AppError
from app.schemas.verify import IssuerFile
from app.services import storage
from app.services.content import ISSUER_NAME

router = APIRouter(tags=["public"])


@router.get("/.well-known/ai-passport-issuer.json", response_model=IssuerFile)
def issuer_file() -> IssuerFile:
    """Binds BTU to its registry and issuer key (FR-21). Verifiers check that the registry's
    owner() is this issuer_address; the browser and the standalone script read it too."""
    s = get_settings()
    return IssuerFile(
        issuer_name=ISSUER_NAME,
        chain_id=s.chain_id,
        contract_address=s.contract_address,
        issuer_address=s.issuer_address,
    )


_STAMP_TYPES = {"svg": "image/svg+xml", "png": "image/png"}


@router.get(
    "/api/stamps/{sha256}",
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {}, "image/png": {}}}},
)
def stamp(sha256: str) -> Response:
    """Stamp images by content hash (check-in and verify pages). Never changes, so cacheable."""
    found = storage.get_stamp(sha256) if re.fullmatch(r"[0-9a-f]{64}", sha256) else None
    if found is None:
        raise AppError("not_found", "No such stamp.", 404)
    data, ext = found
    return Response(
        data,
        media_type=_STAMP_TYPES[ext],
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            # Opened on its own, an SVG stamp can't run anything or load anything (BE-51).
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )
