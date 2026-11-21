"""systemd application database credential configuration tests."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_systemd_application_database_credential_overrides_dotenv_and_environment(
    tmp_path: Path, monkeypatch
):
    credential = "mysql+aiomysql://credential_user:credential-secret@127.0.0.1:3306/platform"
    (tmp_path / "application-database-url").write_text(credential, encoding="utf-8")
    monkeypatch.setenv("UNIT_TEST", "1")
    monkeypatch.setenv("PRODUCTION_ENV", "development")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    monkeypatch.setenv(
        "DATABASE_URL",
        "mysql+aiomysql://environment_user:wrong@127.0.0.1:3306/wrong",
    )

    settings = Settings(_env_file=None)
    assert settings.SQLALCHEMY_DATABASE_URI == credential


def test_systemd_missing_application_credential_fails_closed(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("UNIT_TEST", "1")
    monkeypatch.setenv("PRODUCTION_ENV", "development")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    monkeypatch.setenv(
        "DATABASE_URL",
        "mysql+aiomysql://environment_user:must-not-fallback@127.0.0.1:3306/wrong",
    )

    with pytest.raises(ValidationError, match="systemd application database credential is required"):
        Settings(_env_file=None)
