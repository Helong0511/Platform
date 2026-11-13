"""应用启动使用的只读 schema revision gate；此模块绝不执行 DDL。"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.migrations.ledger import validate_ledger_rows
from app.db.migrations.manifest import Migration, MigrationManifestError, validate_manifest
from app.db.migrations.planner import plan_migrations


class SchemaRevisionNotReady(RuntimeError):
    """数据库 migration ledger 缺失、异常或落后于当前代码 manifest。"""


async def verify_schema_revision(
    connection,
    *,
    repository_root: str | Path | None = None,
    migrations: tuple[Migration, ...] | None = None,
) -> str | None:
    """只读核验当前数据库已应用全部 manifest migration。

    connection 必须由调用方提供；此函数只执行 SELECT，不创建数据库/表、
    不获取 DDL 锁、不自动补迁移。适合 API/Scheduler lifespan 的 readiness gate。
    """
    root = Path(repository_root).resolve() if repository_root else Path(__file__).resolve().parents[3]
    manifest = validate_manifest(root, migrations)
    try:
        result = await connection.execute(
            text(
                "SELECT revision, checksum, status, execution_order "
                "FROM platform_schema_migrations ORDER BY execution_order"
            )
        )
        rows = result.mappings().all()
    except SQLAlchemyError as exc:
        raise SchemaRevisionNotReady(
            "migration ledger 缺失或不可读取；必须先运行受控 provisioning/migration"
        ) from exc

    try:
        applied = validate_ledger_rows(
            rows,
            repository_root=root,
            migrations=manifest,
        )
    except MigrationManifestError as exc:
        raise SchemaRevisionNotReady(
            f"migration ledger 历史无效或存在未完成 migration：{type(exc).__name__}"
        ) from exc

    pending = plan_migrations(
        applied,
        repository_root=root,
        migrations=manifest,
    )
    if pending:
        raise SchemaRevisionNotReady(
            "数据库 schema revision 落后于当前代码："
            + ", ".join(item.revision for item in pending)
        )
    return manifest[-1].revision if manifest else None
