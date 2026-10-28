"""SH-04: the sync engine. Every outcome of the addendum's §5 and its invariants."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    AwardSubmission,
    Passport,
    PassportVersion,
    SheetRecord,
    SheetSyncRun,
    Skill,
    SkillAward,
    Student,
)
from app.services import issuance
from app.sheets import source as src
from app.sheets import sync
from app.sheets.source import COLUMNS, SKILLS, STUDENTS, VERIFIED, FileSource, Tab
from cli import export_sheets

pytestmark = pytest.mark.usefixtures("s3_bucket")

TODAY = date.today()


def header(tab: str) -> list[str]:
    required, optional = COLUMNS[tab]
    return [*required, *optional]


class TableSource:
    """The three tabs from Python lists: the seed export plus extra rows per tab."""

    label = "test"

    def __init__(self) -> None:
        self.base = FileSource(export_sheets.OUT_DIR).read()
        self.extra: dict[str, list[list[Any]]] = {STUDENTS: [], SKILLS: [], VERIFIED: []}
        self.edits: dict[tuple[str, str], dict[str, Any]] = {}
        self.fail: str | None = None

    def add(self, tab: str, *rows: list[Any]) -> "TableSource":
        self.extra[tab].extend(rows)
        return self

    def edit(self, tab: str, key: str, **values: Any) -> "TableSource":
        self.edits[(tab, key)] = values
        return self

    def read(self) -> dict[str, Tab]:
        if self.fail:
            raise src.SourceError(self.fail)
        tabs = {}
        for name, base in self.base.items():
            head = header(name)
            grid: list[list[Any]] = [head]
            for row in base.rows:
                values = dict(row.values)
                values.update(self.edits.get((name, str(values[head[0]])), {}))
                grid.append([values.get(h, "") for h in head])
            grid.extend(self.extra[name])
            tabs[name] = src.build_tab(name, name, grid)
        return tabs


def record(rid: str, student: str, skill: str, when: object = "2026-10-27",
           status: str = "CONFIRMED", through: str = "") -> list[Any]:  # fmt: skip
    return [rid, student, skill, when, status, through]


def new_student(sid: str = "BTU-T-0030", first: str = "Mariam") -> list[Any]:
    email = f"{sid.lower()}@example.org"
    return [sid, first, "Tsiklauri", email, "Computer Science", "BACHELOR", "ACTIVE"]


@pytest.fixture
def sheet(seeded: Session) -> TableSource:
    return TableSource()


def outcome(db: Session, tab: str, key: str) -> tuple[str, str | None]:
    db.expire_all()
    row = db.get(SheetRecord, (tab, key))
    assert row is not None, f"no record for {tab} {key}"
    return row.outcome, row.message


def count(db: Session, model: Any) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model)) or 0


def versions_of(db: Session, student_id: str) -> list[PassportVersion]:
    db.expire_all()
    return list(
        db.scalars(
            select(PassportVersion)
            .join(Passport, Passport.passport_id == PassportVersion.passport_id)
            .where(Passport.student_id == student_id)
            .order_by(PassportVersion.version_no)
        )
    )


def test_seed_files_change_nothing(seeded: Session, sheet: TableSource) -> None:
    """SH-02's check: the import files against the seeded database."""
    before = (count(seeded, SkillAward), count(seeded, PassportVersion), count(seeded, Student))
    for _ in range(2):
        result = sync.sync_now(sheet)
        assert result.status == "DONE", result.error
        assert result.counts[STUDENTS] == {"UNCHANGED": 18}
        assert result.counts[SKILLS] == {"UNCHANGED": 16}
        assert result.counts[VERIFIED] == {"DUPLICATE": 60}
    after = (count(seeded, SkillAward), count(seeded, PassportVersion), count(seeded, Student))
    assert after == before
    assert outcome(seeded, VERIFIED, "REC-0001") == (
        "DUPLICATE",
        "Already on the passport (seed import)",
    )


