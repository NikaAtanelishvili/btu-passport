"""Public verification (BE-30 to BE-32): VerifyResult, the proof file and the issuer file."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal[
    "VALID", "SUPERSEDED", "NOT_FOUND", "UNKNOWN_CODE", "NOT_ISSUED_BY_BTU", "REVOKED"
]


class HashQuery(BaseModel):
    sha256: Annotated[str, Field(pattern=r"^(0x)?[0-9a-fA-F]{64}$")]


class VerifyChecks(BaseModel):
    document: bool  # the PDF hash leads to a root anchored on the registry
    issuer: bool  # that registry is BTU's (issuer file) and BTU's issuer key owns it


class VerifySkill(BaseModel):
    name: str
    category: str
    badge_code: str
    stamp_sha256: str | None
    date_earned: date


class VerifyVersion(BaseModel):
    passport_id: str
    version_no: int
    verification_code: str
    issued_at: datetime
    holder_name: str
    skills: list[VerifySkill]


class VerifyChain(BaseModel):
    chain_id: int
    contract_address: str
    issuer_address: str
    merkle_root: str
    tx_hash: str
    block_number: int
    anchored_at: datetime


class VerifyProof(BaseModel):
    pdf_sha256: str
    leaf: str
    proof: list[str]


class VerifyResult(BaseModel):
    verdict: Verdict
    checks: VerifyChecks
    version: VerifyVersion | None = None  # only when BTU's registry vouches for the document
    latest_version_no: int | None = None
    latest_issued_at: datetime | None = None  # when latest_version_no was issued
    chain: VerifyChain | None = None
    proof: VerifyProof | None = None


class IssuerFile(BaseModel):
    issuer_name: str
    chain_id: int
    contract_address: str
    issuer_address: str


class ProofFile(BaseModel):
    """proof.json (Blockchain tab §5): with the PDF and any RPC, enough to check without BTU."""

    model_config = ConfigDict(populate_by_name=True)

    schema_: Annotated[str, Field(alias="schema")] = "btu-ai-passport-proof/1"
    passport_id: str
    version_no: int
    verification_code: str
    pdf_sha256: str
    leaf: str
    proof: list[str]
    merkle_root: str
    chain_id: int
    contract_address: str
    issuer_address: str
    tx_hash: str
    block_number: int
    anchored_at: str
    issuer_file_url: str
