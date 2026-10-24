"""BE-26: the Postgres job queue and the worker loop (one iteration at a time)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Job
from app.services import jobs
from worker import loop
from worker.jobs import HANDLERS, JobHandler


def _jobs(db: Session) -> list[Job]:
    db.expire_all()
    return list(db.scalars(select(Job).order_by(Job.job_id)))


def test_enqueue_ignores_a_duplicate_dedupe_key_while_queued_or_running(db: Session) -> None:
    assert jobs.enqueue(db, "ANCHOR_BATCH", {}, dedupe_key="anchor") is not None
    assert jobs.enqueue(db, "ANCHOR_BATCH", {}, dedupe_key="anchor") is None
    db.execute(update(Job).values(status="RUNNING"))
    assert jobs.enqueue(db, "ANCHOR_BATCH", {}, dedupe_key="anchor") is None
    db.execute(update(Job).values(status="DONE"))
    assert jobs.enqueue(db, "ANCHOR_BATCH", {}, dedupe_key="anchor") is not None
    assert jobs.enqueue(db, "ISSUE_VERSION", {"version_id": 1}) is not None  # no key: always
    assert len(_jobs(db)) == 3


def test_claim_takes_the_oldest_ready_job_and_counts_the_attempt(db: Session) -> None:
    first = jobs.enqueue(db, "ISSUE_VERSION", {"version_id": 1})
    jobs.enqueue(db, "ISSUE_VERSION", {"version_id": 2})
    later = jobs.enqueue(db, "ISSUE_VERSION", {"version_id": 3})
    db.execute(update(Job).where(Job.job_id == later).values(run_after=text("now() + '1 hour'")))
    db.commit()
    job = jobs.claim(db)
    assert job is not None and job.job_id == first
    assert (job.status, job.attempts, job.locked_at is not None) == ("RUNNING", 1, True)


def test_two_workers_never_claim_the_same_job(db: Session) -> None:
    jobs.enqueue(db, "ISSUE_VERSION", {"version_id": 1})
    jobs.enqueue(db, "ISSUE_VERSION", {"version_id": 2})
    db.commit()
    a, b, c = SessionLocal(), SessionLocal(), SessionLocal()
    try:
        job_a, job_b = jobs.claim(a), jobs.claim(b)  # both transactions still open
        assert job_a is not None and job_b is not None
        assert job_a.job_id != job_b.job_id
        assert jobs.claim(c) is None  # the third finds both locked
    finally:
        for s in (a, b, c):
            s.rollback()
            s.close()


def test_stale_running_jobs_are_requeued_on_start(db: Session) -> None:
    stale = jobs.enqueue(db, "ISSUE_VERSION", {"version_id": 1})
    fresh = jobs.enqueue(db, "ISSUE_VERSION", {"version_id": 2})
    old = datetime.now(UTC) - timedelta(minutes=6)
    db.execute(update(Job).where(Job.job_id == stale).values(status="RUNNING", locked_at=old))
    db.execute(
        update(Job).where(Job.job_id == fresh).values(status="RUNNING", locked_at=text("now()"))
    )
    db.commit()
    assert jobs.requeue_stale(db) == 1
    assert [j.status for j in _jobs(db)] == ["QUEUED", "RUNNING"]


@pytest.fixture
def fake_handler(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {"run": [], "give_up": [], "fail": False}

    def run(db: Session, payload: dict[str, Any]) -> None:
        calls["run"].append(payload)
        if calls["fail"]:
            raise RuntimeError("boom")

    def give_up(db: Session, payload: dict[str, Any], error: str) -> None:
        calls["give_up"].append((payload, error))

    monkeypatch.setitem(HANDLERS, "ISSUE_VERSION", JobHandler(run=run, give_up=give_up))
    return calls


def test_success_marks_the_job_done(db: Session, fake_handler: dict[str, Any]) -> None:
    jobs.enqueue(db, "ISSUE_VERSION", {"version_id": 7})
    db.commit()
    assert loop.run_once() is True
    assert loop.run_once() is False  # queue empty
    assert fake_handler["run"] == [{"version_id": 7}]
    assert _jobs(db)[0].status == "DONE"


def test_failure_backs_off_then_fails_after_max_attempts(
    db: Session, fake_handler: dict[str, Any]
) -> None:
    fake_handler["fail"] = True
    jobs.enqueue(db, "ISSUE_VERSION", {"version_id": 7}, max_attempts=3)
    db.commit()
    delays = []
    for attempt in (1, 2):
        assert loop.run_once() is True
        job = _jobs(db)[0]
        assert (job.status, job.attempts, job.last_error) == ("QUEUED", attempt, "boom")
        delays.append(db.scalar(select(Job.run_after - Job.locked_at)))
        db.execute(update(Job).values(run_after=text("now()")))  # skip the wait
        db.commit()
    assert [round(d.total_seconds() / 60) for d in delays if d] == [1, 2]  # 1, 2, 4 … minutes
    assert fake_handler["give_up"] == []
    assert loop.run_once() is True
    job = _jobs(db)[0]
    assert (job.status, job.attempts) == ("FAILED", 3)
    assert fake_handler["give_up"] == [({"version_id": 7}, "boom")]


def test_timers_requeue_stale_jobs_while_running(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A worker killed and restarted within 5 minutes must not leave its job RUNNING forever.
    from worker import ticks

    stale = jobs.enqueue(db, "ANCHOR_BATCH", {}, dedupe_key="anchor")
    db.execute(
        update(Job).where(Job.job_id == stale).values(status="RUNNING", locked_at=text("now()"))
    )
    db.commit()
    timers = ticks.Timers()
    timers.run_due()
    assert _jobs(db)[0].status == "RUNNING"  # not stale yet
    db.execute(update(Job).values(locked_at=text("now() - interval '6 minutes'")))
    db.commit()
    timers.next_stale_check = 0.0  # due now
    timers.run_due()
    assert _jobs(db)[0].status == "QUEUED"