def test_new_confirmed_record_is_processed_once(seeded: Session, sheet: TableSource) -> None:
    sheet.add(
        VERIFIED, record("REC-0102", "BTU-T-0001", "SKL-003", through="AI Ethics Masterclass")
    )
    first = sync.sync_now(sheet)
    assert first.counts[VERIFIED] == {"DUPLICATE": 60, "PROCESSED": 1}
    award = seeded.scalars(
        select(SkillAward).where(SkillAward.source_record_id == "REC-0102")
    ).one()
    assert (award.student_id, award.skill_id, award.date_earned) == (
        "BTU-T-0001",
        "SKL-003",
        date(2026, 10, 27),
    )
    assert award.earned_through == "AI Ethics Masterclass"
    submission = seeded.get_one(AwardSubmission, award.submission_id)
    assert submission.kind == "SHEET"
    versions = versions_of(seeded, "BTU-T-0001")
    assert [v.status for v in versions][-1] == "PENDING"
    state, message = outcome(seeded, VERIFIED, "REC-0102")
    assert state == "PROCESSED"
    assert message == f"Added to BTU-AI-000125 v{versions[-1].version_no}"
    rec = seeded.get_one(SheetRecord, (VERIFIED, "REC-0102"))
    assert (rec.award_id, rec.version_id) == (award.award_id, versions[-1].version_id)

    # A repeated sync adds nothing.
    awards, n_versions = count(seeded, SkillAward), count(seeded, PassportVersion)
    second = sync.sync_now(sheet)
    assert second.counts[VERIFIED] == {"DUPLICATE": 60, "PROCESSED": 1}
    assert (count(seeded, SkillAward), count(seeded, PassportVersion)) == (awards, n_versions)
    assert seeded.scalar(select(func.count()).where(AuditLog.action == "sheet.award")) == 1


def test_pending_and_rejected_never_create_awards(seeded: Session, sheet: TableSource) -> None:
    sheet.add(
        VERIFIED,
        record("REC-0103", "BTU-T-0002", "SKL-005", status="PENDING"),
        record("REC-0104", "BTU-T-0003", "SKL-013", status="rejected"),
    )
    awards, versions = count(seeded, SkillAward), count(seeded, PassportVersion)
    for _ in range(2):
        sync.sync_now(sheet)
    assert (count(seeded, SkillAward), count(seeded, PassportVersion)) == (awards, versions)
    assert outcome(seeded, VERIFIED, "REC-0103")[0] == "WAITING"
    assert outcome(seeded, VERIFIED, "REC-0104")[0] == "IGNORED"

    # Re-checked: once confirmed, the waiting record is processed.
    sheet.extra[VERIFIED][0][4] = "CONFIRMED"
    result = sync.sync_now(sheet)
    assert result.counts[VERIFIED]["PROCESSED"] == 1
    assert outcome(seeded, VERIFIED, "REC-0103")[0] == "PROCESSED"


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (record("REC-0105", "BTU-T-9999", "SKL-001"), "Unknown student BTU-T-9999"),
        (record("REC-0105", "BTU-T-0001", "SKL-099"), "Unknown skill SKL-099"),
        (record("REC-0105", "BTU-T-0001", "SKL-003", "2030-01-15"), "Date earned is in the future"),
        (
            record("REC-0105", "BTU-T-0001", "SKL-003", "27/10/2026"),
            "Date earned must be YYYY-MM-DD or DD.MM.YYYY",
        ),
        (record("REC-0105", "", "SKL-003", ""), "student_id is missing; date_earned is missing"),
        (
            record("REC-0105", "BTU-T-0001", "SKL-003", status="DONE"),
            "Status must be CONFIRMED, PENDING or REJECTED",
        ),
        (
            record("REC-0105", "BTU-T-0001", "SKL-003", through="x" * 121),
            "earned_through is longer than 120 characters",
        ),
    ],
)
def test_invalid_records_change_nothing(
    seeded: Session, sheet: TableSource, row: list[Any], message: str
) -> None:
    sheet.add(VERIFIED, row)
    awards, versions = count(seeded, SkillAward), count(seeded, PassportVersion)
    result = sync.sync_now(sheet)
    assert result.status == "DONE"
    assert outcome(seeded, VERIFIED, "REC-0105") == ("ERROR", message)
    assert (count(seeded, SkillAward), count(seeded, PassportVersion)) == (awards, versions)


def test_archived_skill_and_missing_record_id(seeded: Session, sheet: TableSource) -> None:
    seeded.get_one(Skill, "SKL-005").archived_at = func.now()
    seeded.commit()
    sheet.add(VERIFIED, record("REC-0105", "BTU-T-0001", "SKL-005"))
    sheet.add(VERIFIED, record("", "BTU-T-0001", "SKL-004"))
    sync.sync_now(sheet)
    assert outcome(seeded, VERIFIED, "REC-0105") == ("ERROR", "Skill SKL-005 is archived")
    assert outcome(seeded, VERIFIED, "@63") == ("ERROR", "record_id is missing")


