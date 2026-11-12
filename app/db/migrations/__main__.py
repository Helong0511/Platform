"""迁移工具命令行入口。

validate 仅校验仓库内迁移清单和 SQL 文件，不创建数据库连接、不执行 SQL。
"""
from __future__ import annotations

import argparse
import sys

from app.db.migrations.manifest import MigrationManifestError, validate_manifest
from app.db.migrations.sql_parser import MigrationSQLParseError, split_mysql_statements


def _validate() -> int:
    migrations = validate_manifest()
    for migration in migrations:
        statements = split_mysql_statements(
            (validate_manifest.__globals__["_repository_root"]() / migration.path).read_text(
                encoding="utf-8"
            )
        )
        if not statements:
            raise MigrationManifestError(
                f"migration contains no executable statements: {migration.revision}"
            )
    print(f"Migration validation passed: {len(migrations)} revision(s); SQL syntax boundaries checked.")
    print("No database connection was opened; no SQL was executed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.db.migrations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate manifest and SQL statement boundaries (offline)")
    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            return _validate()
        except (MigrationManifestError, MigrationSQLParseError, OSError) as exc:
            print(f"Migration validation failed: {exc}", file=sys.stderr)
            return 1
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
