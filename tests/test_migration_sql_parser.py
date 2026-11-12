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
    assert len(statements) == 3
    assert "a;b" in statements[0]
    assert "c;d" in statements[0]
    assert "comment" not in statements[1]
    assert "escaped" in statements[1]
    assert "`semi;colon`" in statements[2]


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


def test_backslash_handling_can_match_mysql_no_backslash_escapes_mode():
    sql = "SELECT 'one\\'; SELECT 'two';"
    # NO_BACKSLASH_ESCAPES 下，反斜杠不转义引号，两个语句必须正确切开。
    statements = split_mysql_statements(sql, backslash_escapes=False)
    assert len(statements) == 2


def test_all_repository_migrations_are_parseable_without_client_delimiter():
    from pathlib import Path

    migration_files = sorted(Path("sql/migrations").glob("*.sql"))
    assert migration_files
    for migration_file in migration_files:
        statements = split_mysql_statements(
            migration_file.read_text(encoding="utf-8")
        )
        assert statements, migration_file.name


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE PROCEDURE p() BEGIN SELECT 1; SELECT 2; END",
        "CREATE DEFINER=CURRENT_USER FUNCTION f() RETURNS INT RETURN 1",
        "CREATE TRIGGER t BEFORE INSERT ON items FOR EACH ROW SET @x = 1",
        "CREATE EVENT e ON SCHEDULE EVERY 1 DAY DO SELECT 1",
    ],
)
def test_rejects_routine_ddl_even_without_delimiter_directive(sql):
    with pytest.raises(MigrationSQLParseError, match="stored routines"):
        split_mysql_statements(sql)
