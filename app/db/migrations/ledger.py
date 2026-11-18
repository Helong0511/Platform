"""迁移 ledger 原始记录校验；必须在构造 revision->checksum 映射前调用。"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.db.migrations.manifest import (
    Migration,
    MigrationManifestError,
    validate_manifest,
)


_CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class MigrationLedgerError(MigrationManifestError):
    """迁移 ledger 原始行重复、乱序、状态异常或校验和不可信。"""


def validate_ledger_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    repository_root=None,
    migrations: tuple[Migration, ...] | None = None,
) -> dict[str, str]:
    """校验数据库返回的原始 ledger 行，再生成有序 applied checksum 映射。

    不允许调用方先用 dict comprehension 归并数据库行：那会静默覆盖重复
    revision，且丢失 execution_order 冲突。只有状态全部为 applied、执行序号
    连续且 revision/checksum 与 manifest 前缀一致时，才返回 planner 可用映射。
    running/failed 记录必须先由人工核验 DDL 部分执行状态，不能自动猜测重试。
    """
    manifest = validate_manifest(repository_root, migrations)
    manifest_by_revision = {item.revision: item for item in manifest}

    seen_revisions: set[str] = set()
    seen_orders: set[int] = set()
    normalized: list[tuple[int, str, str]] = []

    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise MigrationLedgerError(f"ledger row {index} is not a mapping")

        revision = row.get("revision")
        checksum = row.get("checksum")
        status = row.get("status")
        execution_order = row.get("execution_order")

        if not isinstance(revision, str) or not revision:
            raise MigrationLedgerError(f"ledger row {index} has an invalid revision")
        if revision in seen_revisions:
            raise MigrationLedgerError(f"duplicate ledger revision: {revision}")
        seen_revisions.add(revision)

        if not isinstance(checksum, str) or not _CHECKSUM_PATTERN.fullmatch(checksum):
            raise MigrationLedgerError(f"invalid ledger checksum: {revision}")
        if status != "applied":
            raise MigrationLedgerError(
                f"migration ledger is not fully applied: {revision} status={status!r}; "
                "manual DDL recovery is required"
            )
        if type(execution_order) is not int or execution_order < 1:
            raise MigrationLedgerError(
                f"invalid migration execution_order: {revision}"
            )
        if execution_order in seen_orders:
            raise MigrationLedgerError(
                f"duplicate migration execution_order: {execution_order}"
            )
        seen_orders.add(execution_order)

        if revision not in manifest_by_revision:
            raise MigrationLedgerError(f"ledger contains unknown revision: {revision}")
        normalized.append((execution_order, revision, checksum))

    normalized.sort(key=lambda item: item[0])
    actual_orders = [item[0] for item in normalized]
    expected_orders = list(range(1, len(normalized) + 1))
    if actual_orders != expected_orders:
        raise MigrationLedgerError(
            "migration execution_order must be a unique contiguous sequence starting at 1"
        )

    actual_revisions = [item[1] for item in normalized]
    expected_revisions = [item.revision for item in manifest[:len(normalized)]]
    if actual_revisions != expected_revisions:
        raise MigrationLedgerError(
            "ledger revisions are not a contiguous manifest prefix in execution_order"
        )

    applied: dict[str, str] = {}
    for _order, revision, stored_checksum in normalized:
        expected_checksum = manifest_by_revision[revision].sha256
        if stored_checksum != expected_checksum:
            raise MigrationLedgerError(
                f"applied migration checksum drift: {revision}"
            )
        applied[revision] = stored_checksum
    return applied
