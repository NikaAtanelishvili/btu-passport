"""End-to-end anchoring on Anvil (BE-28 + BC-07): the worker's signer client talks to the real
signer app (in-process), which sends a real transaction to the registry."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AnchorBatch, PassportVersion
from app.services import merkle
from signer.config import get_signer_settings
from signer.main import load_signer

pytestmark = pytest.mark.chain

ClientAs = Callable[[str | None], TestClient]
RunJobs = Callable[[], int]


def test_A1_additional_award_on_chain(
    seeded: Session, client_as: ClientAs, real_signer: None, run_jobs: RunJobs
) -> None:
    db = seeded
    r = client_as("admin").post(
        "/api/admin/awards",
        json={
            "student_ids": ["BTU-T-0021"],
            "skill_id": "SKL-001",
            "date_earned": "2026-10-20",
            "reason": "Workshop completed",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 202, r.text
    run_jobs()
    db.expire_all()
    version = db.get_one(PassportVersion, r.json()["versions"][0]["version_id"])
    assert version.status == "ANCHORED"
    batch = db.get_one(AnchorBatch, version.batch_id)
    assert batch.tx_hash and batch.block_number

    contract = load_signer(get_signer_settings()).contract
    root = bytes.fromhex(batch.merkle_root[2:])
    assert contract.functions.anchoredAt(root).call() > 0
    leaf = bytes.fromhex(merkle.leaf(version.pdf_sha256 or "")[2:])
    proof = [bytes.fromhex(p[2:]) for p in version.merkle_proof or []]
    assert contract.functions.verify(leaf, proof).call() > 0  # the contract accepts the proof
