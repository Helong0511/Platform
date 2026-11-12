"""受限 MySQL SQL 解析器测试。"""
import pytest

from app.db.migrations.sql_parser import (
    MigrationSQLParseError,
    split_mysql_statements,
)


def test_splits_only_semicolons_outside_quotes_and_comments():
    sql = """
    -- header; ignored
    INSERT INTO t(value) VALUES ('a;b'), ("c;d");
    /* comment; ignored */
    UPDATE t SET value = 'escaped\\';still string';
    # tail; ignored
    SELECT `semi;colon` FROM t;
    """
    statements = split_mysql_statements(sql)
    assert len(statements) == 4
    assert "a;b" in statements[0]
    assert "c;d" in statements[0]
    assert "comment" not in statements[1]
    assert "escaped" in statements[2]
    assert "`semi;colon`" in statements[3]


def test_preserves_mysql_executable_comments():
    statements = split_mysql_statements("/*!80000 SET @value = 1 */; SELECT 1;")
    assert statements[0] == "/*!80000 SET @value = 1 */"
    assert statements[1] == "SELECT 1"


@pytest.mark.parametrize(
    "sql",
    ["SELECT 'unterminated", 'SELECT "unterminated', "SELECT `unterminated", "SELECT 1 /*"],
)
def test_rejects_unterminated_sql_constructs(sql):
    with pytest.raises(MigrationSQLParseError, match="unterminated"):
        split_mysql_statements(sql)


def test_rejects_mysql_client_delimiter_directive():
    with pytest.raises(MigrationSQLParseError, match="DELIMITER"):
        split_mysql_statements("DELIMITER //\nCREATE PROCEDURE p() SELECT 1//")


def test_empty_and_comment_only_files_have_no_statements():
    assert split_mysql_statements("-- only a comment;\n/* another */") == ()