def test_dates_from_sheets_and_excel(seeded: Session, sheet: TableSource) -> None:
    sheet.add(
        VERIFIED,
        record("REC-0201", "BTU-T-0001", "SKL-003", 46322),  # a Sheets serial date: 2026-10-27
        record("REC-0202", "BTU-T-0001", "SKL-004", "26.10.2026"),
        record("REC-0203", "BTU-T-0002", "SKL-004", date(2026, 10, 25)),
    )
    sync.sync_now(sheet)
    earned = dict(
        seeded.execute(
            select(SkillAward.source_record_id, SkillAward.date_earned).where(
                SkillAward.source_record_id.in_(["REC-0201", "REC-0202", "REC-0203"])
            )
        ).all()
    )
    assert earned == {
        "REC-0201": date(2026, 10, 27),
        "REC-0202": date(2026, 10, 26),
        "REC-0203": date(2026, 10, 25),
    }


def test_one_version_per_student_per_sync(seeded: Session, sheet: TableSource) -> None:
    before = len(versions_of(seeded, "BTU-T-0001"))
    sheet.add(
        VERIFIED,
        record("REC-0301", "BTU-T-0001", "SKL-003"),
        record("REC-0302", "BTU-T-0001", "SKL-004"),
    )
    sync.sync_now(sheet)
    versions = versions_of(seeded, "BTU-T-0001")
    assert len(versions) == before + 1
    first, second = (seeded.get_one(SheetRecord, (VERIFIED, k)) for k in ("REC-0301", "REC-0302"))
    assert first.version_id == second.version_id == versions[-1].version_id


