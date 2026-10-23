import pytest

from app.config import Settings


def test_email_domains_split_from_comma_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "BTU.edu.ge, btu.test")
    settings = Settings(_env_file=None)
    assert settings.allowed_email_domains == ["btu.edu.ge", "btu.test"]
    assert settings.signer_hmac_secret.get_secret_value() != ""
