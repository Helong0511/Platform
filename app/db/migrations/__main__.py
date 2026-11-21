"""迁移工具命令行入口。

validate 仅校验仓库内迁移清单和 SQL 文件，不创建数据库连接、不执行 SQL。
systemd 部署通过 LoadCredential 注入 DSN 文件；手工/CI 环境可使用显式环境变量。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from app.db.migrations.manifest import MigrationManifestError, validate_manifest
from app.db.migrations.sql_parser import MigrationSQLParseError, split_mysql_statements


def _read_credential(credential_name: str, *environment_names: str) -> str:
    """优先读取 systemd LoadCredential 文件；存在凭据目录时禁止回退到环境变量。"""
    credentials_directory = os.getenv("CREDENTIALS_DIRECTORY", "").strip()
    if credentials_directory:
        credential_path = Path(credentials_directory) / credential_name
        try:
            return credential_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""
        except OSError as exc:
            raise RuntimeError(
                f"无法读取 systemd credential：{credential_name}"
            ) from exc

    for environment_name in environment_names:
        value = os.getenv(environment_name, "").strip()
        if value:
            return value
    return ""


def _validate() -> int:
    from app.db.migrations.runner import _validate_event_key_backfill_contract

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
        if migration.backfill_handler is not None:
            _validate_event_key_backfill_contract(migration, statements)
    print(f"Migration validation passed: {len(migrations)} revision(s); SQL syntax boundaries checked.")
    print("No database connection was opened; no SQL was executed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.db.migrations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate manifest and SQL statement boundaries (offline)")
    subparsers.add_parser("apply", help="apply pending migrations using a protected migration credential")
    subparsers.add_parser("status", help="read migration ledger status without changing schema")
    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            return _validate()
        except (MigrationManifestError, MigrationSQLParseError, RuntimeError, OSError) as exc:
            print(f"Migration validation failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "status":
        try:
            database_url = _read_credential(
                "migration-database-url", "MIGRATION_DATABASE_URL"
            )
            application_database_url = _read_credential(
                "application-database-url",
                "DATABASE_URL",
                "SQLALCHEMY_DATABASE_URI",
            )
        except RuntimeError as exc:
            print(f"Migration status failed: {exc}", file=sys.stderr)
            return 1
        if not database_url:
            print("Migration status failed: migration database credential is required.", file=sys.stderr)
            return 2
        if not application_database_url:
            print("Migration status failed: application database credential is required.", file=sys.stderr)
            return 2
        try:
            from app.db.migrations.runner import read_migration_status

            rows = asyncio.run(
                read_migration_status(
                    database_url,
                    application_database_url=application_database_url,
                )
            )
            if not rows:
                print("No migration ledger rows found; schema is not verified.")
                return 3
            print("revision | status | execution_order | started_at | applied_at | error_type")
            for row in rows:
                print(
                    f"{row['revision']} | {row['status']} | {row['execution_order']} | "
                    f"{row['started_at']} | {row['applied_at']} | {row['error_type'] or '-'}"
                )
            from app.db.migrations.ledger import validate_ledger_rows
            from app.db.migrations.manifest import validate_manifest
            from app.db.migrations.planner import plan_migrations

            root = Path(__file__).resolve().parents[3]
            manifest = validate_manifest(root)
            resumable_revisions = {
                migration.revision
                for migration in manifest
                if migration.backfill_handler is not None
            }
            try:
                applied = validate_ledger_rows(
                    rows,
                    repository_root=root,
                    migrations=manifest,
                    allow_running_revisions=resumable_revisions,
                )
            except MigrationManifestError:
                print(
                    "BLOCKED: ledger state requires manual DDL reconciliation; "
                    "automatic resume is not allowed.",
                    file=sys.stderr,
                )
                return 3

            blocked = [row for row in rows if row["status"] != "applied"]
            if blocked:
                resumable = [
                    row
                    for row in blocked
                    if row["status"] == "running"
                    and row["revision"] in resumable_revisions
                ]
                if len(blocked) == 1 and len(resumable) == 1:
                    print(
                        "RESUMABLE: one declared batch backfill is still running. "
                        "Stop all writers, then rerun 'python -m app.db.migrations apply'; "
                        "the schema is not yet verified.",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"BLOCKED: {len(blocked)} migration record(s) require manual DDL reconciliation.",
                        file=sys.stderr,
                    )
                return 3

            pending = plan_migrations(
                applied, repository_root=root, migrations=manifest
            )
            if pending:
                print(
                    "PENDING: " + ", ".join(item.revision for item in pending),
                    file=sys.stderr,
                )
                return 3
            print("Migration history is valid and current; physical application schema is not verified by this command.")
            return 0
        except (MigrationManifestError, RuntimeError, ValueError, OSError) as exc:
            print(f"Migration status failed: {type(exc).__name__}", file=sys.stderr)
            return 1

    if args.command == "apply":
        try:
            database_url = _read_credential(
                "migration-database-url", "MIGRATION_DATABASE_URL"
            )
            application_database_url = _read_credential(
                "application-database-url",
                "DATABASE_URL",
                "SQLALCHEMY_DATABASE_URI",
            )
        except RuntimeError as exc:
            print(f"Migration failed: {exc}", file=sys.stderr)
            return 1
        if not database_url:
            print("Migration failed: migration database credential is required; application DSN is never used.", file=sys.stderr)
            return 2
        if not application_database_url:
            print("Migration failed: application database credential is required.", file=sys.stderr)
            return 2
        try:
            from app.db.migrations.runner import apply_migrations

            completed = asyncio.run(
                apply_migrations(
                    database_url,
                    application_database_url=application_database_url,
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
