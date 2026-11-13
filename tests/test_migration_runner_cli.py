"""Migration Runner CLI 安全入口测试；不连接任何数据库。"""
from app.db.migrations.__main__ import main


def test_apply_requires_explicit_migration_dsn(monkeypatch, capsys):
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    assert main(["apply"]) == 2
    output = capsys.readouterr().err
    assert "MIGRATION_DATABASE_URL is required" in output


def test_validate_remains_offline(capsys):
    assert main(["validate"]) == 0
    output = capsys.readouterr().out
    assert "No database connection was opened" in output
