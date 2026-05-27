"""
将 clicks / clicks_archive 表中旧版标量形态的 url_params 迁移为 dict[str, list[str]]。

用法（项目根目录）:
  python tests/migrate_clicks_url_params_storage.py --dry-run
  python tests/migrate_clicks_url_params_storage.py --apply
  python tests/migrate_clicks_url_params_storage.py --apply --table clicks_archive
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.url.url_params_util import canonicalize_url_params_json_text

ALLOWED_TABLES = ("clicks", "clicks_archive")


async def _migrate_table(
    table: str,
    *,
    dry_run: bool,
    batch_size: int,
) -> tuple[int, int]:
    scanned = 0
    updated = 0
    last_id = 0

    async with AsyncSessionLocal() as session:
        while True:
            result = await session.execute(
                text(
                    f"""
                    SELECT id, url_params
                    FROM `{table}`
                    WHERE id > :last_id
                      AND url_params IS NOT NULL
                      AND TRIM(url_params) != ''
                    ORDER BY id
                    LIMIT :batch_size
                    """
                ),
                {"last_id": last_id, "batch_size": batch_size},
            )
            rows = result.fetchall()
            if not rows:
                break

            for row_id, url_params in rows:
                scanned += 1
                last_id = int(row_id)
                new_text = canonicalize_url_params_json_text(url_params)
                if new_text is None:
                    continue
                updated += 1
                if dry_run:
                    print(
                        f"[dry-run] {table} id={row_id} "
                        f"len {len(url_params)} -> {len(new_text)}"
                    )
                else:
                    await session.execute(
                        text(
                            f"UPDATE `{table}` SET url_params = :up WHERE id = :id"
                        ),
                        {"up": new_text, "id": row_id},
                    )

            if not dry_run:
                await session.commit()

    return scanned, updated


async def main() -> None:
    parser = argparse.ArgumentParser(description="迁移 clicks.url_params 存库形态")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入（默认仅 dry-run）",
    )
    parser.add_argument(
        "--table",
        choices=["clicks", "clicks_archive", "both"],
        default="both",
        help="要迁移的表",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    dry_run = not args.apply

    tables = list(ALLOWED_TABLES) if args.table == "both" else [args.table]
    mode = "dry-run" if dry_run else "APPLY"
    print(f"模式: {mode}, 表: {tables}, batch={args.batch_size}")

    total_scanned = 0
    total_updated = 0
    for table in tables:
        scanned, updated = await _migrate_table(
            table, dry_run=dry_run, batch_size=args.batch_size
        )
        print(f"{table}: 扫描 {scanned} 条, 需更新 {updated} 条")
        total_scanned += scanned
        total_updated += updated

    print(f"合计: 扫描 {total_scanned}, 需更新 {total_updated}")
    if dry_run and total_updated:
        print("确认后执行: python tests/migrate_clicks_url_params_storage.py --apply")


if __name__ == "__main__":
    asyncio.run(main())
