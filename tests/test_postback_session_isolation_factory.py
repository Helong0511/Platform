"""Postback 会话隔离级别与连接池边界回归测试。"""

from app.core.database import (
    AsyncSessionLocal,
    PostbackAsyncSessionLocal,
    engine,
    postback_engine,
)


def test_postback_session_factory_reuses_database_pool():
    """Postback 专用引擎不得创建第二套连接池。"""
    assert postback_engine.sync_engine.pool is engine.sync_engine.pool
    assert PostbackAsyncSessionLocal.kw["bind"] is postback_engine
    assert AsyncSessionLocal.kw["bind"] is engine


def test_postback_mysql_uses_read_committed_only_for_mysql_family():
    """MySQL/MariaDB Postback 使用 READ COMMITTED，其他方言不被强制修改。"""
    options = postback_engine.sync_engine.get_execution_options()
    if engine.dialect.name in {"mysql", "mariadb"}:
        assert options.get("isolation_level") == "READ COMMITTED"
    else:
        assert "isolation_level" not in options
        assert postback_engine is engine
