"""SH-13: smoke test against the real Google Sheet. Runs only when .env sets GOOGLE_SHEETS_ID
(the test settings blank it, so it is read from the file). Read-only: write-back is off, and
the engine runs against the test database."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.sheets import sync
from app.sheets.source import SKILLS, STUDENTS, TABS, VERIFIED, GoogleSheetSource


def _sheet_id(env: Path = REPO_ROOT / ".env") -> str:
    if not env.exists():
        return ""
    for line in env.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "GOOGLE_SHEETS_ID":
            return value.strip().strip("'\"")
    return ""


SHEET_ID = _sheet_id()
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not SHEET_ID, reason="GOOGLE_SHEETS_ID is not set in .env"),
    pytest.mark.usefixtures("s3_bucket"),
]


def test_reads_the_three_tabs() -> None:
    tabs = GoogleSheetSource(SHEET_ID, writeback=False).read()
    assert list(tabs) == list(TABS)
    assert all(tab.missing() == [] for tab in tabs.values())
    assert len(tabs[STUDENTS].rows) >= 18
    assert len(tabs[SKILLS].rows) >= 16
    assert len(tabs[VERIFIED].rows) >= 60


def test_sync_against_the_seed(seeded: Session) -> None:
    result = sync.sync_now(GoogleSheetSource(SHEET_ID, writeback=False))
    assert result.status == "DONE", result.error
    by_key = {(d.tab, d.key): d for d in result.decisions}
    # Every hackathon record is already on its passport, whatever rows were added since.
    for n in range(1, 61):
        assert by_key[(VERIFIED, f"REC-{n:04d}")].outcome == "DUPLICATE"
    assert by_key[(STUDENTS, "BTU-T-0001")].outcome == "UNCHANGED"
