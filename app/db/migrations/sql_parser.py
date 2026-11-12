"""受限 MySQL SQL 文件解析器。

支持常见字符串/标识符引号、行注释、块注释和语句分隔。
明确拒绝 DELIMITER 指令；不支持存储过程/触发器定义脚本。
"""
from __future__ import annotations


class MigrationSQLParseError(ValueError):
    """迁移 SQL 超出受支持语法时拒绝执行。"""


def split_mysql_statements(
    sql: str, *, backslash_escapes: bool = True
) -> tuple[str, ...]:
    """按 SQL 语法状态切分语句；调用方应按当前 MySQL SQL_MODE 设置转义规则。"""
    if not isinstance(sql, str):
        raise TypeError("migration SQL must be text")

    statements: list[str] = []
    buffer: list[str] = []
    state = "normal"
    index = 0
    length = len(sql)

    def finish_statement() -> None:
        statement = "".join(buffer).strip()
        buffer.clear()
        if statement:
            statements.append(statement)

    while index < length:
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < length else ""

        if state == "normal":
            # DELIMITER 是 mysql 客户端指令，不是服务端 SQL；拒绝而不是误执行。
            if not buffer or not "".join(buffer).strip():
                line_end = sql.find("\n", index)
                line_end = length if line_end < 0 else line_end
                line = sql[index:line_end].strip()
                if line.upper().startswith("DELIMITER "):
                    raise MigrationSQLParseError("DELIMITER directives are not supported")
            if char == "'":
                state = "single"
                buffer.append(char)
                index += 1
                continue
            if char == '"':
                state = "double"
                buffer.append(char)
                index += 1
                continue
            if char == chr(96):
                state = "backtick"
                buffer.append(char)
                index += 1
                continue
            if char == "#" or (
                char == "-" and nxt == "-" and
                (index + 2 == length or sql[index + 2].isspace() or ord(sql[index + 2]) < 32)
            ):
                state = "line_comment"
                index += 2 if char == "-" else 1
                continue
            if char == "/" and nxt == "*":
                # MySQL /*! ... */ 是服务端可执行注释，必须保留。
                if index + 2 < length and sql[index + 2] == "!":
                    buffer.extend(("/*", "!"))
                    index += 3
                    state = "executable_comment"
                else:
                    state = "block_comment"
                    index += 2
                continue
            if char == ";":
                finish_statement()
                index += 1
                continue
            buffer.append(char)
            index += 1
            continue

        if state in {"single", "double", "backtick"}:
            quote = {"single": "'", "double": '"', "backtick": chr(96)}[state]
            buffer.append(char)
            if backslash_escapes and char == "\\\\" and state != "backtick" and index + 1 < length:
                buffer.append(sql[index + 1])
                index += 2
                continue
            if char == quote:
                if nxt == quote:
                    buffer.append(nxt)
                    index += 2
                    continue
                state = "normal"
            index += 1
            continue

        if state == "line_comment":
            if char == "\n":
                buffer.append("\n")
                state = "normal"
            index += 1
            continue

        if state == "block_comment":
            if char == "*" and nxt == "/":
                buffer.append(" ")
                state = "normal"
                index += 2
            else:
                index += 1
            continue

        if state == "executable_comment":
            buffer.append(char)
            if char == "*" and nxt == "/":
                buffer.append(nxt)
                state = "normal"
                index += 2
            else:
                index += 1

    if state in {"single", "double", "backtick", "block_comment", "executable_comment"}:
        raise MigrationSQLParseError(f"unterminated SQL {state.replace('_', ' ')}")
    finish_statement()
    return tuple(statements)
