"""纯函数迁移计划生成器；不访问数据库、不执行 DDL。"""
from __future__ import annotations

from collections.abc import Mapping

from app.db.migrations.manifest import (
    MIGRATION_MANIFEST,
    Migration,
    MigrationManifestError,
    validate_manifest,
)


def plan_migrations(
    applied_checksums: Mapping[str, str],
    *,
    repository_root=None,
    migrations: tuple[Migration, ...] | None = None,
) -> tuple[Migration, ...]:
    """根据 ledger 中已应用 revision/checksum 计算待执行项。

    已应用但未知的 revision、checksum 漂移、依赖未满足或 ledger 顺序倒置
    一律 fail closed。调用方必须从真实 ledger 读取 checksum，不得只传 revision。
    """
    ordered = validate_manifest(repository_root, migrations)
    by_revision = {item.revision: item for item in ordered}

    unknown = sorted(set(applied_checksums) - set(by_revision))
    if unknown:
        raise MigrationManifestError(f"ledger contains unknown revisions: {unknown}")

    applied_positions = [
        index for index, item in enumerate(ordered)
        if item.revision in applied_checksums
    ]
    if applied_positions != sorted(applied_positions):
        raise MigrationManifestError("ledger revisions are not in manifest order")

    for revision, stored_checksum in applied_checksums.items():
        expected = by_revision[revision].sha256
        if stored_checksum != expected:
            raise MigrationManifestError(
                f"applied migration checksum drift: {revision}"
            )

    applied = set(applied_checksums)
    pending: list[Migration] = []
    for item in ordered:
        if item.revision in applied:
            continue
        missing_dependencies = sorted(set(item.depends_on) - applied)
        if missing_dependencies:
            raise MigrationManifestError(
                f"migration {item.revision} has unapplied dependencies: "
                f"{missing_dependencies}"
            )
        pending.append(item)
        # 计划中的前置 revision 可满足后续依赖，但只在清单顺序正确时成立。
        applied.add(item.revision)

    return tuple(pending)
