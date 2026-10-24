"""Admin dashboard (BE-35, page A1)."""

from pydantic import BaseModel

from app.schemas.version import VersionRow


class Dashboard(BaseModel):
    checkin_open: int  # events with check-in open now
    awaiting_completion: int  # check-in closed, not yet marked done
    unregistered_checkins: int  # live check-ins with no student record, in open events
    failed_versions: int
    recent: list[VersionRow]  # last 10 issued (ANCHORED) versions
