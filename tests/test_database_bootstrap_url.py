"""数据库引导 URI 解析的纯单元测试，不建立真实数据库连接。"""

from app.db.database import _get_database_bootstrap_target


def test_mysql_bootstrap_preserves_credentials_and_query_parameters():
    uri = (
        "mysql+aiomysql://deploy:p%40ss%2Fplatform@127.0.0.1:3306/"
        "platform?charset=utf8mb4"
    )

    target = _get_database_bootstrap_target(uri)

    assert target is not None
    server_url, database_name = target
    assert database_name == "platform"
    assert server_url.database is None
    assert server_url.username == "deploy"
    assert server_url.password == "p@ss/platform"
    assert server_url.host == "127.0.0.1"
    assert server_url.port == 3306
    assert server_url.query["charset"] == "utf8mb4"


def test_mysql_bootstrap_uses_configured_database_name_not_hardcoded_name():
    target = _get_database_bootstrap_target(
        "mysql+aiomysql://user:secret@localhost/platform_stage"
    )

    assert target is not None
    server_url, database_name = target
    assert database_name == "platform_stage"
    assert server_url.database is None


def test_non_mysql_backend_does_not_require_create_database():
    assert _get_database_bootstrap_target("sqlite+aiosqlite:///./platform.db") is None


def test_mysql_bootstrap_requires_database_name():
    import pytest

    with pytest.raises(ValueError, match="必须指定目标数据库名"):
        _get_database_bootstrap_target("mysql+aiomysql://user:secret@localhost/")
