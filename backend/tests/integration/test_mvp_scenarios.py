"""SH-13: one test per scenario of the hackathon spec's MVP table (docs/spec/), driven through the
Sheet engine with a FileSource-like table, the real worker jobs, a fake signer and a fake chain.

The live smoke test against the real Google Sheet is tests/live/test_sheet_live.py.
"""

import hashlib
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import sessions
from app.config import get_settings
from app.main import create_app
from app.models import Passport, PassportVersion, SheetRecord, SkillAward
from app.services import issuance, storage
from app.sheets import service, sync
from app.sheets.source import STUDENTS, VERIFIED
from tests import factories
from tests.integration.test_sheet_sync import TableSource, new_student, record

pytestmark = pytest.mark.usefixtures("s3_bucket")
RunJobs = Callable[[], int]

NEW = "BTU-T-0030"
GIORGI = "BTU-T-0001"  # BTU-AI-000125: four seed skills


@pytest.fixture
def world(seeded: Session, fake_chain: Any, run_jobs: RunJobs) -> TableSource:
    """Giorgi's passport issued and anchored; the Sheet is the seed export."""
    issuance.create_versions(seeded, [GIORGI])
    seeded.commit()
    run_jobs()
    return TableSource()


def versions(db: Session, student_id: str) -> list[PassportVersion]:
    db.expire_all()
    return list(
        db.scalars(
            select(PassportVersion)
            .join(Passport, Passport.passport_id == PassportVersion.passport_id)
            .where(Passport.student_id == student_id)
            .order_by(PassportVersion.version_no)
        )
    )


def pdf_of(version: PassportVersion) -> bytes:
    assert version.pdf_sha256
    return storage.get(storage.pdf_key(version.pdf_sha256))


def anon() -> TestClient:
    return TestClient(create_app())


def verify(pdf: bytes) -> dict[str, Any]:
    response = anon().post("/api/verify/hash", json={"sha256": hashlib.sha256(pdf).hexdigest()})
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def giorgi_gets_ai_ethics(db: Session, sheet: TableSource, run_jobs: RunJobs) -> None:
    sheet.add(VERIFIED, record("REC-0102", GIORGI, "SKL-003", through="AI Ethics Masterclass"))
    sync.sync_now(sheet)
    run_jobs()


# --- The MVP table, in order ---------------------------------------------------------------


def test_adding_a_new_student(seeded: Session, world: TableSource, run_jobs: RunJobs) -> None:
    """A single passport with a permanent ID is created."""
    world.add(STUDENTS, new_student(NEW))
    sync.sync_now(world)
    sync.sync_now(world)  # again: still one passport
    passports = seeded.scalars(select(Passport).where(Passport.student_id == NEW)).all()
    assert [p.passport_id for p in passports] == ["BTU-AI-000143"]


@pytest.mark.skipif(not shutil.which("pdfinfo"), reason="needs poppler-utils")
def test_initial_passport_generation(
    seeded: Session, world: TableSource, run_jobs: RunJobs, tmp_path: Path
) -> None:
    """A multi-page PDF on BTU's design is created."""
    world.add(STUDENTS, new_student(NEW))
    world.add(VERIFIED, record("REC-0101", NEW, "SKL-001", through="AI Literacy Workshop"))
    sync.sync_now(world)
    run_jobs()
    [v1] = versions(seeded, NEW)
    assert (v1.version_no, v1.status) == (1, "ANCHORED")
    path = tmp_path / "v1.pdf"
    path.write_bytes(pdf_of(v1))
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
    assert int(next(x.split()[-1] for x in info.splitlines() if x.startswith("Pages:"))) >= 4
    text = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True).stdout
    assert "AI LITERACY" in text.upper() and "BTU-AI-000143" in text


