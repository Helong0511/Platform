"""迁移计划纯函数测试；不访问数据库。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.db.migrations.manifest import Migration, MigrationManifestError
from app.db.migrations.planner import plan_migrations


def _fixture(tmp_path: Path):
    entries = []
    for revision, dependency in (
        ("20261110_first", ()),
        ("20261111_second", ("20261110_first",)),
        ("20261112_third", ("20261111_second",)),
    ):
        relative = f"sql/migrations/{revision}.sql"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"-- {revision}\n", encoding="utf-8")
        entries.append(
            Migration(
                revision=revision,
                path=relative,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                depends_on=dependency,
            )
        )
    return tuple(entries)


def test_plan_returns_all_pending_in_manifest_order(tmp_path: Path):
    entries = _fixture(tmp_path)
    plan = plan_migrations({}, repository_root=tmp_path, migrations=entries)
    assert [item.revision for item in plan] == [item.revision for item in entries]


def test_plan_skips_applied_and_returns_remaining(tmp_path: Path):
    entries = _fixture(tmp_path)
    applied = {entries[0].revision: entries[0].sha256}
    plan = plan_migrations(applied, repository_root=tmp_path, migrations=entries)
    assert [item.revision for item in plan] == [
        "20261111_second", "20261112_third"
    ]


def test_plan_rejects_applied_checksum_drift(tmp_path: Path):
    entries = _fixture(tmp_path)
    with pytest.raises(MigrationManifestError, match="checksum drift"):
        plan_migrations(
            {entries[0].revision: "0" * 64},
            repository_root=tmp_path,
            migrations=entries,
        )


def test_plan_rejects_unknown_ledger_revision(tmp_path: Path):
    entries = _fixture(tmp_path)
    with pytest.raises(MigrationManifestError, match="unknown revisions"):
        plan_migrations(
            {"20261109_unknown": "0" * 64},
            repository_root=tmp_path,
            migrations=entries,
        )


def test_plan_rejects_non_prefix_ledger_history(tmp_path: Path):
    entries = _fixture(tmp_path)
    with pytest.raises(MigrationManifestError, match="contiguous manifest prefix"):
        plan_migrations(
            {
                entries[1].revision: entries[1].sha256,
                entries[0].revision: entries[0].sha256,
            },
            repository_root=tmp_path,
            migrations=entries,
        )


def test_plan_rejects_dependency_gap(tmp_path: Path):
    entries = _fixture(tmp_path)
    # 使用独立的迁移清单，仅登记依赖项之后的迁移，验证依赖缺失会阻断计划。
    from dataclasses import replace

    only_second = (replace(entries[1], depends_on=("20261110_first",)),)
    with pytest.raises(MigrationManifestError, match="unknown dependency"):
        plan_migrations({}, repository_root=tmp_path, migrations=only_second)

def test_plan_rejects_non_prefix_ledger(tmp_path: Path):
    entries = _fixture(tmp_path)
    with pytest.raises(MigrationManifestError, match="contiguous manifest prefix"):
        plan_migrations(
            {entries[1].revision: entries[1].sha256},
            repository_root=tmp_path,
            migrations=entries,
        )
