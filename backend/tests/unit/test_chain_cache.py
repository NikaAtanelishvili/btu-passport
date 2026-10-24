"""BE-30: chain reads are cached in-process for 60 s (anchoring times forever once set)."""

from collections.abc import Iterator
from typing import Any

import pytest
import time_machine

from app.services import chain


class _Call:
    def __init__(self, counts: dict[str, int], name: str, value: Any) -> None:
        self.counts, self.name, self.value = counts, name, value

    def call(self) -> Any:
        self.counts[self.name] = self.counts.get(self.name, 0) + 1
        return self.value


class _Functions:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.anchored = 0

    def anchoredAt(self, root: bytes) -> _Call:
        return _Call(self.counts, "anchoredAt", self.anchored)

    def owner(self) -> _Call:
        return _Call(self.counts, "owner", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")

    def revoked(self, leaf: bytes) -> _Call:
        return _Call(self.counts, "revoked", False)


class _Contract:
    def __init__(self) -> None:
        self.functions = _Functions()


@pytest.fixture
def contract(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Functions]:
    fake = _Contract()
    monkeypatch.setattr(chain, "_contract", lambda: fake)
    chain.clear_cache()
    yield fake.functions
    chain.clear_cache()


ROOT = "0x" + "ab" * 32


def test_owner_is_cached_for_60_seconds(contract: _Functions) -> None:
    with time_machine.travel(0, tick=False) as clock:
        assert chain.owner() == "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        chain.owner()
        assert contract.counts["owner"] == 1
        clock.shift(61)
        chain.owner()
        assert contract.counts["owner"] == 2


def test_an_unanchored_root_is_rechecked_after_60_seconds_and_an_anchored_one_never(
    contract: _Functions,
) -> None:
    with time_machine.travel(0, tick=False) as clock:
        assert chain.anchored_at(ROOT) == 0
        contract.anchored = 1_700_000_000
        assert chain.anchored_at(ROOT) == 0  # still cached
        clock.shift(61)
        assert chain.anchored_at(ROOT) == 1_700_000_000
        clock.shift(3600)
        assert chain.anchored_at(ROOT) == 1_700_000_000
        assert contract.counts["anchoredAt"] == 2
