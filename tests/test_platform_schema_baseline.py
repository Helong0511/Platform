"""平台完整基线 SQL 的关键结构完整性测试；不连接数据库。"""
import re
from pathlib import Path

from app.db.migrations.sql_parser import split_mysql_statements


def test_platform_baseline_cap_reservation_table_has_complete_hex_check():
    source = (
        Path(__file__).resolve().parents[1] / "sql" / "platform.sql"
    ).read_text(encoding="utf-8")

    table_start = source.index("CREATE TABLE IF NOT EXISTS cap_reservations (")
    table_end_marker = "  COMMENT='Cap Redis 预留持久化账本';"
    table_end = source.index(table_end_marker, table_start) + len(table_end_marker)
    table_sql = source[table_start:table_end]

    statements = split_mysql_statements(table_sql)
    assert len(statements) == 1
    assert (
        "REGEXP_LIKE(reservation_key COLLATE utf8mb4_bin, "
        "'^[0-9a-f]{64}$', 'c')"
    ) in statements[0]
    assert source.count("CREATE TABLE IF NOT EXISTS cap_reservations (") == 1
    assert source.count("chk_cap_reservation_key_hex") == 1
    assert source.count("SET FOREIGN_KEY_CHECKS = 1;") == 1
    assert not re.search(r"^\s*CREATE\s+DATABASE\b", source, re.IGNORECASE | re.MULTILINE)
    assert not re.search(r"^\s*USE\s+", source, re.IGNORECASE | re.MULTILINE)


def test_platform_baseline_and_incremental_migrations_cover_all_orm_tables():
    import re

    from app.db.migrations.manifest import validate_manifest
    from app.models import Base

    root = Path(__file__).resolve().parents[1]
    sql_sources = [
        (root / "sql" / "platform.sql").read_text(encoding="utf-8")
    ]
    for migration in validate_manifest(root):
        sql_sources.append((root / migration.path).read_text(encoding="utf-8"))

    declared_tables = set()
    pattern = re.compile(
        r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+"
        r"`?([A-Za-z0-9_]+)`?\s*\(",
        re.IGNORECASE,
    )
    for source in sql_sources:
        declared_tables.update(match.group(1).lower() for match in pattern.finditer(source))

    orm_tables = {table.name.lower() for table in Base.metadata.sorted_tables}
    missing = sorted(orm_tables - declared_tables)
    assert not missing, (
        "完整基线与增量 migrations 未覆盖以下 ORM 表；这些表目前可能依赖应用启动时 "
        f"Base.metadata.create_all() 隐式创建：{missing}"
    )


def test_platform_baseline_third_party_identity_scope_is_complete():
    source = (
        Path(__file__).resolve().parents[1] / "sql" / "platform.sql"
    ).read_text(encoding="utf-8")

    table_start = source.index("CREATE TABLE IF NOT EXISTS `third_party_report_logs`")
    table_end_marker = "COMMENT = '第三方上报日志表' ROW_FORMAT = Dynamic;"
    table_end = source.index(table_end_marker, table_start) + len(table_end_marker)
    table_sql = source[table_start:table_end]
    statements = split_mysql_statements(table_sql)
    assert len(statements) == 1
    for column in ("platform", "identity_scope", "destination_pixel_id", "manual_retry_count"):
        assert f"`{column}`" in statements[0]
    assert "idx_third_party_scope_due" in statements[0]
    assert "chk_third_party_identity_scope_v1" in statements[0]
    assert "legacy_unresolved" in statements[0]
    assert "platform_scoped" in statements[0]

    lock_table_start = source.index(
        "CREATE TABLE IF NOT EXISTS `third_party_report_identity_locks`"
    )
    lock_table_end = source.index(
        "COMMENT = '第三方上报跨直接发送与 Postback 的基础身份仲裁锁';",
        lock_table_start,
    )
    lock_table_sql = source[lock_table_start:lock_table_end]
    assert len(split_mysql_statements(lock_table_sql)) == 1
    assert "`identity_key` CHAR(64)" in lock_table_sql
    assert "`identity_fingerprint` BINARY(64)" in lock_table_sql
