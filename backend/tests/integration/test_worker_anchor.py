"""BE-28: ANCHOR_BATCH — one Merkle tree and one transaction per batch, crash-safe retries."""

from collections.abc import Callable

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import AnchorBatch, Job, Passport, PassportVersion
from app.services import issuance, merkle
from tests import factories as f
from tests.conftest import FakeSigner
from worker.jobs import HANDLERS

RunJobs = Callable[[], int]


def _rendered(db: Session, n_students: int, run_jobs: RunJobs, signer: FakeSigner) -> list[int]:
    """n students with one award each, rendered but not anchored (signer down)."""
    sk = f.skill(db)
    sts = [f.student(db, n) for n in range(1, n_students + 1)]
    for st in sts:
        f.award(db, st, sk)
    made = issuance.create_versions(db, [st.student_id for st in sts])
    db.commit()
    for m in made:
        HANDLERS["ISSUE_VERSION"].run(db, {"version_id": m.version_id})
    db.commit()
    return [m.version_id for m in made]


def _anchor(db: Session) -> None:
    HANDLERS["ANCHOR_BATCH"].run(db, {})
    db.commit()


def _versions(db: Session, ids: list[int]) -> list[PassportVersion]:
    db.expire_all()
    return [v for i in ids if (v := db.get(PassportVersion, i)) is not None]


def test_three_versions_share_one_batch_and_one_transaction(
    db: Session, s3_bucket: str, fake_signer: FakeSigner, run_jobs: RunJobs
) -> None:
    ids = _rendered(db, 3, run_jobs, fake_signer)
    _anchor(db)
    versions = _versions(db, ids)
    batch = db.scalars(select(AnchorBatch)).one()
    root, _ = merkle.build_tree([v.pdf_sha256 or "" for v in versions])
    assert fake_signer.calls == [(root, 3)]
    assert (batch.merkle_root, batch.leaf_count, batch.status) == (root, 3, "ANCHORED")
    assert batch.tx_hash and batch.block_number and batch.anchored_at
    assert (batch.chain_id, batch.attempts) == (31337, 0)
    for v in versions:
        assert (v.status, v.batch_id) == ("ANCHORED", batch.batch_id)
        leaf = merkle.leaf(v.pdf_sha256 or "")
        assert merkle.process_proof(leaf, v.merkle_proof or []) == root
        passport = db.get(Passport, v.passport_id)
        assert passport is not None and passport.latest_version_id == v.version_id


def test_signer_down_keeps_the_batch_and_retries_the_same_root(
    db: Session, s3_bucket: str, fake_signer: FakeSigner, run_jobs: RunJobs
) -> None:
    ids = _rendered(db, 2, run_jobs, fake_signer)
    fake_signer.fail = True
    with pytest.raises(Exception, match="signer unreachable"):
        _anchor(db)
    db.rollback()
    batch = db.scalars(select(AnchorBatch)).one()
    assert (batch.status, batch.attempts) == ("SUBMITTING", 1)
    assert batch.last_error and "signer unreachable" in batch.last_error
    assert {v.status for v in _versions(db, ids)} == {"ANCHORING"}

    # A version rendered meanwhile is not added to the unfinished batch.
    late = _rendered_one_more(db)
    fake_signer.fail = False
    _anchor(db)
    assert [c[0] for c in fake_signer.calls] == [batch.merkle_root, batch.merkle_root]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(AnchorBatch)) == 1
    assert {v.status for v in _versions(db, ids)} == {"ANCHORED"}
    assert _versions(db, [late])[0].status == "RENDERED"  # next batch


def _rendered_one_more(db: Session) -> int:
    st = f.student(db, 50)
    f.award(db, st, f.skill(db, "SKL-050"))
    [m] = issuance.create_versions(db, [st.student_id])
    db.commit()
    HANDLERS["ISSUE_VERSION"].run(db, {"version_id": m.version_id})
    db.commit()
    return m.version_id


def test_batch_fails_after_max_attempts(
    db: Session, s3_bucket: str, fake_signer: FakeSigner, run_jobs: RunJobs
) -> None:
    ids = _rendered(db, 2, run_jobs, fake_signer)
    fake_signer.fail = True
    for _ in range(4):
        with pytest.raises(Exception, match="signer unreachable"):
            _anchor(db)
        db.rollback()
    _anchor(db)  # fifth failure: gives up without raising
    batch = db.scalars(select(AnchorBatch)).one()
    db.refresh(batch)
    assert (batch.status, batch.attempts) == ("FAILED", 5)
    for v in _versions(db, ids):
        assert v.status == "FAILED"
        assert v.error and v.error.startswith("anchoring failed: signer unreachable")


def test_retried_versions_with_the_same_leaves_reuse_the_failed_batch(
    db: Session, s3_bucket: str, fake_signer: FakeSigner, run_jobs: RunJobs
) -> None:
    ids = _rendered(db, 1, run_jobs, fake_signer)
    fake_signer.fail = True
    for _ in range(4):
        with pytest.raises(Exception, match="signer unreachable"):
            _anchor(db)
        db.rollback()
    _anchor(db)
    # Retry (BE-29 logic): back to RENDERED without batch or proof.
    db.execute(
        update(PassportVersion)
        .where(PassportVersion.version_id.in_(ids))
        .values(status="RENDERED", batch_id=None, merkle_proof=None, error=None)
    )
    db.commit()
    fake_signer.fail = False
    _anchor(db)  # same single leaf -> same root as the FAILED batch
    batch = db.scalars(select(AnchorBatch)).one()
    db.refresh(batch)
    assert batch.status == "ANCHORED"
    assert _versions(db, ids)[0].status == "ANCHORED"


def test_latest_version_only_moves_forward(
    db: Session, s3_bucket: str, fake_signer: FakeSigner, run_jobs: RunJobs
) -> None:
    st = f.student(db, 1)
    f.award(db, st, f.skill(db))
    v1, v2 = (issuance.create_versions(db, [st.student_id])[0] for _ in range(2))
    db.commit()
    for v in (v2, v1):  # v2 is rendered and anchored first
        HANDLERS["ISSUE_VERSION"].run(db, {"version_id": v.version_id})
        db.commit()
        _anchor(db)
    passport = db.get(Passport, "BTU-AI-000001")
    db.refresh(passport)
    assert passport is not None and passport.latest_version_id == v2.version_id


def test_batch_size_is_capped(
    db: Session,
    s3_bucket: str,
    fake_signer: FakeSigner,
    run_jobs: RunJobs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "batch_max_leaves", 2)
    _rendered(db, 3, run_jobs, fake_signer)
    _anchor(db)
    _anchor(db)
    assert [c[1] for c in fake_signer.calls] == [2, 1]


def test_the_anchor_tick_enqueues_one_deduped_job(
    db: Session, s3_bucket: str, fake_signer: FakeSigner, run_jobs: RunJobs
) -> None:
    from worker import ticks

    _rendered(db, 1, run_jobs, fake_signer)
    assert ticks.anchor_tick(db) is True
    assert ticks.anchor_tick(db) is False
    db.commit()
    assert db.scalar(select(func.count()).where(Job.type == "ANCHOR_BATCH")) == 1
    run_jobs()
    assert db.scalar(select(func.count()).where(AnchorBatch.status == "ANCHORED")) == 1
