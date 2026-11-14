"""迁移 CLI 离线验证测试。"""
from app.db.migrations.__main__ import main
from app.db.migrations.manifest import validate_manifest


def test_validate_command_is_explicitly_offline(capsys):
    assert main(["validate"]) == 0
    output = capsys.readouterr().out
    expected_revision_count = len(validate_manifest())
    assert f"Migration validation passed: {expected_revision_count} revision(s)" in output
    assert "No database connection was opened" in output


def test_cli_requires_an_explicit_subcommand():
    try:
        main([])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("CLI must require an explicit command")
