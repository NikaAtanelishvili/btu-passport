"""Worker timers (BE-26), checked on every loop iteration.

The event tick (every 15 s, BE-40) is added with events in M7.
"""

import time

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import AnchorBatch, PassportVersion
from app.services import jobs


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

    def run_due(self) -> None:
        now = time.monotonic()
        if now >= self.next_anchor:
            self.next_anchor = now + self.anchor_every
            with SessionLocal() as db:
                anchor_tick(db)
                db.commit()
