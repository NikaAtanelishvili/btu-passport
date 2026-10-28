"""M10: the signer takes its key from ISSUER_PRIVATE_KEY (content, for hosts without secret
files such as Railway) or ISSUER_PRIVATE_KEY_FILE. The address check runs before any RPC
call, so these need no chain."""

from pathlib import Path

import pytest

from signer.config import SignerSettings
from signer.main import StartupError, load_signer

# DEV ONLY: Anvil's published test keys #0 and #1.
ANVIL_KEY_0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ANVIL_KEY_1 = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
ANVIL_ADDR_0 = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNER_HMAC_SECRET", "test")
    monkeypatch.delenv("ISSUER_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("ISSUER_ADDRESS", ANVIL_ADDR_0)


def _settings(**kwargs: object) -> SignerSettings:
    return SignerSettings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def test_key_content_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ISSUER_PRIVATE_KEY", f"  {ANVIL_KEY_0}\n")
    settings = _settings(issuer_private_key_file=tmp_path / "missing")
    assert settings.private_key() == ANVIL_KEY_0


def test_key_file_when_no_content(tmp_path: Path) -> None:
    key_file = tmp_path / "issuer_key"
    key_file.write_text(ANVIL_KEY_0 + "\n")
    assert _settings(issuer_private_key_file=key_file).private_key() == ANVIL_KEY_0


def test_env_content_checked_like_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUER_PRIVATE_KEY", ANVIL_KEY_1)
    with pytest.raises(StartupError) as exc:
        load_signer(_settings())
    assert "does not match ISSUER_ADDRESS" in str(exc.value)
    assert ANVIL_KEY_1[2:] not in str(exc.value)


def test_unreadable_file_names_both_options(tmp_path: Path) -> None:
    with pytest.raises(StartupError, match="ISSUER_PRIVATE_KEY"):
        load_signer(_settings(issuer_private_key_file=tmp_path / "missing"))


def test_invalid_key_content_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUER_PRIVATE_KEY", "0xnot-a-key-secret-value")
    with pytest.raises(StartupError) as exc:
        load_signer(_settings())
    assert "secret-value" not in str(exc.value)


def test_key_content_never_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUER_PRIVATE_KEY", ANVIL_KEY_0)
    assert ANVIL_KEY_0[2:] not in repr(_settings())