def test_new_verified_skill_is_detected_automatically(
    seeded: Session, world: TableSource, run_jobs: RunJobs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scheduled sync picks the new row up; nobody presses anything."""
    monkeypatch.setattr(get_settings(), "google_sheets_id", "test-sheet")
    monkeypatch.setattr(service, "source_for_run", lambda: world)
    world.add(VERIFIED, record("REC-0102", GIORGI, "SKL-003"))
    assert service.tick(seeded) is not None  # the worker's timer
    seeded.commit()
    run_jobs()
    seeded.expire_all()
    assert seeded.get_one(SheetRecord, (VERIFIED, "REC-0102")).outcome == "PROCESSED"


def test_reflecting_a_new_skill(seeded: Session, world: TableSource, run_jobs: RunJobs) -> None:
    """The student's existing passport is updated, not a new one created."""
    before = versions(seeded, GIORGI)
    giorgi_gets_ai_ethics(seeded, world, run_jobs)
    after = versions(seeded, GIORGI)
    assert len(after) == len(before) + 1
    assert {v.passport_id for v in after} == {"BTU-AI-000125"}
    assert after[-1].content_json is not None
    assert "SKL-003" in {s["skill_id"] for s in after[-1].content_json["skills"]}


def test_repeated_data_synchronization(
    seeded: Session, world: TableSource, run_jobs: RunJobs
) -> None:
    """The same entry is not added a second time."""
    giorgi_gets_ai_ethics(seeded, world, run_jobs)
    n = len(versions(seeded, GIORGI))
    for _ in range(2):
        sync.sync_now(world)
        run_jobs()
    assert len(versions(seeded, GIORGI)) == n
    awards = seeded.scalars(
        select(SkillAward).where(SkillAward.student_id == GIORGI, SkillAward.skill_id == "SKL-003")
    ).all()
    assert len(awards) == 1


def test_invalid_student_identifier(seeded: Session, world: TableSource, run_jobs: RunJobs) -> None:
    """Processing of the wrong entry halts; nothing else changes."""
    world.add(VERIFIED, record("REC-0105", "BTU-T-9999", "SKL-001"))
    before = seeded.scalars(select(PassportVersion.version_id)).all()
    result = sync.sync_now(world)
    run_jobs()
    assert result.status == "DONE"
    seeded.expire_all()
    rec = seeded.get_one(SheetRecord, (VERIFIED, "REC-0105"))
    assert (rec.outcome, rec.message) == ("ERROR", "Unknown student BTU-T-9999")
    assert seeded.scalars(select(PassportVersion.version_id)).all() == before


def test_passport_update_preserves_id_date_and_skills(
    seeded: Session, world: TableSource, run_jobs: RunJobs
) -> None:
    """Permanent Passport ID, original issue date and existing skills are preserved."""
    old = versions(seeded, GIORGI)[-1].content_json
    giorgi_gets_ai_ethics(seeded, world, run_jobs)
    new = versions(seeded, GIORGI)[-1].content_json
    assert old is not None and new is not None
    assert new["passport_id"] == old["passport_id"]
    assert new["first_issued_on"] == old["first_issued_on"]
    assert new["holder"] == old["holder"]
    assert all(skill in new["skills"] for skill in old["skills"])


def test_issuing_a_new_version(seeded: Session, world: TableSource, run_jobs: RunJobs) -> None:
    """A new official PDF and a matching verification record are created."""
    giorgi_gets_ai_ethics(seeded, world, run_jobs)
    old, new = versions(seeded, GIORGI)[-2:]
    assert new.status == "ANCHORED" and new.batch_id is not None and new.merkle_proof is not None
    assert new.verification_code and new.verification_code != old.verification_code
    assert new.pdf_sha256 and new.pdf_sha256 != old.pdf_sha256
    seeded.expire_all()
    passport = seeded.get_one(Passport, new.passport_id)
    assert passport.latest_version_id == new.version_id


def test_verifying_an_unaltered_pdf(seeded: Session, world: TableSource, run_jobs: RunJobs) -> None:
    giorgi_gets_ai_ethics(seeded, world, run_jobs)
    result = verify(pdf_of(versions(seeded, GIORGI)[-1]))
    assert result["verdict"] == "VALID"
    assert result["checks"] == {"document": True, "issuer": True}


def test_verifying_a_modified_pdf(seeded: Session, world: TableSource, run_jobs: RunJobs) -> None:
    pdf = bytearray(pdf_of(versions(seeded, GIORGI)[-1]))
    pdf[len(pdf) // 2] ^= 0x01  # one byte changed
    assert verify(bytes(pdf))["verdict"] == "NOT_FOUND"


def test_verifying_the_issuers_identity(
    seeded: Session, world: TableSource, fake_chain: Any
) -> None:
    """BTU's (test) identity is confirmed; a registry BTU doesn't own is refused."""
    issuer = anon().get("/.well-known/ai-passport-issuer.json").json()
    s = get_settings()
    assert (issuer["chain_id"], issuer["issuer_address"]) == (s.chain_id, s.issuer_address)
    pdf = pdf_of(versions(seeded, GIORGI)[-1])
    assert verify(pdf)["checks"]["issuer"] is True
    fake_chain.owner_address = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"  # not BTU
    assert verify(pdf)["verdict"] == "NOT_ISSUED_BY_BTU"


def test_verifying_an_older_version(seeded: Session, world: TableSource, run_jobs: RunJobs) -> None:
    """Authentic, but no longer the latest."""
    older = versions(seeded, GIORGI)[-1]
    giorgi_gets_ai_ethics(seeded, world, run_jobs)
    result = verify(pdf_of(older))
    assert result["verdict"] == "SUPERSEDED"
    assert result["checks"] == {"document": True, "issuer": True}
    assert result["latest_version_no"] == older.version_no + 1


def test_student_access(seeded: Session, world: TableSource, run_jobs: RunJobs) -> None:
    """The student views and downloads their own passport, and only their own."""
    giorgi_gets_ai_ethics(seeded, world, run_jobs)
    user = factories.user(seeded, "btu-t-0001@example.org")
    token, _ = sessions.create_session(seeded, user)
    seeded.commit()
    client = anon()
    client.cookies.set(get_settings().session_cookie_name, token)
    passport = client.get("/api/me/passport").json()
    assert passport["passport_id"] == "BTU-AI-000125"
    latest = passport["current"]["version_no"]
    pdf = client.get(f"/api/me/versions/{latest}/pdf")
    assert pdf.status_code == 200 and pdf.content == pdf_of(versions(seeded, GIORGI)[-1])
    assert client.get("/api/admin/students").status_code == 403
    assert anon().get("/api/me/passport").status_code == 401


def test_public_verification(seeded: Session, world: TableSource) -> None:
    """Third parties verify without signing in."""
    code = versions(seeded, GIORGI)[-1].verification_code
    response = anon().get(f"/api/verify/{code}")
    assert response.status_code == 200
    assert response.json()["verdict"] == "VALID"
