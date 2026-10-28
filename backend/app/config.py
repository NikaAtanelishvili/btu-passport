"""Settings for the API, worker and CLI (Overview §4).

The signer has its own settings class (signer/config.py); the issuer key file and the
deployer key are deliberately absent here.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Validation errors must not print the input: it holds every secret from .env.
        hide_input_in_errors=True,
    )

    env: Literal["dev", "test", "demo"] = "dev"
    timezone: str = "Asia/Tbilisi"
    public_base_url: str = "http://localhost:3000"

    database_url: str = "postgresql+psycopg://passport:passport@localhost:5432/passport"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minio"
    s3_secret_key: SecretStr
    s3_bucket: str = "passports"
    # MinIO: us-east-1 with path-style URLs; a hosted bucket (Railway) may need its own.
    s3_region: str = "us-east-1"
    s3_addressing_style: Literal["path", "virtual"] = "path"

    # Outgoing email: SMTP (Mailpit in dev) or Resend's HTTP API (hosts that block SMTP).
    mail_provider: Literal["smtp", "resend"] = "smtp"
    # SMTP_FROM is the name this had before MAIL_PROVIDER; still accepted.
    mail_from: str = Field(
        "passport@btu.test", validation_alias=AliasChoices("MAIL_FROM", "SMTP_FROM")
    )
    resend_api_key: SecretStr = SecretStr("")
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")

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
    # Exact addresses allowed to sign in with Google although their domain isn't (BE-15).
    allowed_emails: Annotated[list[str], NoDecode] = []
    bootstrap_super_admin_email: str = "superadmin@btu.test"
    # Extra super admins granted by `cli bootstrap --dev-users` (dev only, BE-16).
    dev_super_admin_emails: Annotated[list[str], NoDecode] = []

    # "Sign in with Google" (BE-15); empty client ID = the routes 404 and the button hides.
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")

    # Demo accounts with real inboxes (`python -m cli demo-users`); set in the demo env only.
    demo_super_admin_email: str = ""
    demo_admin_email: str = ""
    demo_student_email: str = ""
    demo_student_id: str = "BTU-T-0900"
    demo_student_first_name: str = "Demo"
    demo_student_last_name: str = "Student"

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

    # Google Sheets intake (M11, SH-01). Empty ID = no scheduled sync. The service account key
    # comes from a file (dev, relative to the repo root) or its JSON content (demo host).
    google_sheets_id: str = ""
    google_sheets_credentials_file: str = ""
    google_sheets_credentials_json: SecretStr = SecretStr("")
    sheet_sync_interval_seconds: int = 60
    sheet_writeback: bool = False

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, value: str) -> str:
        # Hosted Postgres (Railway) gives postgresql:// or postgres://; SQLAlchemy would pick
        # psycopg2, which isn't installed.
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value.removeprefix(prefix)
        return value

    @field_validator(
        "allowed_email_domains", "allowed_emails", "dev_super_admin_emails", mode="before"
    )
    @classmethod
    def _split_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [d.strip().lower() for d in value.split(",") if d.strip()]
        return value

    @model_validator(mode="after")
    def _no_logged_codes_outside_dev(self) -> "Settings":
        if self.dev_log_login_codes and self.env not in ("dev", "test"):
            raise ValueError(
                f"DEV_LOG_LOGIN_CODES=true is refused when ENV={self.env}: sign-in codes would "
                "be written to the log. Set DEV_LOG_LOGIN_CODES=false."
            )
        return self

    @model_validator(mode="after")
    def _demo_is_locked_down(self) -> "Settings":
        """ENV=demo (M10): a public deployment. Cookies only over HTTPS, and no dev-only
        sign-in exceptions; the API, worker and CLI refuse to start otherwise."""
        if self.env != "demo":
            return self
        if not self.session_secure:
            raise ValueError("ENV=demo needs SESSION_SECURE=true (session cookies over HTTPS)")
        if self.allowed_emails:
            raise ValueError(
                "ENV=demo refuses ALLOWED_EMAILS (dev-only sign-in exceptions); leave it empty "
                "and use ALLOWED_EMAIL_DOMAINS"
            )
        return self

    @model_validator(mode="after")
    def _cookie_prefix_needs_https(self) -> "Settings":
        """Browsers drop a __Host- / __Secure- cookie set over plain http, even on localhost
        (Chrome: InvalidPrefix), and sign-in then silently never sticks."""
        prefixed = self.session_cookie_name.startswith(("__Host-", "__Secure-"))
        if prefixed and not self.public_base_url.startswith("https://"):
            raise ValueError(
                f"SESSION_COOKIE_NAME={self.session_cookie_name} needs an https PUBLIC_BASE_URL "
                f"(it is {self.public_base_url}): browsers refuse the cookie prefix over http. "
                "Use a name without the prefix there, e.g. passport_session."
            )
        return self

    @model_validator(mode="after")
    def _resend_needs_its_key(self) -> "Settings":
        if self.mail_provider == "resend" and not self.resend_api_key.get_secret_value():
            raise ValueError("MAIL_PROVIDER=resend needs RESEND_API_KEY")
        return self

    @model_validator(mode="after")
    def _google_needs_its_secret(self) -> "Settings":
        if self.google_client_id and not self.google_client_secret.get_secret_value():
            raise ValueError("GOOGLE_CLIENT_ID is set but GOOGLE_CLIENT_SECRET is empty")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
