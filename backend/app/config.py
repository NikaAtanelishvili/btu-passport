"""Settings for the API, worker and CLI (Overview §4).

The signer has its own settings class (signer/config.py); the issuer key file and the
deployer key are deliberately absent here.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: Literal["dev", "test", "demo"] = "dev"
    timezone: str = "Asia/Tbilisi"
    public_base_url: str = "http://localhost:3000"

    database_url: str = "postgresql+psycopg://passport:passport@localhost:5432/passport"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minio"
    s3_secret_key: SecretStr
    s3_bucket: str = "passports"

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = "passport@btu.test"

    login_code_ttl_minutes: int = 10
    login_code_max_attempts: int = 5
    login_rate_per_email_hour: int = 5
    login_rate_per_ip_hour: int = 20
    dev_log_login_codes: bool = True

    allowed_email_domains: Annotated[list[str], NoDecode] = [
        "btu.edu.ge",
        "btu.test",
        "example.org",
    ]
    bootstrap_super_admin_email: str = "superadmin@btu.test"

    session_cookie_name: str = "session"
    session_secure: bool = False
    session_absolute_hours: int = 8
    admin_idle_minutes: int = 30

    chain_id: int = 31337
    rpc_url: str = "http://localhost:8545"
    contract_address: str = ""  # written to .env by `make chain-deploy`
    issuer_address: str = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"  # DEV ONLY: Anvil #0

    signer_url: str = "http://localhost:8100"
    signer_hmac_secret: SecretStr

    anchor_interval_seconds: int = 10
    batch_max_leaves: int = 1024
    anchor_max_attempts: int = 5

    passport_template_dir: str = "app/pdf/templates"

    @field_validator("allowed_email_domains", mode="before")
    @classmethod
    def _split_domains(cls, value: object) -> object:
        if isinstance(value, str):
            return [d.strip().lower() for d in value.split(",") if d.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