def test_one_students_error_does_not_block_another(
    seeded: Session, sheet: TableSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = issuance.create_versions

    def flaky(db: Session, student_ids: list[str]) -> Any:
        if "BTU-T-0001" in student_ids:
            raise RuntimeError("disk full")
        return real(db, student_ids)

    monkeypatch.setattr(issuance, "create_versions", flaky)
    sheet.add(
        VERIFIED,
        record("REC-0401", "BTU-T-0001", "SKL-003"),
        record("REC-0402", "BTU-T-9999", "SKL-003"),
        record("REC-0403", "BTU-T-0002", "SKL-004"),
    )
    result = sync.sync_now(sheet)
    assert result.status == "DONE"
    assert outcome(seeded, VERIFIED, "REC-0401") == (
        "ERROR",
        "Could not be processed (RuntimeError); retried on the next sync",
    )
    assert outcome(seeded, VERIFIED, "REC-0402")[0] == "ERROR"
    assert outcome(seeded, VERIFIED, "REC-0403")[0] == "PROCESSED"
    # The failed student's transaction left nothing behind.
    assert (
        seeded.scalar(select(SkillAward).where(SkillAward.source_record_id == "REC-0401")) is None
    )

    monkeypatch.setattr(issuance, "create_versions", real)
    sync.sync_now(sheet)
    assert outcome(seeded, VERIFIED, "REC-0401")[0] == "PROCESSED"


def test_skill_already_held_is_a_duplicate(seeded: Session, sheet: TableSource) -> None:
    """D4: one record space with the admin panel; also a second record for the same skill."""
    sheet.add(
        VERIFIED,
        record("REC-0501", "BTU-T-0001", "SKL-001"),  # held since the seed (REC-0001)
        record("REC-0502", "BTU-T-0001", "SKL-003"),
        record("REC-0503", "BTU-T-0001", "SKL-003"),
    )
    sync.sync_now(sheet)
    assert outcome(seeded, VERIFIED, "REC-0501") == (
        "DUPLICATE",
        "BTU-T-0001 already holds SKL-001 (seed import REC-0001)",
    )
    assert outcome(seeded, VERIFIED, "REC-0502")[0] == "PROCESSED"
    assert outcome(seeded, VERIFIED, "REC-0503") == (
        "DUPLICATE",
        "BTU-T-0001 already holds SKL-003 (record REC-0502)",
    )


def test_exact_repeat_of_a_record_is_counted_once(seeded: Session, sheet: TableSource) -> None:
    row = record("REC-0102", "BTU-T-0001", "SKL-003")
    sheet.add(VERIFIED, row, list(row))
    versions = len(versions_of(seeded, "BTU-T-0001"))
    sync.sync_now(sheet)
    assert outcome(seeded, VERIFIED, "REC-0102")[0] == "PROCESSED"
    assert outcome(seeded, VERIFIED, "REC-0102@63") == (
        "DUPLICATE",
        "Same Record ID as row 62; counted once",
    )
    assert len(versions_of(seeded, "BTU-T-0001")) == versions + 1


def test_processed_row_edited_later_is_flagged_not_applied(
    seeded: Session, sheet: TableSource
) -> None:
    sheet.add(VERIFIED, record("REC-0601", "BTU-T-0001", "SKL-003"))
    sync.sync_now(sheet)
    award = seeded.scalars(
        select(SkillAward).where(SkillAward.source_record_id == "REC-0601")
    ).one()
    versions = count(seeded, PassportVersion)

    sheet.extra[VERIFIED][0][3] = "2026-10-20"
    result = sync.sync_now(sheet)
    assert result.counts[VERIFIED]["CHANGED_AFTER_PROCESSING"] == 1
    assert outcome(seeded, VERIFIED, "REC-0601") == (
        "CHANGED_AFTER_PROCESSING",
        "Edited after processing (date_earned 2026-10-27 → 2026-10-20); not applied",
    )
    seeded.refresh(award)
    assert award.date_earned == date(2026, 10, 27)

    sheet.extra[VERIFIED][0][4] = "REJECTED"
    sync.sync_now(sheet)
    state, message = outcome(seeded, VERIFIED, "REC-0601")
    assert state == "REVOKED_IN_SHEET"
    assert message is not None and "stays on the passport" in message
    assert count(seeded, PassportVersion) == versions

    # Undoing the edits makes it a plain processed record again.
    sheet.extra[VERIFIED][0][3:5] = ["2026-10-27", "CONFIRMED"]
    sync.sync_now(sheet)
    assert outcome(seeded, VERIFIED, "REC-0601")[0] == "PROCESSED"

    # A seed record edited in the Sheet is flagged too.
    sheet.edit(VERIFIED, "REC-0001", skill_code="SKL-002")
    sync.sync_now(sheet)
    assert outcome(seeded, VERIFIED, "REC-0001") == (
        "CHANGED_AFTER_PROCESSING",
        "Edited after processing (skill_code SKL-001 → SKL-002); not applied",
    )


def test_update_keeps_passport_id_first_issue_and_earlier_skills(
    seeded: Session,
    sheet: TableSource,
    fake_signer: Any,
    run_jobs: Callable[[], int],
) -> None:
    from cli.__main__ import issue_pending

    issue_pending()
    run_jobs()
    seeded.expire_all()
    passport = seeded.scalars(select(Passport).where(Passport.student_id == "BTU-T-0001")).one()
    before = versions_of(seeded, "BTU-T-0001")[-1]
    assert before.status == "ANCHORED" and before.content_json is not None

    sheet.add(VERIFIED, record("REC-0701", "BTU-T-0001", "SKL-003"))
    sync.sync_now(sheet)
    run_jobs()
    after = versions_of(seeded, "BTU-T-0001")[-1]
    assert after.status == "ANCHORED" and after.content_json is not None
    assert after.version_no == before.version_no + 1
    old, new = before.content_json, after.content_json
    assert new["passport_id"] == old["passport_id"] == passport.passport_id
    assert new["first_issued_on"] == old["first_issued_on"]
    assert new["holder"] == old["holder"]
    assert all(s in new["skills"] for s in old["skills"])  # earlier skills exactly as issued
    assert {s["skill_id"] for s in new["skills"]} == {s["skill_id"] for s in old["skills"]} | {
        "SKL-003"
    }


# --- Students tab --------------------------------------------------------------------------


def test_new_student_gets_a_passport_and_v1(seeded: Session, sheet: TableSource) -> None:
    sheet.add(STUDENTS, new_student("BTU-T-0030"), new_student("BTU-T-0031", "Nino"))
    sheet.add(VERIFIED, record("REC-0101", "BTU-T-0030", "SKL-001", through="AI Literacy Workshop"))
    result = sync.sync_now(sheet)
    assert result.counts[STUDENTS] == {"UNCHANGED": 18, "CREATED": 2}
    passport = seeded.scalars(select(Passport).where(Passport.student_id == "BTU-T-0030")).one()
    assert passport.passport_id == "BTU-AI-000143"  # the next number after the seed's
    state, message = outcome(seeded, STUDENTS, "BTU-T-0030")
    assert (state, message) == ("CREATED", "Passport BTU-AI-000143")
    # With a record in the same sync: one V1 holding it. Without: an empty V1.
    with_record, without = versions_of(seeded, "BTU-T-0030"), versions_of(seeded, "BTU-T-0031")
    assert [v.version_no for v in with_record] == [1]
    assert [v.version_no for v in without] == [1]
    assert outcome(seeded, VERIFIED, "REC-0101")[1] == "Added to BTU-AI-000143 v1"
    assert seeded.scalar(select(func.count()).where(AuditLog.action == "sheet.student.create")) == 2

    again = sync.sync_now(sheet)
    assert again.counts[STUDENTS] == {"UNCHANGED": 20}
    assert len(versions_of(seeded, "BTU-T-0030")) == 1


def test_student_updates_and_conflicts(seeded: Session, sheet: TableSource) -> None:
    sheet.edit(STUDENTS, "BTU-T-0002", program="Data Science", status="GRADUATE")
    sheet.edit(STUDENTS, "BTU-T-0003", first_name="Nina")  # BTU-AI-000133 was issued
    sheet.edit(STUDENTS, "BTU-T-0004", email="saba@example.org", program="Marketing")
    sheet.edit(STUDENTS, "BTU-T-0005", education_level="PHD")
    result = sync.sync_now(sheet)
    assert result.counts[STUDENTS] == {
        "UNCHANGED": 14,
        "UPDATED": 1,
        "CONFLICT": 2,
        "ERROR": 1,
    }
    seeded.expire_all()
    two = seeded.get_one(Student, "BTU-T-0002")
    assert (two.program, two.status) == ("Data Science", "GRADUATE")
    assert outcome(seeded, STUDENTS, "BTU-T-0002") == (
        "UPDATED",
        "program, status updated",
    )
    assert seeded.get_one(Student, "BTU-T-0003").first_name == "Nino"
    assert outcome(seeded, STUDENTS, "BTU-T-0003") == (
        "CONFLICT",
        "First name differs from the issued passport (Nino); not applied",
    )
    four = seeded.get_one(Student, "BTU-T-0004")
    assert (four.email, four.program) == ("btu-t-0004@example.org", "Marketing")
    assert outcome(seeded, STUDENTS, "BTU-T-0004") == (
        "CONFLICT",
        "program updated; Email differs from the system (btu-t-0004@example.org); not applied",
    )
    assert outcome(seeded, STUDENTS, "BTU-T-0005") == (
        "ERROR",
        "education_level: Choose Bachelor's, Master's or Doctoral.",
    )


def test_student_row_errors(seeded: Session, sheet: TableSource) -> None:
    sheet.add(
        STUDENTS,
        ["BTU-0030", "A", "B", "a@example.org", "IT", "BACHELOR", "ACTIVE"],
        [*new_student("BTU-T-0031")[:3], "btu-t-0001@example.org", "IT", "BACHELOR", "ACTIVE"],
        new_student("BTU-T-0032"),
        new_student("BTU-T-0032", "Other"),
    )
    sync.sync_now(sheet)
    assert outcome(seeded, STUDENTS, "BTU-0030") == (
        "ERROR",
        "student_id: Use the BTU format, e.g. BTU-T-0001.",
    )
    assert outcome(seeded, STUDENTS, "BTU-T-0031") == (
        "ERROR",
        "email: Already used by BTU-T-0001.",
    )
    assert outcome(seeded, STUDENTS, "BTU-T-0032")[0] == "CREATED"
    assert outcome(seeded, STUDENTS, "BTU-T-0032@23") == (
        "ERROR",
        "Same Student ID as row 22; not applied",
    )
    assert seeded.get(Student, "BTU-T-0031") is None


# --- Skills Catalog tab --------------------------------------------------------------------


def test_skills_catalog(seeded: Session, sheet: TableSource) -> None:
    sheet.add(
        SKILLS,
        ["SKL-017", "AI Agents", "AI Advanced Skill", "Building agents.", "BDG-AI-003"],
        ["SKL-018", "AI Video", "AI Skill", "Video.", "BDG-AI-003"],
        ["SKL-019", "AI Literacy", "AI Skill", "Same name as SKL-001.", ""],
        ["SKL-020", "AI Music", "No such category", "Music.", ""],
    )
    sheet.edit(SKILLS, "SKL-002", description="Writing prompts.")
    sheet.edit(SKILLS, "SKL-003", category="AI Applied Skill", badge_code="")
    result = sync.sync_now(sheet)
    assert result.counts[SKILLS] == {"UNCHANGED": 14, "CREATED": 1, "UPDATED": 1, "ERROR": 4}
    seeded.expire_all()
    agents = seeded.get_one(Skill, "SKL-017")
    assert (agents.name, agents.description) == ("AI Agents", "Building agents.")
    assert seeded.get_one(Skill, "SKL-002").description == "Writing prompts."
    assert outcome(seeded, SKILLS, "SKL-018") == (
        "ERROR",
        "badge_code BDG-AI-003 doesn't match the category AI Skill (BDG-AI-001)",
    )
    assert outcome(seeded, SKILLS, "SKL-019") == ("ERROR", "name: Already used by SKL-001")
    assert outcome(seeded, SKILLS, "SKL-020") == ("ERROR", "Unknown category No such category")
    assert outcome(seeded, SKILLS, "SKL-003") == (
        "ERROR",
        "Category differs from the system (AI Skill); change it in the admin panel",
    )
    # The new skill can be awarded in the same sync.
    sheet.add(VERIFIED, record("REC-0801", "BTU-T-0001", "SKL-017"))
    sync.sync_now(sheet)
    assert outcome(seeded, VERIFIED, "REC-0801")[0] == "PROCESSED"


# --- Whole-run failures --------------------------------------------------------------------


def test_read_failure_fails_the_run_and_changes_nothing(
    seeded: Session, sheet: TableSource
) -> None:
    sheet.fail = "Google Sheets unreachable (ConnectError)"
    result = sync.sync_now(sheet)
    assert result.status == "FAILED"
    assert result.error == "Google Sheets unreachable (ConnectError)"
    assert count(seeded, SheetRecord) == 0
    run = seeded.get_one(SheetSyncRun, result.run_id)
    assert (run.status, run.error) == ("FAILED", "Google Sheets unreachable (ConnectError)")
    assert run.finished_at is not None


def test_missing_column_fails_that_tab_only(
    seeded: Session, sheet: TableSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    tabs = sheet.read()
    students = tabs[STUDENTS]
    columns = {k: v for k, v in students.columns.items() if k != "email"}
    tabs[STUDENTS] = Tab(STUDENTS, STUDENTS, 1, columns, students.rows)
    monkeypatch.setattr(sheet, "read", lambda: tabs)
    sheet.add(VERIFIED, record("REC-0901", "BTU-T-0001", "SKL-003"))
    tabs[VERIFIED] = TableSource.read(sheet)[VERIFIED]
    result = sync.sync_now(sheet)
    assert result.status == "FAILED"
    assert result.error == "Students: missing column email"
    assert STUDENTS not in result.counts
    assert outcome(seeded, VERIFIED, "REC-0901")[0] == "PROCESSED"


def test_unchanged_runs_write_no_audit_rows(seeded: Session, sheet: TableSource) -> None:
    sync.sync_now(sheet)
    sync.sync_now(sheet)
    assert seeded.scalar(select(func.count()).where(AuditLog.action == "sheet.sync")) == 0
    sheet.add(VERIFIED, record("REC-1001", "BTU-T-0001", "SKL-003"))
    sync.sync_now(sheet)
    assert seeded.scalar(select(func.count()).where(AuditLog.action == "sheet.sync")) == 1


def test_today_is_not_the_future(seeded: Session, sheet: TableSource) -> None:
    sheet.add(VERIFIED, record("REC-1101", "BTU-T-0001", "SKL-003", issuance.today().isoformat()))
    sheet.add(
        VERIFIED,
        record("REC-1102", "BTU-T-0001", "SKL-004", (issuance.today() + timedelta(1)).isoformat()),
    )
    sync.sync_now(sheet)
    assert outcome(seeded, VERIFIED, "REC-1101")[0] == "PROCESSED"
    assert outcome(seeded, VERIFIED, "REC-1102")[0] == "ERROR"
