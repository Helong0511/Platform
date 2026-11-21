"""systemd Migration Runner 发布依赖契约测试；不连接系统服务或数据库。"""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _unit(name: str) -> str:
    return (ROOT / "systemd" / name).read_text(encoding="utf-8")


def _values(content: str, key: str) -> list[str]:
    return [
        line.split("=", 1)[1].strip()
        for line in content.splitlines()
        if line.strip().startswith(f"{key}=")
    ]


def test_migration_unit_is_fail_closed_and_uses_separate_os_identity():
    unit = _unit("Platform-migrate.service")
    assert "Type=oneshot" in unit
    assert "RemainAfterExit=yes" in unit
    assert "User=platform-migrator" in unit
    assert "Group=platform-migrator" in unit
    assert "LoadCredential=application-database-url:/etc/platform/migration-app-database-url" in unit
    assert "LoadCredential=migration-database-url:/etc/platform/migration-database-url" in unit
    assert "EnvironmentFile=" not in unit
    assert "WorkingDirectory=/run/platform-migration" in unit
    assert "RuntimeDirectory=platform-migration" in unit
    assert "ProtectSystem=strict" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ReadOnlyPaths=/data/Platform" in unit
    assert "PYTHONPATH=/data/Platform" in unit
    assert "PYTHONDONTWRITEBYTECODE=1" in unit
    assert "/data/Platform/.env" not in unit

    pre = _values(unit, "ExecStartPre")
    start = _values(unit, "ExecStart")
    post = _values(unit, "ExecStartPost")
    assert len(pre) == 1 and pre[0].endswith("-m app.db.migrations validate")
    assert len(start) == 1 and start[0].endswith("-m app.db.migrations apply")
    assert len(post) == 1 and post[0].endswith("-m app.db.migrations status")
    assert "TimeoutStartSec=2h" in unit
    assert "Restart=no" in unit


def test_backend_and_scheduler_require_successful_migration_unit():
    for filename in ("Platform-backend.service", "Platform-scheduler.service"):
        unit = _unit(filename)
        assert "Requires=Platform-migrate.service" in unit
        after = " ".join(_values(unit, "After"))
        assert "Platform-migrate.service" in after


def test_migration_credentials_are_not_part_of_application_env_template():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert not re.search(r"^\s*MIGRATION_DATABASE_URL\s*=", env_example, re.MULTILINE)
    assert "LoadCredential" in env_example
    assert "root-only" in env_example
