"""Postgres job queue (BE-26): enqueue from the API, claim/finish from the worker.

Claiming uses FOR UPDATE SKIP LOCKED, so several worker processes can run safely.
"""

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Job

STALE_AFTER = "5 minutes"


def enqueue(
    db: Session,
    type_: str,
    payload: dict[str, Any],
    dedupe_key: str | None = None,
    max_attempts: int | None = None,
) -> int | None:
    """Insert a QUEUED job in the caller's transaction. Returns its id, or None when a
    QUEUED/RUNNING job with the same dedupe_key already exists (silently ignored)."""
    values: dict[str, Any] = {
        "type": type_,
        "payload": payload,
        "status": "QUEUED",
        "dedupe_key": dedupe_key,
    }
    if max_attempts is not None:
        values["max_attempts"] = max_attempts
    stmt = (
        insert(Job)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=["dedupe_key"],
            index_where=text("status IN ('QUEUED', 'RUNNING')"),
        )
        .returning(Job.job_id)
    )
    return db.scalar(stmt)


_CLAIM = text("""
    UPDATE jobs SET status = 'RUNNING', locked_at = now(), attempts = attempts + 1
    WHERE job_id = (SELECT job_id FROM jobs
                    WHERE status = 'QUEUED' AND run_after <= now()
                    ORDER BY job_id FOR UPDATE SKIP LOCKED LIMIT 1)
    RETURNING job_id
""")


def claim(db: Session) -> Job | None:
    """Take the oldest ready job. The caller commits to release the row lock."""
    job_id = db.scalar(_CLAIM)
    if job_id is None:
        return None
    return db.scalars(
        select(Job).where(Job.job_id == job_id).execution_options(populate_existing=True)
    ).one()


def finish(db: Session, job_id: int) -> None:
    db.execute(text("UPDATE jobs SET status = 'DONE' WHERE job_id = :id"), {"id": job_id})


def fail(db: Session, job_id: int, error: str) -> bool:
    """Back off and requeue (1, 2, 4, 8 … minutes), or mark FAILED after the last attempt.
    Returns True when the job has given up."""
    status = db.scalar(
        text("""
            UPDATE jobs SET last_error = :error,
              status = CASE WHEN attempts < max_attempts THEN 'QUEUED' ELSE 'FAILED' END,
              run_after = CASE WHEN attempts < max_attempts
                          THEN now() + make_interval(mins => power(2, attempts - 1)::int)
                          ELSE run_after END
            WHERE job_id = :id RETURNING status
        """),
        {"id": job_id, "error": error[:2000]},
    )
    return bool(status == "FAILED")


def requeue_stale(db: Session) -> int:
    """RUNNING jobs locked more than 5 minutes ago belong to a crashed worker: requeue them."""
    result = db.execute(
        text(f"""
            UPDATE jobs SET status = 'QUEUED', locked_at = NULL
            WHERE status = 'RUNNING' AND locked_at < now() - interval '{STALE_AFTER}'
        """)
    )
    return int(result.rowcount)  # type: ignore[attr-defined]
