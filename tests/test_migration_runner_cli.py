"""Migration Runner CLI 凭据入口测试；不连接任何数据库。"""
from app.db.migrations.__main__ import main


def test_apply_requires_explicit_migration_dsn(monkeypatch, capsys):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    assert main(["apply"]) == 2
    output = capsys.readouterr().err
    assert "migration database credential is required" in output


def test_validate_remains_offline(capsys):
    assert main(["validate"]) == 0
    output = capsys.readouterr().out
    assert "No database connection was opened" in output


def test_status_requires_explicit_migration_dsn(monkeypatch, capsys):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    assert main(["status"]) == 2
    assert "migration database credential is required" in capsys.readouterr().err


def test_apply_reads_systemd_credentials_without_environment_fallback(
    tmp_path, monkeypatch, capsys
):
    from app.db.migrations import runner

    (tmp_path / "migration-database-url").write_text(
        "mysql+aiomysql://migration_user:secret@127.0.0.1:3306/platform",
        encoding="utf-8",
    )
    (tmp_path / "application-database-url").write_text(
        "mysql+aiomysql://application_user:secret@127.0.0.1:3306/platform",
        encoding="utf-8",
    )
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "mysql+aiomysql://wrong/must-not-use")
    monkeypatch.setenv("DATABASE_URL", "mysql+aiomysql://wrong/must-not-use")

    captured = {}

    async def fake_apply(database_url, application_database_url=None, **kwargs):
        captured["migration"] = database_url
        captured["application"] = application_database_url
        return ()

    monkeypatch.setattr(runner, "apply_migrations", fake_apply)
    assert main(["apply"]) == 0
    assert captured == {
        "migration": "mysql+aiomysql://migration_user:secret@127.0.0.1:3306/platform",
        "application": "mysql+aiomysql://application_user:secret@127.0.0.1:3306/platform",
    }
    assert "secret" not in capsys.readouterr().out


def test_systemd_credentials_directory_never_falls_back_to_environment(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "mysql+aiomysql://wrong/must-not-use")
    monkeypatch.setenv("DATABASE_URL", "mysql+aiomysql://wrong/must-not-use")
    assert main(["apply"]) == 2
    output = capsys.readouterr().err
    assert "migration database credential is required" in output
    assert "must-not-use" not in output


def test_status_reads_systemd_credentials_without_environment_fallback(
    tmp_path, monkeypatch, capsys
):
    from app.db.migrations import runner

    (tmp_path / "migration-database-url").write_text(
        "mysql+aiomysql://migration_user:secret@127.0.0.1:3306/platform",
        encoding="utf-8",
    )
    (tmp_path / "application-database-url").write_text(
        "mysql+aiomysql://application_user:secret@127.0.0.1:3306/platform",
        encoding="utf-8",
    )
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    captured = {}

    async def fake_status(database_url, application_database_url=None, **kwargs):
        captured["migration"] = database_url
        captured["application"] = application_database_url
        return []

    monkeypatch.setattr(runner, "read_migration_status", fake_status)
    assert main(["status"]) == 3
    assert captured == {
        "migration": "mysql+aiomysql://migration_user:secret@127.0.0.1:3306/platform",
        "application": "mysql+aiomysql://application_user:secret@127.0.0.1:3306/platform",
    }
    assert "secret" not in capsys.readouterr().out
