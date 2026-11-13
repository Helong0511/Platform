"""迁移 CLI 离线验证测试。"""
from app.db.migrations.__main__ import main


def test_validate_command_is_explicitly_offline(capsys):
    assert main(["validate"]) == 0
    output = capsys.readouterr().out
    assert "Migration validation passed: 10 revision(s)" in output
    assert "No database connection was opened" in output


def test_cli_requires_an_explicit_subcommand():
    try:
        main([])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("CLI must require an explicit command")
