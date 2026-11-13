"""迁移工具命令行入口。

validate 仅校验仓库内迁移清单和 SQL 文件，不创建数据库连接、不执行 SQL。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from app.db.migrations.manifest import MigrationManifestError, validate_manifest
from app.db.migrations.sql_parser import MigrationSQLParseError, split_mysql_statements


def _validate() -> int:
    migrations = validate_manifest()
    for migration in migrations:
        statements = split_mysql_statements(
            (Path(__file__).resolve().parents[3] / migration.path).read_text(
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
    subparsers.add_parser("apply", help="apply pending migrations using MIGRATION_DATABASE_URL")
    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            return _validate()
        except (MigrationManifestError, MigrationSQLParseError, OSError) as exc:
            print(f"Migration validation failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "apply":
        database_url = os.getenv("MIGRATION_DATABASE_URL", "").strip()
        if not database_url:
            print("Migration failed: MIGRATION_DATABASE_URL is required; application DSN is never used.", file=sys.stderr)
            return 2
        try:
            from app.core.config import settings
            from app.db.migrations.runner import apply_migrations

            completed = asyncio.run(
                apply_migrations(
                    database_url,
                    application_database_url=str(settings.SQLALCHEMY_DATABASE_URI),
                )
            )
            print(f"Migration apply completed: {len(completed)} revision(s)")
            for revision in completed:
                print(f"  applied {revision}")
            return 0
        except (MigrationManifestError, MigrationSQLParseError, RuntimeError, ValueError, OSError) as exc:
            print(f"Migration apply failed: {type(exc).__name__}", file=sys.stderr)
            return 1
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
