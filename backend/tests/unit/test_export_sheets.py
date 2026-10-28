"""SH-02: the import files are the seed in the addendum's §4 format, and read back cleanly."""

from pathlib import Path

from app.sheets.source import CSV_FILES, SKILLS, STUDENTS, VERIFIED, FileSource
from cli import export_sheets


def test_committed_files_match_a_fresh_export(tmp_path: Path) -> None:
    counts = export_sheets.write_csvs(tmp_path)
    assert counts == {STUDENTS: 18, SKILLS: 16, VERIFIED: 60}
    for name in CSV_FILES.values():
        committed = (export_sheets.OUT_DIR / name).read_bytes()
        assert committed == (tmp_path / name).read_bytes(), f"run `make export-sheets` ({name})"


def test_files_read_back_through_file_source(tmp_path: Path) -> None:
    export_sheets.write_xlsx(tmp_path / "seed.xlsx")
    for tabs in (
        FileSource(export_sheets.OUT_DIR).read(),
        FileSource(tmp_path / "seed.xlsx").read(),
    ):
        assert {name: len(tab.rows) for name, tab in tabs.items()} == {
            STUDENTS: 18,
            SKILLS: 16,
            VERIFIED: 60,
        }
        assert all(tab.missing() == [] for tab in tabs.values())
        verified = tabs[VERIFIED].rows
        assert {r.values["status"] for r in verified} == {"CONFIRMED"}
        assert verified[0].number == 2
        assert verified[0].values["record_id"] == "REC-0001"
        assert tabs[STUDENTS].rows[0].values["education_level"] == "BACHELOR"
