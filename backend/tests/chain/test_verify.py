"""A4-A7 on Anvil (M5): issue through the real signer, verify through the public API, which
reads the real registry. The same scenarios run against a fake chain in
tests/integration/test_verification.py."""

import hashlib
import json
from collections.abc import Callable

import pytest
from eth_account import Account
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from web3 import Web3

from app.config import REPO_ROOT, get_settings
from app.models import AnchorBatch, PassportVersion, Skill, Student
from app.services import issuance, storage
from tests import factories as f

pytestmark = pytest.mark.chain

RunJobs = Callable[[], int]
ClientAs = Callable[[str | None], TestClient]
# DEV ONLY: Anvil account 1's published test key (not BTU's issuer).
ANVIL_KEY_1 = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"


@pytest.fixture
def issue(db: Session, s3_bucket: str, run_jobs: RunJobs) -> Callable[..., PassportVersion]:
    def make(st: Student, sk: Skill) -> PassportVersion:
        f.award(db, st, sk)
        (made,) = issuance.create_versions(db, [st.student_id])
        db.commit()
        run_jobs()
        db.expire_all()
        version = db.get_one(PassportVersion, made.version_id)
        assert version.status == "ANCHORED", version.error
        return version

    return make


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_A4_valid(
    db: Session, real_signer: None, issue: Callable[..., PassportVersion], client_as: ClientAs
) -> None:
    v1 = issue(f.student(db, 1), f.skill(db))
    pdf = client_as(None).get(f"/api/verify/{v1.verification_code}/pdf").content
    r = client_as(None).post("/api/verify/hash", json={"sha256": _sha256(pdf)})
    body = r.json()
    assert body["verdict"] == "VALID", body
    assert body["checks"] == {"document": True, "issuer": True}
    assert body["version"]["holder_name"] == "Nino Test"


def test_A5_tampered(
    db: Session, real_signer: None, issue: Callable[..., PassportVersion], client_as: ClientAs
) -> None:
    v1 = issue(f.student(db, 1), f.skill(db))
    pdf = bytearray(storage.get(v1.pdf_key or ""))
    pdf[len(pdf) // 2] ^= 0x01
    r = client_as(None).post("/api/verify/hash", json={"sha256": _sha256(bytes(pdf))})
    assert r.json()["verdict"] == "NOT_FOUND"


def test_A6_superseded(
    db: Session, real_signer: None, issue: Callable[..., PassportVersion], client_as: ClientAs
) -> None:
    st = f.student(db, 1)
    v1 = issue(st, f.skill(db, "SKL-001"))
    v2 = issue(st, f.skill(db, "SKL-002"))
    old = client_as(None).get(f"/api/verify/{v1.verification_code}").json()
    assert (old["verdict"], old["latest_version_no"]) == ("SUPERSEDED", 2)
    assert client_as(None).get(f"/api/verify/{v2.verification_code}").json()["verdict"] == "VALID"


def _deploy_foreign_registry(w3: Web3) -> str:
    """A look-alike PassportRegistry owned by Anvil account 1."""
    artifact = json.loads(
        (REPO_ROOT / "contracts/out/PassportRegistry.sol/PassportRegistry.json").read_text()
    )
    account = Account.from_key(ANVIL_KEY_1)
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"]["object"])
    tx = contract.constructor(account.address).build_transaction(
        {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address)}
    )
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction)
    )
    return str(receipt["contractAddress"])


def _anchor_as_account_1(w3: Web3, registry: str, root: str) -> None:
    account = Account.from_key(ANVIL_KEY_1)
    abi = json.loads((REPO_ROOT / "shared/PassportRegistry.abi.json").read_text())
    contract = w3.eth.contract(address=Web3.to_checksum_address(registry), abi=abi)
    tx = contract.functions.anchor(bytes.fromhex(root[2:]), 1).build_transaction(
        {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address)}
    )
    w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction)
    )


def test_A7_foreign_issuer(
    db: Session,
    fake_signer: object,
    issue: Callable[..., PassportVersion],
    client_as: ClientAs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proof leads to a root that is really anchored, but on a registry BTU's issuer key
    doesn't own: the document check passes and the issuer check fails."""
    w3 = Web3(Web3.HTTPProvider(get_settings().rpc_url))
    foreign = _deploy_foreign_registry(w3)
    monkeypatch.setattr(get_settings(), "contract_address", foreign)
    v1 = issue(f.student(db, 1), f.skill(db))  # batch recorded against the foreign registry
    _anchor_as_account_1(w3, foreign, db.get_one(AnchorBatch, v1.batch_id).merkle_root)

    body = client_as(None).get(f"/api/verify/{v1.verification_code}").json()
    assert body["verdict"] == "NOT_ISSUED_BY_BTU", body
    assert body["checks"] == {"document": True, "issuer": False}
    assert body["version"] is None
