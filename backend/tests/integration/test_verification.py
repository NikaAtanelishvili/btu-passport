"""BE-30: the verification service against a fake chain (the Anvil versions of A4-A7 are in
tests/chain/test_verify.py). Verification never trusts the version status alone."""

from collections.abc import Callable

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import AnchorBatch, PassportVersion, Skill, Student
from app.services import issuance, merkle, storage, verification
from app.services.chain import ChainUnavailable
from tests import factories as f
from tests.conftest import FakeChain

RunJobs = Callable[[], int]


@pytest.fixture
def issue(
    db: Session, s3_bucket: str, fake_chain: FakeChain, run_jobs: RunJobs
) -> Callable[..., PassportVersion]:
    """issue(student, skill): award the skill and run the worker until ANCHORED."""

    def make(st: Student, sk: Skill) -> PassportVersion:
        f.award(db, st, sk)
        (made,) = issuance.create_versions(db, [st.student_id])
        db.commit()
        run_jobs()
        db.expire_all()
        version = db.get_one(PassportVersion, made.version_id)
        assert version.status == "ANCHORED"
        return version

    return make


def test_A4_an_issued_pdf_is_valid(db: Session, issue: Callable[..., PassportVersion]) -> None:
    st, sk = f.student(db, 1), f.skill(db)
    v1 = issue(st, sk)
    pdf = storage.get(v1.pdf_key or "")
    result = verification.verify_hash(db, verification.sha256_hex(pdf))
    assert result.verdict == "VALID"
    assert (result.checks.document, result.checks.issuer) == (True, True)
    assert result.version is not None
    assert (result.version.passport_id, result.version.version_no) == ("BTU-AI-000001", 1)
    assert result.version.holder_name == "Nino Test"
    assert [s.name for s in result.version.skills] == ["Skill SKL-001"]
    assert result.latest_version_no == 1
    assert result.proof is not None and result.chain is not None
    assert result.proof.pdf_sha256 == "0x" + (v1.pdf_sha256 or "")
    assert result.proof.leaf == merkle.leaf(v1.pdf_sha256 or "")
    assert merkle.process_proof(result.proof.leaf, result.proof.proof) == result.chain.merkle_root


def test_A5_one_changed_byte_is_not_found(
    db: Session, issue: Callable[..., PassportVersion]
) -> None:
    v1 = issue(f.student(db, 1), f.skill(db))
    pdf = bytearray(storage.get(v1.pdf_key or ""))
    pdf[len(pdf) // 2] ^= 0x01
    result = verification.verify_hash(db, verification.sha256_hex(bytes(pdf)))
    assert result.verdict == "NOT_FOUND"
    assert (result.checks.document, result.checks.issuer) == (False, False)
    assert result.version is None and result.proof is None


def test_A6_an_older_version_is_superseded(
    db: Session, issue: Callable[..., PassportVersion]
) -> None:
    st = f.student(db, 1)
    v1 = issue(st, f.skill(db, "SKL-001"))
    v2 = issue(st, f.skill(db, "SKL-002"))
    old = verification.verify_code(db, v1.verification_code or "")
    assert (old.verdict, old.latest_version_no) == ("SUPERSEDED", 2)
    assert old.latest_issued_at == v2.issued_at  # when the newer version was issued
    assert old.version is not None and old.version.version_no == 1
    latest = verification.verify_code(db, v2.verification_code or "")
    assert (latest.verdict, latest.latest_issued_at) == ("VALID", v2.issued_at)


def test_A7_a_registry_btu_does_not_own_is_not_issued_by_btu(
    db: Session, issue: Callable[..., PassportVersion], fake_chain: FakeChain
) -> None:
    v1 = issue(f.student(db, 1), f.skill(db))
    fake_chain.owner_address = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"  # Anvil #1
    result = verification.verify_code(db, v1.verification_code or "")
    assert result.verdict == "NOT_ISSUED_BY_BTU"
    assert (result.checks.document, result.checks.issuer) == (True, False)
    assert result.version is None  # no personal data unless BTU's registry vouches for it
    assert result.chain is not None and result.proof is not None  # the browser can re-check


def test_a_batch_on_another_contract_is_not_issued_by_btu(
    db: Session, issue: Callable[..., PassportVersion]
) -> None:
    v1 = issue(f.student(db, 1), f.skill(db))
    db.execute(update(AnchorBatch).values(contract_address="0x" + "11" * 20))
    db.commit()
    assert verification.verify_code(db, v1.verification_code or "").verdict == "NOT_ISSUED_BY_BTU"


def test_an_anchored_row_whose_root_is_not_on_chain_is_not_found(
    db: Session, issue: Callable[..., PassportVersion], fake_chain: FakeChain
) -> None:
    v1 = issue(f.student(db, 1), f.skill(db))
    fake_chain.signer.receipts.clear()  # e.g. the chain was reset
    result = verification.verify_code(db, v1.verification_code or "")
    assert result.verdict == "NOT_FOUND"
    assert (result.checks.document, result.checks.issuer) == (False, True)
    assert result.version is None


def test_a_revoked_leaf_is_revoked(
    db: Session, issue: Callable[..., PassportVersion], fake_chain: FakeChain
) -> None:
    v1 = issue(f.student(db, 1), f.skill(db))
    fake_chain.revoked.add(merkle.leaf(v1.pdf_sha256 or ""))
    assert verification.verify_code(db, v1.verification_code or "").verdict == "REVOKED"


def test_codes_accept_any_case_dashes_and_look_alikes(
    db: Session, issue: Callable[..., PassportVersion]
) -> None:
    v1 = issue(f.student(db, 1), f.skill(db))
    code = v1.verification_code or ""
    typed = f"{code[:4]}-{code[4:8]}-{code[8:]}".lower()
    assert verification.verify_code(db, typed).verdict == "VALID"
    assert verification.verify_code(db, "not a code!").verdict == "UNKNOWN_CODE"
    assert verification.verify_code(db, "ZZZZZZZZZZ").verdict == "UNKNOWN_CODE"


def test_hashes_accept_0x_and_any_case(db: Session, issue: Callable[..., PassportVersion]) -> None:
    v1 = issue(f.student(db, 1), f.skill(db))
    assert verification.verify_hash(db, "0x" + (v1.pdf_sha256 or "").upper()).verdict == "VALID"


def test_versions_that_are_not_anchored_are_not_verifiable(
    db: Session, issue: Callable[..., PassportVersion]
) -> None:
    v1 = issue(f.student(db, 1), f.skill(db))
    db.execute(update(PassportVersion).values(status="FAILED"))
    db.commit()
    assert verification.verify_code(db, v1.verification_code or "").verdict == "UNKNOWN_CODE"
    assert verification.verify_hash(db, v1.pdf_sha256 or "").verdict == "NOT_FOUND"


def test_an_unreachable_chain_raises(
    db: Session, issue: Callable[..., PassportVersion], fake_chain: FakeChain
) -> None:
    v1 = issue(f.student(db, 1), f.skill(db))
    fake_chain.down = True
    with pytest.raises(ChainUnavailable):
        verification.verify_code(db, v1.verification_code or "")
