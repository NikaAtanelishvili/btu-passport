"""Fixtures for tests against Anvil with the registry deployed (make test-chain)."""

from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services import chain
from signer.main import create_app


@pytest.fixture
def real_signer(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Route anchoring.anchor_root's HTTP call to the signer app instead of SIGNER_URL."""
    with TestClient(create_app()) as signer_client:

        def post(url: str, **kwargs: object) -> object:
            assert url.endswith("/anchor")
            return signer_client.post("/anchor", **kwargs)

        monkeypatch.setattr(httpx, "post", post)
        yield


@pytest.fixture(autouse=True)
def _fresh_chain_cache() -> Iterator[None]:
    chain.clear_cache()
    yield
    chain.clear_cache()
