"""The worker loop (BE-26): claim a job, run it in its own transaction, repeat; plus timers."""

import logging
import os
import signal
import time
from pathlib import Path
from types import FrameType

from app.db import SessionLocal
from app.services import jobs
from worker import ticks
from worker.jobs import HANDLERS

log = logging.getLogger("worker")


def run_once() -> bool:
    """Claim and run one job. Returns False when no job was ready."""
    with SessionLocal() as db:
        job = jobs.claim(db)
        db.commit()
    if job is None:
        return False
    handler = HANDLERS[job.type]
    log.info("job %s %s %s (attempt %s)", job.job_id, job.type, job.payload, job.attempts)
    try:
        with jobs.heartbeat(job.job_id), SessionLocal() as db:
            handler.run(db, job.payload)
            db.commit()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        log.warning("job %s failed: %s", job.job_id, error)
        with SessionLocal() as db:
            gave_up = jobs.fail(db, job.job_id, str(exc))
            if gave_up and handler.give_up is not None:
                handler.give_up(db, job.payload, str(exc))
            db.commit()
    else:
        with SessionLocal() as db:
            jobs.finish(db, job.job_id)
            db.commit()
    return True


class _Stop:
    requested = False

    def __call__(self, signum: int, _: FrameType | None) -> None:
        log.info("signal %s: finishing the current job, then exiting", signum)
        self.requested = True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
    stop = _Stop()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with SessionLocal() as db:
        if n := jobs.requeue_stale(db):
            log.info("requeued %s job(s) left RUNNING by a crashed worker", n)
        db.commit()
    timers = ticks.Timers()
    # Container healthcheck (docker_healthcheck.py): the file's age shows the loop is alive.
    heartbeat = os.environ.get("WORKER_HEARTBEAT_FILE")
    log.info("worker started")
    while not stop.requested:
        if heartbeat:
            Path(heartbeat).touch()
        timers.run_due()
        if not run_once():
            time.sleep(1)
    log.info("worker stopped")
