"""M10: cli demo-reset refuses without --yes and touches nothing then."""

import pytest

from cli import demo_reset


def test_refuses_without_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not run")

    monkeypatch.setattr(demo_reset, "create_engine", boom)
    with pytest.raises(SystemExit, match="--yes"):
        demo_reset.main(yes=False)
