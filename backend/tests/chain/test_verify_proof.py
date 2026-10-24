"""BC-06b: shared/verify_proof.py checks a PDF with its proof.json and an RPC, without BTU's
server. Run as a separate process, the way a verifier would run it."""

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import REPO_ROOT, get_settings
from app.models import PassportVersion
from app.services import issuance
from tests import factories as f

pytestmark = pytest.mark.chain

SCRIPT = REPO_ROOT / "shared" / "verify_proof.py"
ClientAs = Callable[[str | None], TestClient]


@pytest.fixture
def files(
    db: Session,
    s3_bucket: str,
    real_signer: None,
    run_jobs: Callable[[], int],
    client_as: ClientAs,
    tmp_path: Path,
) -> dict[str, Path]:
    st, sk = f.student(db, 1), f.skill(db)
    f.award(db, st, sk)
    (made,) = issuance.create_versions(db, [st.student_id])
    db.commit()
    run_jobs()
    db.expire_all()
    code = db.get_one(PassportVersion, made.version_id).verification_code
    api = client_as(None)
    out = {"pdf": tmp_path / "passport.pdf", "proof": tmp_path / "proof.json"}
    out["pdf"].write_bytes(api.get(f"/api/verify/{code}/pdf").content)
    out["proof"].write_bytes(api.get(f"/api/verify/{code}/proof.json").content)
    out["issuer"] = tmp_path / "issuer.json"
    out["issuer"].write_bytes(api.get("/.well-known/ai-passport-issuer.json").content)
    return out


def _run(pdf: Path, proof: Path, issuer: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(pdf), str(proof)]
        + ["--rpc", get_settings().rpc_url, "--issuer-file", str(issuer)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_an_issued_pdf_is_valid(files: dict[str, Path]) -> None:
    r = _run(files["pdf"], files["proof"], files["issuer"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().splitlines()[-1] == "VALID"


def test_an_edited_pdf_is_not_valid(files: dict[str, Path], tmp_path: Path) -> None:
    pdf = bytearray(files["pdf"].read_bytes())
    pdf[len(pdf) // 2] ^= 0x01
    edited = tmp_path / "edited.pdf"
    edited.write_bytes(bytes(pdf))
    r = _run(edited, files["proof"], files["issuer"])
    assert r.returncode == 1
    assert r.stdout.strip().splitlines()[-1].startswith("NOT VALID")


def test_an_issuer_file_naming_another_owner_is_not_valid(files: dict[str, Path]) -> None:
    issuer = json.loads(files["issuer"].read_text())
    issuer["issuer_address"] = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"  # Anvil #1
    files["issuer"].write_text(json.dumps(issuer))
    r = _run(files["pdf"], files["proof"], files["issuer"])
    assert r.returncode == 1
    assert "issuer" in r.stdout.strip().splitlines()[-1]
