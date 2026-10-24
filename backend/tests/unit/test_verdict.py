"""BE-30: the verdict order. Issuer first (an untrusted registry proves nothing), then the
document, then revocation, then whether a newer version exists."""

import pytest

from app.services.verification import decide


def _decide(**kw: object) -> str:
    args: dict[str, object] = {
        "issuer_ok": True,
        "document_ok": True,
        "revoked": False,
        "version_no": 2,
        "latest_version_no": 2,
    }
    args.update(kw)
    return decide(**args)  # type: ignore[arg-type]


def test_latest_version_is_valid() -> None:
    assert _decide() == "VALID"


def test_older_version_is_superseded() -> None:
    assert _decide(version_no=1) == "SUPERSEDED"


@pytest.mark.parametrize("document_ok", [True, False])
def test_a_foreign_issuer_wins_over_everything(document_ok: bool) -> None:
    assert _decide(issuer_ok=False, document_ok=document_ok, revoked=True) == "NOT_ISSUED_BY_BTU"


def test_a_root_missing_on_chain_is_not_found_even_for_an_anchored_row() -> None:
    assert _decide(document_ok=False, revoked=True) == "NOT_FOUND"


def test_revoked_wins_over_superseded() -> None:
    assert _decide(revoked=True, version_no=1) == "REVOKED"
