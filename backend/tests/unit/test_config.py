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
