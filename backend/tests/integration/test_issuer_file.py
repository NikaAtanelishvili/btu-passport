"""BE-31: BTU's issuer file (FR-21), public and served from configuration."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

ClientAs = Callable[[str | None], TestClient]


def test_issuer_file_is_public_and_comes_from_config(client_as: ClientAs) -> None:
    s = get_settings()
    r = client_as(None).get("/.well-known/ai-passport-issuer.json")
    assert r.status_code == 200
    assert r.json() == {
        "issuer_name": "Business and Technology University",
        "chain_id": s.chain_id,
        "contract_address": s.contract_address,
        "issuer_address": s.issuer_address,
    }


def test_issuer_file_follows_the_issuer_address_setting(
    client_as: ClientAs, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "issuer_address", "0x" + "22" * 20)
    r = client_as(None).get("/.well-known/ai-passport-issuer.json")
    assert r.json()["issuer_address"] == "0x" + "22" * 20
