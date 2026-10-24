"""BE-32: the public verify routes (fake chain; the Anvil versions are tests/chain/test_verify.py).
No sign-in and no CSRF header: these are for anyone holding a code or a PDF."""

import hashlib
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PassportVersion, SkillCategory
from app.services import issuance, merkle, storage
from tests import factories as f
from tests.conftest import FakeChain

RunJobs = Callable[[], int]
ClientAs = Callable[[str | None], TestClient]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def v1(db: Session, s3_bucket: str, fake_chain: FakeChain, run_jobs: RunJobs) -> PassportVersion:
    """BTU-AI-000001 v1, anchored, with one skill whose category has a stamp."""
    st, sk = f.student(db, 1), f.skill(db)
    stamp = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"/>'
    sha = _sha256(stamp)
    storage.put(f"stamps/{sha}.svg", stamp, "image/svg+xml")
    db.execute(update(SkillCategory).values(stamp_sha256=sha, stamp_key=f"stamps/{sha}.svg"))
    f.award(db, st, sk)
    (made,) = issuance.create_versions(db, [st.student_id])
    db.commit()
    run_jobs()
    db.expire_all()
    return db.get_one(PassportVersion, made.version_id)


@pytest.fixture
def anon(client_as: ClientAs) -> TestClient:
    return client_as(None)


def test_verify_by_code(anon: TestClient, v1: PassportVersion) -> None:
    r = anon.get(f"/api/verify/{(v1.verification_code or '').lower()}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "VALID"
    assert body["checks"] == {"document": True, "issuer": True}
    assert body["version"]["verification_code"] == v1.verification_code
    assert body["version"]["skills"][0]["stamp_sha256"]
    assert body["chain"]["merkle_root"] and body["proof"]["leaf"]


def test_unknown_code_is_a_verdict_not_an_error(anon: TestClient, v1: PassportVersion) -> None:
    for code in ("AAAA-AAAA-AA", "%%%"):
        r = anon.get(f"/api/verify/{code}")
        assert (r.status_code, r.json()["verdict"]) == (200, "UNKNOWN_CODE")


def test_verify_by_hash_takes_only_the_hash(anon: TestClient, v1: PassportVersion) -> None:
    r = anon.post("/api/verify/hash", json={"sha256": v1.pdf_sha256})
    assert (r.status_code, r.json()["verdict"]) == (200, "VALID")
    r = anon.post("/api/verify/hash", json={"sha256": "0x" + "00" * 32})
    assert (r.status_code, r.json()["verdict"]) == (200, "NOT_FOUND")
    r = anon.post("/api/verify/hash", json={"sha256": "not-a-hash"})
    assert (r.status_code, r.json()["error"]) == (422, "validation_error")
    assert "sha256" in r.json()["fields"]


def test_a_signed_in_user_needs_no_csrf_header_either_way(
    client_as: ClientAs, v1: PassportVersion
) -> None:
    client = client_as("admin")  # sends the CSRF header like the web client
    r = client.post("/api/verify/hash", json={"sha256": v1.pdf_sha256})
    assert r.json()["verdict"] == "VALID"


def test_an_unreachable_chain_is_503(
    anon: TestClient, v1: PassportVersion, fake_chain: FakeChain
) -> None:
    fake_chain.down = True
    r = anon.get(f"/api/verify/{v1.verification_code}")
    assert (r.status_code, r.json()["error"]) == (503, "chain_unavailable")


def test_official_pdf_is_the_stored_bytes(anon: TestClient, v1: PassportVersion) -> None:
    r = anon.get(f"/api/verify/{v1.verification_code}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == storage.get(v1.pdf_key or "")
    assert _sha256(r.content) == v1.pdf_sha256


def test_proof_file(anon: TestClient, v1: PassportVersion) -> None:
    s = get_settings()
    r = anon.get(f"/api/verify/{v1.verification_code}/proof.json")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    proof = r.json()
    assert proof["schema"] == "btu-ai-passport-proof/1"
    assert (proof["passport_id"], proof["version_no"]) == ("BTU-AI-000001", 1)
    assert proof["pdf_sha256"] == "0x" + (v1.pdf_sha256 or "")
    assert proof["leaf"] == merkle.leaf(v1.pdf_sha256 or "")
    assert merkle.process_proof(proof["leaf"], proof["proof"]) == proof["merkle_root"]
    assert (proof["chain_id"], proof["contract_address"]) == (s.chain_id, s.contract_address)
    assert proof["issuer_address"] == s.issuer_address
    assert proof["tx_hash"].startswith("0x") and proof["anchored_at"].endswith("Z")
    assert proof["issuer_file_url"].endswith("/.well-known/ai-passport-issuer.json")


def test_only_anchored_versions_are_downloadable(
    db: Session, anon: TestClient, v1: PassportVersion
) -> None:
    db.execute(update(PassportVersion).values(status="FAILED"))
    db.commit()
    for path in ("pdf", "proof.json"):
        assert anon.get(f"/api/verify/{v1.verification_code}/{path}").status_code == 404
    assert anon.get("/api/verify/AAAA-AAAA-AA/pdf").status_code == 404


def test_stamps_are_public_and_content_addressed(anon: TestClient, v1: PassportVersion) -> None:
    sha = (v1.content_json or {})["skills"][0]["stamp_sha256"]
    r = anon.get(f"/api/stamps/{sha}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert _sha256(r.content) == sha
    assert "immutable" in r.headers["cache-control"]
    assert anon.get(f"/api/stamps/{'0' * 64}").status_code == 404
    assert anon.get("/api/stamps/..%2Fpdf").status_code == 404
