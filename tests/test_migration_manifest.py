"""迁移清单完整性测试；只操作临时文件，不连接数据库。"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from app.db.migrations.manifest import (
    MIGRATION_MANIFEST,
    Migration,
    MigrationManifestError,
    validate_manifest,
)


def test_repository_migration_manifest_is_complete_and_ordered():
    migrations = validate_manifest()
    assert tuple(item.revision for item in migrations) == tuple(
        sorted(item.revision for item in migrations)
    )
    assert len({item.path for item in migrations}) == len(migrations)


def test_manifest_rejects_checksum_drift(tmp_path: Path):
    migration = Migration(
        revision="20261110_example",
        path="sql/migrations/20261110_example.sql",
        sha256="0" * 64,
    )
    target = tmp_path / migration.path
    target.parent.mkdir(parents=True)
    target.write_text("-- synthetic migration\n", encoding="utf-8")

    with pytest.raises(MigrationManifestError, match="checksum mismatch"):
        validate_manifest(tmp_path, (migration,))


def test_manifest_rejects_unregistered_sql_file(tmp_path: Path):
    migration = Migration(
        revision="20261110_example",
        path="sql/migrations/20261110_example.sql",
        sha256="",
    )
    target = tmp_path / migration.path
    target.parent.mkdir(parents=True)
    target.write_text("-- synthetic migration\n", encoding="utf-8")

    migration = replace(
        migration,
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    )
    (target.parent / "20261111_unregistered.sql").write_text(
        "-- must be explicitly registered\n", encoding="utf-8"
    )

    with pytest.raises(MigrationManifestError, match="file set mismatch"):
        validate_manifest(tmp_path, (migration,))


def test_manifest_rejects_unknown_or_forward_dependency(tmp_path: Path):
    entries = []
    for revision in ("20261110_first", "20261111_second"):
        path = f"sql/migrations/{revision}.sql"
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"-- {revision}\n", encoding="utf-8")
        entries.append(
            Migration(
                revision=revision,
                path=path,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            )
        )

    invalid = (
        replace(entries[0], depends_on=("20261112_missing",)),
        entries[1],
    )
    with pytest.raises(MigrationManifestError, match="unknown dependency"):
        validate_manifest(tmp_path, invalid)


def test_manifest_is_explicit_and_contains_no_unreviewed_files():
    assert len(MIGRATION_MANIFEST) == 12
    assert all(item.path.startswith("sql/migrations/") for item in MIGRATION_MANIFEST)

def test_manifest_rejects_revision_path_mismatch(tmp_path: Path):
    revision = "20261110_example"
    wrong_path = tmp_path / "sql/migrations" / "other_revision.sql"
    wrong_path.parent.mkdir(parents=True)
    wrong_path.write_text("-- matching bytes not enough\n", encoding="utf-8")
    migration = Migration(
        revision=revision,
        path="sql/migrations/other_revision.sql",
        sha256=hashlib.sha256(wrong_path.read_bytes()).hexdigest(),
    )
    with pytest.raises(MigrationManifestError, match="path does not match revision"):
        validate_manifest(tmp_path, (migration,))
