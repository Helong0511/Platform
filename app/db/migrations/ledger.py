"""Migration ledger 原始记录校验；必须在构造 revision->checksum 映射前调用。"""
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
    allow_running_revisions: Iterable[str] = (),
) -> dict[str, str]:
    """校验原始 ledger；默认只接受 applied，指定安全回填才可接受末尾 running。

    普通 running/failed 必须人工核验 DDL。只有 manifest 显式登记 backfill_handler
    且调用方显式允许的唯一末尾 running revision，才可作为可续跑状态返回。
    """
    manifest = validate_manifest(repository_root, migrations)
    manifest_by_revision = {item.revision: item for item in manifest}
    allowed_running = set(allow_running_revisions)
    unknown_allowed = allowed_running - set(manifest_by_revision)
    if unknown_allowed:
        raise MigrationLedgerError(
            f"allow_running_revisions contains unknown revisions: {sorted(unknown_allowed)}"
        )
    unsafe_allowed = sorted(
        revision
        for revision in allowed_running
        if manifest_by_revision[revision].backfill_handler is None
    )
    if unsafe_allowed:
        raise MigrationLedgerError(
            f"running resume is not declared safe for revisions: {unsafe_allowed}"
        )

    seen_revisions: set[str] = set()
    seen_orders: set[int] = set()
    normalized: list[tuple[int, str, str, str]] = []

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
        if status == "running":
            if revision not in allowed_running:
                raise MigrationLedgerError(
                    f"migration ledger is not fully applied: {revision} status='running'; "
                    "manual DDL recovery is required"
                )
        elif status != "applied":
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
        normalized.append((execution_order, revision, checksum, status))

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

    running_positions = [
        index for index, item in enumerate(normalized) if item[3] == "running"
    ]
    if len(running_positions) > 1 or (
        running_positions and running_positions[0] != len(normalized) - 1
    ):
        raise MigrationLedgerError(
            "only one explicitly resumable running migration may appear at the end of ledger"
        )

    applied: dict[str, str] = {}
    for _order, revision, stored_checksum, status in normalized:
        expected_checksum = manifest_by_revision[revision].sha256
        if stored_checksum != expected_checksum:
            raise MigrationLedgerError(
                f"applied migration checksum drift: {revision}"
            )
        if status == "applied":
            applied[revision] = stored_checksum
    return applied
