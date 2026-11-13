"""平台完整基线 SQL 的关键结构完整性测试；不连接数据库。"""
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
