"""版本化 SQL migration 清单与完整性校验。

本模块只负责发现、排序和校验迁移文件；不执行 SQL，不连接数据库。
正式 Runner 必须先调用 validate_manifest()，再实施独立的锁、ledger 和 SQL 执行策略。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Migration:
    """一条不可变的迁移声明。"""

    revision: str
    path: str
    sha256: str
    depends_on: tuple[str, ...] = ()


# 仅允许显式登记的迁移；新增 SQL 文件必须先经过审查并登记 SHA-256。
MIGRATION_MANIFEST: tuple[Migration, ...] = (
    Migration(
        revision="20261110_short_link_click_sync_idempotency",
        path="sql/migrations/20261110_short_link_click_sync_idempotency.sql",
        sha256="e814f85af3881485d3322e812aaa3a656a096a630a2f177b7690daa3a7a0788b",
    ),
    Migration(
        revision="20261110_third_party_report_event_idempotency",
        path="sql/migrations/20261110_third_party_report_event_idempotency.sql",
        sha256="57c865bea2818b1923260838a9594a6043a0892081c7d68085794f79092f1c26",
    ),
    Migration(
        revision="20261111_cap_reservation_ledger",
        path="sql/migrations/20261111_cap_reservation_ledger.sql",
        sha256="672a0dc9f5a8f50c256d4acc5105c177034524f4b0c2866d9bd8db3fda2cbad7",
    ),
    Migration(
        revision="20261111_third_party_report_outbox",
        path="sql/migrations/20261111_third_party_report_outbox.sql",
        sha256="96d14e271a7f8cea7f1a8f3ba4173859b1b3002bb81aac06bf6d774c1231583b",
        depends_on=("20261110_third_party_report_event_idempotency",),
    ),
    Migration(
        revision="20261112_third_party_report_pii_retention",
        path="sql/migrations/20261112_third_party_report_pii_retention.sql",
        sha256="2d9a32a7e0a71f9ec8cdce77c40cea834d912c97d65c1926c8fbac34db5e33cb",
    ),
    Migration(
        revision="20261113_cap_reservation_key_hex",
        path="sql/migrations/20261113_cap_reservation_key_hex.sql",
        sha256="7cd84df9412d0ba753d3d1a9721a7a330334780c05fee69b84783ed2417ca552",
        depends_on=("20261111_cap_reservation_ledger",),
    ),
    Migration(
        revision="20261113_cap_reservation_schema_guard",
        path="sql/migrations/20261113_cap_reservation_schema_guard.sql",
        sha256="014c549db77112c521467a3a37fc74e5bc2e0f2ffb594142962356661db149e1",
        depends_on=("20261111_cap_reservation_ledger",),
    ),
    Migration(
        revision="20261113_third_party_report_identity_scope",
        path="sql/migrations/20261113_third_party_report_identity_scope.sql",
        sha256="1c9971602ac456cb35552a11f21cce935bcda754d766a292fcf563d26e28c66a",
        depends_on=(
            "20261111_third_party_report_outbox",
            "20261112_third_party_report_pii_retention",
        ),
    ),
    Migration(
        revision="20261113_third_party_report_identity_scope_constraints",
        path="sql/migrations/20261113_third_party_report_identity_scope_constraints.sql",
        sha256="06c81f67d9d9cbcc170ac21142bdc8ee2c3835792bb83f4cb092c92f2f91fe88",
        depends_on=("20261113_third_party_report_identity_scope",),
    ),
    Migration(
        revision="20261113_third_party_report_identity_scope_locks",
        path="sql/migrations/20261113_third_party_report_identity_scope_locks.sql",
        sha256="ee2ff49f0afd71727c0d00c03bd7a99f0c25592b4d27351ccb8f357b8596ebc4",
        depends_on=("20261113_third_party_report_identity_scope",),
    ),
)

_REVISION_PATTERN = re.compile(r"^20[0-9]{6}_[a-z0-9_]+$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class MigrationManifestError(RuntimeError):
    """迁移清单、顺序或文件内容不可信时拒绝继续。"""


def _repository_root() -> Path:
    """从源码位置定位仓库根目录，不依赖当前工作目录。"""
    return Path(__file__).resolve().parents[3]


def validate_manifest(
    repository_root: Path | None = None,
    migrations: Iterable[Migration] | None = None,
) -> tuple[Migration, ...]:
    """验证 revision、依赖、文件集合和 SHA-256，成功后返回确定执行顺序。

    此函数不会执行 SQL 或创建/修改任何数据库对象。
    """
    root = (repository_root or _repository_root()).resolve()
    entries = tuple(migrations if migrations is not None else MIGRATION_MANIFEST)

    if not entries:
        raise MigrationManifestError("migration manifest is empty")

    by_revision: dict[str, Migration] = {}
    seen_paths: set[str] = set()
    for entry in entries:
        if not _REVISION_PATTERN.fullmatch(entry.revision):
            raise MigrationManifestError(f"invalid migration revision: {entry.revision!r}")
        if entry.revision in by_revision:
            raise MigrationManifestError(f"duplicate migration revision: {entry.revision}")
        if not _SHA256_PATTERN.fullmatch(entry.sha256):
            raise MigrationManifestError(f"invalid SHA-256 for revision: {entry.revision}")
        if entry.path in seen_paths:
            raise MigrationManifestError(f"duplicate migration path: {entry.path}")
        expected_path = f"sql/migrations/{entry.revision}.sql"
        if entry.path != expected_path:
            raise MigrationManifestError(
                f"migration path does not match revision {entry.revision}: {entry.path}"
            )
        candidate = (root / entry.path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise MigrationManifestError(
                f"migration path escapes repository root: {entry.path}"
            ) from exc
        if not candidate.is_file():
            raise MigrationManifestError(f"migration file missing: {entry.path}")
        actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual_hash != entry.sha256:
            raise MigrationManifestError(
                f"migration checksum mismatch: {entry.revision}"
            )
        by_revision[entry.revision] = entry
        seen_paths.add(entry.path)

    # revision 使用日期前缀；清单顺序必须与 revision 字典序一致，避免隐式重排。
    revisions = [entry.revision for entry in entries]
    if revisions != sorted(revisions):
        raise MigrationManifestError("migration manifest is not in deterministic revision order")

    for entry in entries:
        if entry.revision in entry.depends_on:
            raise MigrationManifestError(f"migration depends on itself: {entry.revision}")
        for dependency in entry.depends_on:
            if dependency not in by_revision:
                raise MigrationManifestError(
                    f"unknown dependency {dependency!r} for {entry.revision}"
                )
            if dependency >= entry.revision:
                raise MigrationManifestError(
                    f"dependency must precede {entry.revision}: {dependency}"
                )

    # 防止未登记 SQL 被悄悄遗漏，也防止登记路径之外的脚本被误执行。
    migration_dir = (root / "sql" / "migrations").resolve()
    if not migration_dir.is_dir():
        raise MigrationManifestError("migration directory is missing: sql/migrations")
    discovered = {
        path.relative_to(root).as_posix()
        for path in migration_dir.glob("*.sql")
        if path.is_file()
    }
    if discovered != seen_paths:
        missing = sorted(discovered - seen_paths)
        stale = sorted(seen_paths - discovered)
        raise MigrationManifestError(
            f"migration file set mismatch: unregistered={missing}, missing={stale}"
        )

    return entries
