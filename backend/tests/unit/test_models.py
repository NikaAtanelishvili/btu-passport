"""BE-02: the model metadata matches the schema in the plan."""

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models import Base

TABLES = {
    "students", "passports", "skill_categories", "skills", "award_submissions",
    "skill_awards", "passport_versions", "version_awards", "anchor_batches", "jobs",
    "users", "user_roles", "sessions", "login_codes", "audit_log", "events",
    "event_participants", "sheet_sync_runs", "sheet_records",
}  # fmt: skip


def _unique_sets(table: str) -> set[frozenset[str]]:
    t = Base.metadata.tables[table]
    sets = {frozenset(c.name for c in u.columns) for u in t.constraints
            if isinstance(u, UniqueConstraint)}  # fmt: skip
    sets |= {frozenset([c.name]) for c in t.columns if c.unique}
    return sets


def test_nineteen_tables() -> None:  # seventeen + two for the Sheet (SH-03)
    assert set(Base.metadata.tables) == TABLES


def test_one_passport_per_student_and_key_uniques() -> None:
    assert frozenset({"student_id"}) in _unique_sets("passports")  # FR-10
    assert frozenset({"student_id", "skill_id"}) in _unique_sets("skill_awards")
    assert frozenset({"passport_id", "version_no"}) in _unique_sets("passport_versions")
    assert frozenset({"event_id", "email"}) in _unique_sets("event_participants")  # FR-29
    assert frozenset({"event_id"}) in _unique_sets("award_submissions")  # FR-32
    assert frozenset({"idempotency_key"}) in _unique_sets("award_submissions")
    assert frozenset({"source_record_id"}) in _unique_sets("skill_awards")  # one award a record


def test_version_statuses_match_claude_md() -> None:
    table = Base.metadata.tables["passport_versions"]
    checks = {str(c.name): str(c.sqltext) for c in table.constraints
              if isinstance(c, CheckConstraint)}  # fmt: skip
    status = checks["ck_passport_versions_status"]
    for s in ("LEGACY", "PENDING", "RENDERED", "ANCHORING", "ANCHORED", "FAILED"):
        assert f"'{s}'" in status
