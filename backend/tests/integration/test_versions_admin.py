"""BE-29: issuance page API — version list, retry, retry-failed, admin PDF download."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditLog, Job, PassportVersion
from app.services import issuance
from tests import factories as f
from tests.conftest import FakeSigner

ClientAs = Callable[[str | None], TestClient]
RunJobs = Callable[[], int]


@pytest.fixture
def admin(db: Session, client_as: ClientAs) -> TestClient:
    return client_as("admin")


def _two_versions(db: Session) -> list[int]:
    sk = f.skill(db)
    sts = [f.student(db, n) for n in (2, 3)]
    for st in sts:
        f.award(db, st, sk)
    made = issuance.create_versions(db, [st.student_id for st in sts])
    db.commit()
    return [m.version_id for m in made]


def _set(db: Session, version_id: int, **values: object) -> None:
    db.execute(
        update(PassportVersion).where(PassportVersion.version_id == version_id).values(**values)
    )
    db.commit()


def test_list_filters_by_status_and_passport(db: Session, admin: TestClient) -> None:
    a, b = _two_versions(db)
    _set(db, a, status="FAILED", error="anchoring failed: x")
    r = admin.get("/api/admin/versions", params={"status": "FAILED,PENDING"})
    assert r.status_code == 200
    page = r.json()
    assert page["total"] == 2 and [i["version_id"] for i in page["items"]] == [b, a]  # newest first
    row = page["items"][1]
    assert row == {
        "version_id": a,
        "passport_id": "BTU-AI-000002",
        "student_id": "BTU-T-0002",
        "student_name": "Nino Test",
        "version_no": 1,
        "status": "FAILED",
        "error": "anchoring failed: x",
        "issued_at": None,
        "created_at": row["created_at"],
    }
    only = admin.get("/api/admin/versions", params={"passport_id": "BTU-AI-000003"}).json()
    assert [i["version_id"] for i in only["items"]] == [b]


def test_retry_rendered_failure_goes_back_to_rendered(db: Session, admin: TestClient) -> None:
    a, _ = _two_versions(db)
    _set(db, a, status="FAILED", pdf_sha256="ab" * 32, merkle_proof=["0x" + "00" * 32], error="e")
    r = admin.post(f"/api/admin/versions/{a}/retry")
    assert r.status_code == 202 and r.json()["status"] == "RENDERED"
    db.expire_all()
    v = db.get_one(PassportVersion, a)
    assert (v.status, v.batch_id, v.merkle_proof, v.error) == ("RENDERED", None, None, None)
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "version.retry")).one()
    assert audit.entity_id == str(a) and audit.actor_email == "admin@btu.test"


def test_retry_render_failure_requeues_the_job(db: Session, admin: TestClient) -> None:
    a, _ = _two_versions(db)
    _set(db, a, status="FAILED", error="rendering failed: x")
    before = len(db.scalars(select(Job)).all())
    r = admin.post(f"/api/admin/versions/{a}/retry")
    assert r.status_code == 202 and r.json()["status"] == "PENDING"
    jobs = db.scalars(select(Job).order_by(Job.job_id)).all()
    assert len(jobs) == before + 1 and jobs[-1].payload == {"version_id": a}


def test_retry_needs_a_failed_version(db: Session, admin: TestClient) -> None:
    a, _ = _two_versions(db)
    r = admin.post(f"/api/admin/versions/{a}/retry")
    assert (r.status_code, r.json()["error"]) == (409, "not_failed")
    assert admin.post("/api/admin/versions/999999/retry").status_code == 404


def test_retry_failed_retries_all(db: Session, admin: TestClient) -> None:
    a, b = _two_versions(db)
    _set(db, a, status="FAILED", error="x")
    _set(db, b, status="FAILED", error="y")
    r = admin.post("/api/admin/versions/retry-failed")
    assert r.json() == {"count": 2}
    assert admin.post("/api/admin/versions/retry-failed").json() == {"count": 0}


def test_pdf_only_for_anchored_versions(
    db: Session,
    s3_bucket: str,
    admin: TestClient,
    fake_signer: FakeSigner,
    run_jobs: RunJobs,
) -> None:
    a, _ = _two_versions(db)
    assert admin.get(f"/api/admin/versions/{a}/pdf").status_code == 404  # PENDING
    run_jobs()
    r = admin.get(f"/api/admin/versions/{a}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    assert "BTU-AI-000002-v1.pdf" in r.headers["content-disposition"]


def test_student_gets_403(db: Session, client_as: ClientAs) -> None:
    assert client_as("student").get("/api/admin/versions").status_code == 403
