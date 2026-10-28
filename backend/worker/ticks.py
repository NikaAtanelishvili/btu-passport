"""Worker timers (BE-26), checked on every loop iteration: anchoring, stale jobs, the event
tick (every 15 s, BE-40) that opens and closes check-in by each event's window, and the Sheet
tick (every 5 s, SH-05) that queues a sync once SHEET_SYNC_INTERVAL_SECONDS has passed."""

import logging
import time

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import AnchorBatch, PassportVersion
from app.services import events, jobs
from app.sheets import service as sheets

log = logging.getLogger("worker")
STALE_CHECK_SECONDS = 60
EVENT_TICK_SECONDS = 15
SHEET_TICK_SECONDS = 5


def anchor_tick(db: Session) -> bool:
    """Enqueue ANCHOR_BATCH (deduped) if a version waits to be anchored or a batch is unfinished."""
    pending = db.scalar(
        select(
            or_(
                exists().where(PassportVersion.status == "RENDERED"),
                exists().where(AnchorBatch.status == "SUBMITTING"),
            )
        )
    )
    if pending:
        return jobs.enqueue(db, "ANCHOR_BATCH", {}, dedupe_key="anchor") is not None
    return False


class Timers:
    def __init__(self) -> None:
        self.anchor_every = get_settings().anchor_interval_seconds
        self.next_anchor = 0.0
        self.next_stale_check = time.monotonic() + STALE_CHECK_SECONDS
        self.next_event_tick = 0.0
        self.next_sheet_tick = 0.0

    def run_due(self) -> None:
        now = time.monotonic()
        if now >= self.next_stale_check:
            # Not only at start: a worker restarted within the stale timeout of a crash
            # would otherwise leave the crashed worker's job RUNNING for good.
            self.next_stale_check = now + STALE_CHECK_SECONDS
            with SessionLocal() as db:
                if n := jobs.requeue_stale(db):
                    log.info("requeued %s job(s) left RUNNING by a crashed worker", n)
                db.commit()
        if now >= self.next_event_tick:
            self.next_event_tick = now + EVENT_TICK_SECONDS
            with SessionLocal() as db:
                if n := events.tick(db):
                    log.info("event tick: %s event(s) opened or closed", n)
                db.commit()
        if now >= self.next_sheet_tick:
            self.next_sheet_tick = now + SHEET_TICK_SECONDS
            with SessionLocal() as db:
                if run_id := sheets.tick(db):
                    log.info("sheet tick: sync run %s queued", run_id)
                db.commit()
        if now >= self.next_anchor:
            self.next_anchor = now + self.anchor_every
            with SessionLocal() as db:
                anchor_tick(db)
                db.commit()
