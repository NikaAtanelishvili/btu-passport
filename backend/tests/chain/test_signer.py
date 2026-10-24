"""BC-07: the signer against Anvil with the registry deployed (make test-chain)."""

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.anchoring import signature_headers
from signer.config import SignerSettings, get_signer_settings
from signer.main import StartupError, create_app, load_signer

pytestmark = pytest.mark.chain

# DEV ONLY: Anvil account 1's published test key (not the issuer).
ANVIL_KEY_1 = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"


def _sign(body: bytes, *, secret: str | None = None, ts: int | None = None) -> dict[str, str]:
    """Signed exactly as the worker signs (app/services/anchoring.py)."""
    secret = secret or get_signer_settings().signer_hmac_secret.get_secret_value()
    return signature_headers(body, secret, now=ts)


def _anchor(client: TestClient, root: str, **sign: Any) -> Any:
    body = json.dumps({"root": root, "leaf_count": 3}).encode()
    return client.post(
        "/anchor", content=body, headers={"Content-Type": "application/json", **_sign(body, **sign)}
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def _random_root() -> str:
    return "0x" + os.urandom(32).hex()


def test_valid_call_anchors_and_returns_a_receipt(client: TestClient) -> None:
    root = _random_root()
    r = _anchor(client, root)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["already_anchored"] is False
    assert body["tx_hash"].startswith("0x") and len(body["tx_hash"]) == 66
    assert body["block_number"] > 0 and body["anchored_at"].endswith("Z")

    signer = load_signer(get_signer_settings())
    assert signer.contract.functions.anchoredAt(bytes.fromhex(root[2:])).call() > 0


def test_same_root_again_returns_the_first_transaction(client: TestClient) -> None:
    root = _random_root()
    first = _anchor(client, root).json()
    again = _anchor(client, root)
    assert again.status_code == 200
    assert again.json() == {**first, "already_anchored": True}


def test_wrong_hmac_is_rejected(client: TestClient) -> None:
    r = _anchor(client, _random_root(), secret="not-the-secret")
    assert (r.status_code, r.json()["error"]) == (401, "bad_signature")


def test_stale_timestamp_is_rejected(client: TestClient) -> None:
    r = _anchor(client, _random_root(), ts=int(time.time()) - 61)
    assert (r.status_code, r.json()["error"]) == (401, "bad_signature")


def test_zero_or_malformed_root_is_rejected(client: TestClient) -> None:
    assert _anchor(client, "0x" + "00" * 32).status_code == 422
    assert _anchor(client, "0x1234").status_code == 422


def test_healthz_has_no_secrets(client: TestClient) -> None:
    body = client.get("/healthz").json()
    assert set(body) == {"ok", "address", "chain_id", "balance_wei"}
    assert body["address"] == get_signer_settings().issuer_address


def test_key_not_matching_issuer_address_refuses_to_start(tmp_path: Path) -> None:
    key_file = tmp_path / "issuer_key"
    key_file.write_text(ANVIL_KEY_1)
    settings = SignerSettings(issuer_private_key_file=key_file)
    with pytest.raises(StartupError) as exc:
        load_signer(settings)
    message = str(exc.value)
    assert "does not match ISSUER_ADDRESS" in message
    assert ANVIL_KEY_1[2:] not in message  # never echo the key
