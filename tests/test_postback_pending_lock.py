"""待确认记录锁查询必须支持读取已处理状态用于审计分类。"""
from sqlalchemy.dialects import mysql

from app.core.postback.pending_lock import build_pending_for_update_statement
from app.models.models import PendingPostbackConversion


def test_pending_lock_can_read_any_status_without_dropping_row_lock():
    statement = build_pending_for_update_statement(
        PendingPostbackConversion,
        123,
        status=None,
    )
    sql = str(statement.compile(dialect=mysql.dialect()))

    assert "pending_postback_conversions.id = 123" in sql
    assert "pending_postback_conversions.status" not in sql
    assert sql.rstrip().endswith("FOR UPDATE")


def test_pending_lock_defaults_to_pending_status():
    statement = build_pending_for_update_statement(
        PendingPostbackConversion,
        123,
    )
    sql = str(statement.compile(dialect=mysql.dialect()))

    assert "pending_postback_conversions.status = 'pending'" in sql
    assert sql.rstrip().endswith("FOR UPDATE")
