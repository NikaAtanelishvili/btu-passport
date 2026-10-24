"""Signer settings (BC-07). Separate from app/config.py: the signer imports nothing from app/,
and only this process ever sees ISSUER_PRIVATE_KEY_FILE."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class SignerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,  # never print .env values (the HMAC secret) on a bad config
    )

    env: Literal["dev", "test", "demo"] = "dev"
    chain_id: int = 31337
    rpc_url: str = "http://localhost:8545"
    contract_address: str = ""
    issuer_address: str = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"  # DEV ONLY: Anvil #0
    signer_hmac_secret: SecretStr
    # Relative paths are taken from the repository root.
    issuer_private_key_file: Path = Path("secrets/issuer_key")
    confirmations: int = 1
    receipt_timeout_seconds: int = 120

    def key_path(self) -> Path:
        path = self.issuer_private_key_file
        return path if path.is_absolute() else REPO_ROOT / path

    def abi_path(self) -> Path:
        return REPO_ROOT / "shared" / "PassportRegistry.abi.json"

    def deployment_path(self) -> Path:
        return REPO_ROOT / "contracts" / "deployments" / f"{self.chain_id}.json"


@lru_cache
def get_signer_settings() -> SignerSettings:
    return SignerSettings()
