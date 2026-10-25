"""BE-04: parsing and normalising the hackathon CSV (no database)."""

from datetime import UTC, date, datetime

from cli import seed


def test_parse_reads_exactly_the_60_data_rows() -> None:
    rows = seed.parse_csv(seed.SEED_CSV)
    assert len(rows) == 60
    assert rows[0].record_id == "REC-0001"
    assert {r.record_id for r in rows} == {f"REC-{i:04d}" for i in range(1, 61)}


def test_rows_are_normalised() -> None:
    rows = {r.record_id: r for r in seed.parse_csv(seed.SEED_CSV)}
    r = rows["REC-0049"]
    assert (r.student_id, r.passport_id, r.education_level) == (
        "BTU-T-0021",
        "BTU-AI-000139",
        "MASTER",
    )
    assert r.status == "ACTIVE" and r.email == "btu-t-0021@example.org"
    assert r.date_earned == date(2026, 10, 18) and r.first_issued == date(2026, 10, 17)
    assert r.synced_at is None
    synced = rows["REC-0002"]
    assert synced.education_level == "BACHELOR"
    assert synced.synced_at == datetime(2026, 10, 17, 10, 0, tzinfo=UTC)
    assert {r.status for r in rows.values()} == {"ACTIVE", "GRADUATE"}


def test_every_category_has_a_stamp_file() -> None:
    codes = {r.badge_code for r in seed.parse_csv(seed.SEED_CSV)}
    assert codes == {"BDG-AI-001", "BDG-AI-002", "BDG-AI-003"}
    assert set(seed.STAMP_FILES) == codes
    for file in seed.STAMP_FILES.values():
        assert (seed.STAMPS_DIR / file).is_file()
