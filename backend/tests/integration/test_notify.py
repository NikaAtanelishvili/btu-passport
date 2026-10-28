"""SH-10: one email to the student when a version with new skills is anchored."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services import mailer
from app.sheets import sync
from app.sheets.source import VERIFIED
from cli.__main__ import issue_pending
from tests.integration.test_sheet_sync import TableSource, record

pytestmark = pytest.mark.usefixtures("s3_bucket", "fake_signer")


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    monkeypatch.setattr(mailer, "send_version_notice", lambda **kw: out.append(kw))
    return out


def test_sheet_award_sends_exactly_one_email(
    seeded: Session, sent: list[dict[str, Any]], run_jobs: Callable[[], int]
) -> None:
    issue_pending()
    run_jobs()
    assert sent == []  # seeded students' first issued versions: no email

    sheet = TableSource().add(VERIFIED, record("REC-0102", "BTU-T-0001", "SKL-003"))
    sync.sync_now(sheet)
    run_jobs()
    sync.sync_now(sheet)  # a repeated sync adds nothing, so nothing more is sent
    run_jobs()
    assert len(sent) == 1
    [notice] = sent
    assert notice["email"] == "btu-t-0001@example.org"
    assert notice["first_name"] == "Giorgi"
    assert notice["passport_id"] == "BTU-AI-000125"
    assert notice["version_no"] == 3  # LEGACY v1, issue-pending v2, the Sheet's v3
    assert notice["skills"] == ["AI Ethics & Responsible Use"]
    assert notice["url"] == "http://localhost:3000/me"


def test_no_email_for_an_empty_first_version(
    seeded: Session,
    sent: list[dict[str, Any]],
    run_jobs: Callable[[], int],
    client_as: Callable[[str | None], TestClient],
) -> None:
    admin = client_as("admin")
    body = {
        "student_id": "BTU-T-0100",
        "first_name": "Giorgi",
        "last_name": "Test",
        "email": "btu-t-0100@example.org",
        "program": "IT",
        "education_level": "BACHELOR",
        "status": "ACTIVE",
    }
    assert admin.post("/api/admin/students", json=body).status_code == 201
    run_jobs()
    assert sent == []


def test_notice_text(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[Any] = []
    monkeypatch.setattr(mailer, "_send", messages.append)
    mailer.send_version_notice(
        email="a@example.org",
        first_name="Giorgi",
        passport_id="BTU-AI-000125",
        version_no=3,
        skills=["AI Ethics & Responsible Use", "AI Productivity Tools"],
        url="http://localhost:3000/me",
    )
    [msg] = messages
    assert msg["Subject"] == "Your AI Skills Passport was updated to version 3"
    text = msg.get_content()
    assert "AI Ethics & Responsible Use" in text and "AI Productivity Tools" in text
    assert "http://localhost:3000/me" in text and "BTU-AI-000125" in text
