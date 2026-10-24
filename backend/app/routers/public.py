"""Public, no sign-in: BTU's issuer file (BE-31) and stamp images (BE-32)."""

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.verify import IssuerFile
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
