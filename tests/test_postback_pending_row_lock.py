"""Postback 待确认审批查询必须生成行级排他锁。"""
from sqlalchemy.dialects import mysql

from app.core.postback.pending_lock import build_pending_for_update_statement
from app.models.models import PendingPostbackConversion


def test_pending_approval_statement_uses_mysql_for_update_lock():
    statement = build_pending_for_update_statement(PendingPostbackConversion, 123)
    compiled = str(statement.compile(dialect=mysql.dialect())).upper()

    assert "FOR UPDATE" in compiled
    assert "PENDING_POSTBACK_CONVERSIONS.ID" in compiled
    assert "PENDING_POSTBACK_CONVERSIONS.STATUS" in compiled


def test_pending_approval_lock_is_scoped_to_pending_state():
    statement = build_pending_for_update_statement(PendingPostbackConversion, 123)
    compiled = str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))

    assert "id = 123" in compiled
    assert "status = 'pending'" in compiled
