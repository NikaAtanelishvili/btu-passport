"""The passport design's pagination and wording (docs/design/passport/): 10 grid slots a page,
empty ones kept; "Earned through" from the event or the direct award's reason."""

from typing import Any

from app.pdf.render import _dotted_date, _earned_through, grid_pages


def _skills(n: int) -> list[dict[str, Any]]:
    return [{"skill_id": f"SKL-{i:03d}"} for i in range(n)]


def test_grid_pages_have_ten_slots_and_keep_empty_ones() -> None:
    assert grid_pages([]) == [[None] * 10]
    [two] = grid_pages(_skills(2))
    assert len(two) == 10 and two[2:] == [None] * 8
    [ten] = grid_pages(_skills(10))
    assert None not in ten
    first, second = grid_pages(_skills(14))
    assert None not in first and len(second) == 10 and second[4:] == [None] * 6


def test_earned_through() -> None:
    assert (
        _earned_through({"source": {"type": "event", "event_name": "Prompt Lab"}}) == "Prompt Lab"
    )
    assert (
        _earned_through({"source": {"type": "direct", "reason": "NLP elective"}}) == "NLP elective"
    )
    assert _earned_through({"source": {"type": "direct"}}) == "Direct award"
    assert _earned_through({"source": {"type": "seed"}}) == "Direct award"


def test_dotted_date() -> None:
    assert _dotted_date("2026-03-07") == "07.03.2026"
    assert _dotted_date("2026-10-22T15:40:12Z") == "22.10.2026"


def test_earned_through_for_sheet_records() -> None:
    """SH-04: the Sheet's earned_through column, else DEFAULT(PDF) "Verified by BTU"."""
    from app.pdf.render import _earned_through

    sheet = {"type": "sheet", "earned_through": "AI Ethics Masterclass"}
    assert _earned_through({"source": sheet}) == "AI Ethics Masterclass"
    assert _earned_through({"source": {"type": "sheet"}}) == "Verified by BTU"
