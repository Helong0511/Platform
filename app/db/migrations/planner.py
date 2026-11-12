"""纯函数迁移计划生成器；不访问数据库、不执行 DDL。"""
from __future__ import annotations

from collections.abc import Mapping

from app.db.migrations.manifest import (
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

    已应用但未知的 revision、checksum 漂移、依赖未满足或 ledger 历史断档
    一律 fail closed。调用方必须按数据库分配的 execution_order 升序读取 ledger，并保留该顺序；不得只传 revision。
    """
    ordered = validate_manifest(repository_root, migrations)
    by_revision = {item.revision: item for item in ordered}

    unknown = sorted(set(applied_checksums) - set(by_revision))
    if unknown:
        raise MigrationManifestError(f"ledger contains unknown revisions: {unknown}")

    # 调用方必须按 ledger.execution_order 升序读取；不可依赖 applied_at（可能同值）或 SQL 默认返回顺序。历史必须与 manifest 前缀完全一致。
    # 同时检查映射插入顺序，避免只检查集合而漏掉乱序 ledger。
    applied_revisions = list(applied_checksums)
    expected_prefix = [item.revision for item in ordered[:len(applied_revisions)]]
    if applied_revisions != expected_prefix:
        raise MigrationManifestError("ledger revisions are not a contiguous manifest prefix")

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
