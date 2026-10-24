"""BE-20: verification codes."""

import pytest

from app.services import codes


def test_new_code_is_ten_crockford_characters() -> None:
    for _ in range(200):
        code = codes.new_verification_code()
        assert len(code) == 10
        assert set(code) <= set(codes.ALPHABET)
        assert not set(code) & set("ILOU")


def test_codes_differ() -> None:
    assert len({codes.new_verification_code() for _ in range(1000)}) == 1000


def test_format_code() -> None:
    assert codes.format_code("K7QM3XWP9D") == "K7QM-3XWP-9D"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("K7QM3XWP9D", "K7QM3XWP9D"),
        ("k7qm-3xwp-9d", "K7QM3XWP9D"),
        (" K7QM 3XWP 9D ", "K7QM3XWP9D"),
        ("O0IL", "0011"),  # look-alikes map to digits
        ("o-i-l", "011"),
    ],
)
def test_normalize_code(text: str, expected: str) -> None:
    assert codes.normalize_code(text) == expected


@pytest.mark.parametrize("text", ["K7QM3XWP9U", "K7QM_3XWP", "K7QM3XWP9!", "ÄBC"])
def test_normalize_rejects_characters_outside_the_alphabet(text: str) -> None:
    with pytest.raises(ValueError):
        codes.normalize_code(text)
