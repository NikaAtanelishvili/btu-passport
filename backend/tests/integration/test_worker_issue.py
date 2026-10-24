"""BE-27: ISSUE_VERSION renders the PDF, stores it by hash and freezes the content."""

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job, Passport, PassportVersion
from app.services import issuance, storage
from tests import factories as f
from worker import loop
from worker.jobs import HANDLERS


def _version(db: Session, version_id: int) -> PassportVersion:
    db.expire_all()
    v = db.get(PassportVersion, version_id)
    assert v is not None
    return v


def _make(db: Session) -> int:
    st = f.student(db, 1)
    f.award(db, st, f.skill(db))
    [made] = issuance.create_versions(db, [st.student_id])
    db.commit()
    return made.version_id


def test_pending_becomes_rendered_with_pdf_in_storage(db: Session, s3_bucket: str) -> None:
    version_id = _make(db)
    HANDLERS["ISSUE_VERSION"].run(db, {"version_id": version_id})
    db.commit()
    v = _version(db, version_id)
    assert v.status == "RENDERED"
    assert v.verification_code and re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{10}", v.verification_code)
    assert v.pdf_sha256 and re.fullmatch(r"[0-9a-f]{64}", v.pdf_sha256)
    assert v.pdf_key == f"pdf/{v.pdf_sha256}.pdf"
    pdf = storage.get(v.pdf_key)
    assert hashlib.sha256(pdf).hexdigest() == v.pdf_sha256
    assert v.issued_at is not None and v.issued_at.microsecond == 0
    assert v.content_json is not None
    assert v.content_json["verification_code"] == v.verification_code
    assert v.content_json["issued_at"] == v.issued_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    passport = db.get(Passport, v.passport_id)
    assert passport is not None and passport.first_issued_on is not None  # frozen at first issue


def test_repeat_run_is_a_no_op(db: Session, s3_bucket: str) -> None:
    version_id = _make(db)
    HANDLERS["ISSUE_VERSION"].run(db, {"version_id": version_id})
    db.commit()
    first = _version(db, version_id)
    code, sha = first.verification_code, first.pdf_sha256
    HANDLERS["ISSUE_VERSION"].run(db, {"version_id": version_id})
    db.commit()
    again = _version(db, version_id)
    assert (again.verification_code, again.pdf_sha256) == (code, sha)


def test_render_error_after_the_last_attempt_fails_the_version(db: Session) -> None:
    version_id = _make(db)
    handler = HANDLERS["ISSUE_VERSION"]
    assert handler.give_up is not None
    handler.give_up(db, {"version_id": version_id}, "template missing")
    db.commit()
    v = _version(db, version_id)
    assert (v.status, v.error) == ("FAILED", "rendering failed: template missing")


def test_the_queue_runs_the_job(db: Session, s3_bucket: str) -> None:
    version_id = _make(db)
    assert loop.run_once() is True
    assert _version(db, version_id).status == "RENDERED"
    job = db.scalars(select(Job).where(Job.type == "ISSUE_VERSION")).one()
    assert job.status == "DONE"
