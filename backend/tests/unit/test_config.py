import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def _required_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings has no defaults for secrets; don't depend on `make` exporting .env.
    monkeypatch.setenv("S3_SECRET_KEY", "test")
    monkeypatch.setenv("SIGNER_HMAC_SECRET", "test")


def test_email_domains_split_from_comma_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "BTU.edu.ge, btu.test")
    settings = Settings(_env_file=None)
    assert settings.allowed_email_domains == ["btu.edu.ge", "btu.test"]


def test_login_defaults_match_overview(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SMTP_HOST", "SMTP_PORT", "LOGIN_CODE_TTL_MINUTES", "DEV_LOG_LOGIN_CODES"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert (settings.smtp_host, settings.smtp_port) == ("localhost", 1025)
    assert settings.login_code_ttl_minutes == 10
    assert settings.login_code_max_attempts == 5
    assert (settings.login_rate_per_email_hour, settings.login_rate_per_ip_hour) == (5, 20)
    assert settings.dev_log_login_codes is True


@pytest.mark.parametrize("env", ["dev", "test"])
def test_dev_log_login_codes_allowed_in_dev_and_test(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("ENV", env)
    monkeypatch.setenv("DEV_LOG_LOGIN_CODES", "true")
    assert Settings(_env_file=None).dev_log_login_codes is True


def test_dev_log_login_codes_refused_in_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "demo")
    monkeypatch.setenv("DEV_LOG_LOGIN_CODES", "true")
    with pytest.raises(ValueError, match="DEV_LOG_LOGIN_CODES"):
        Settings(_env_file=None)
    monkeypatch.setenv("DEV_LOG_LOGIN_CODES", "false")
    assert Settings(_env_file=None).env == "demo"


def test_api_refuses_to_start_with_dev_log_in_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("ENV", "demo")
    monkeypatch.setenv("DEV_LOG_LOGIN_CODES", "true")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="DEV_LOG_LOGIN_CODES"):
            create_app()
    finally:
        get_settings.cache_clear()


def test_settings_errors_never_echo_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "demo")
    monkeypatch.setenv("DEV_LOG_LOGIN_CODES", "true")
    monkeypatch.setenv("SIGNER_HMAC_SECRET", "super-secret-hmac-value")
    monkeypatch.setenv("SMTP_PASSWORD", "super-secret-smtp-value")
    with pytest.raises(ValueError) as excinfo:
        Settings(_env_file=None)
    message = str(excinfo.value)
    assert "super-secret" not in message
    assert "input_value" not in message  # pydantic truncates, so check nothing is echoed at all


def test_mail_provider_defaults_to_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAIL_PROVIDER", raising=False)
    assert Settings(_env_file=None).mail_provider == "smtp"


def test_resend_needs_its_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_PROVIDER", "resend")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    with pytest.raises(ValueError, match="RESEND_API_KEY"):
        Settings(_env_file=None)
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    assert Settings(_env_file=None).mail_provider == "resend"


@pytest.mark.parametrize(
    "url",
    ["postgresql://u:p@db.internal:5432/railway", "postgres://u:p@db.internal:5432/railway"],
)
def test_plain_postgres_url_gets_the_psycopg_driver(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    # Railway's Postgres hands out postgresql:// (and some hosts postgres://) URLs.
    monkeypatch.setenv("DATABASE_URL", url)
    assert Settings(_env_file=None).database_url == (
        "postgresql+psycopg://u:p@db.internal:5432/railway"
    )


def test_explicit_driver_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://passport:x@localhost/passport")
    assert Settings(_env_file=None).database_url.startswith("postgresql+psycopg://passport")


def test_s3_region_and_addressing_default_to_minio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S3_REGION", raising=False)
    monkeypatch.delenv("S3_ADDRESSING_STYLE", raising=False)
    s = Settings(_env_file=None)
    assert (s.s3_region, s.s3_addressing_style) == ("us-east-1", "path")
    monkeypatch.setenv("S3_REGION", "auto")
    monkeypatch.setenv("S3_ADDRESSING_STYLE", "virtual")
    s = Settings(_env_file=None)
    assert (s.s3_region, s.s3_addressing_style) == ("auto", "virtual")
