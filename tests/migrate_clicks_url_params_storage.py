"""
将 clicks / clicks_archive 表中旧版标量形态的 url_params 迁移为 dict[str, list[str]]。

大数据量建议流程:
  1) 先估算:  python3 tests/migrate_clicks_url_params_storage.py --estimate
  2) 预览:    python3 tests/migrate_clicks_url_params_storage.py --dry-run --max-batches 5
  3) 分批执行（可断点续跑）:
     python3 tests/migrate_clicks_url_params_storage.py --apply --table clicks \\
       --batch-size 1000 --sleep-ms 200 --max-rows 50000
     # 记下输出的 last_id，下一批:
     python3 tests/migrate_clicks_url_params_storage.py --apply --table clicks \\
       --start-id 123456 --batch-size 1000 --sleep-ms 200

  不带 --apply 时等同于 --dry-run（默认静默，仅汇总；加 --verbose 看样例）。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.url.url_params_util import canonicalize_url_params_json_text

ALLOWED_TABLES = ("clicks", "clicks_archive")


async def _count_nonempty(table: str) -> int:
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            text(
                f"""
                SELECT COUNT(*) AS c FROM `{table}`
                WHERE url_params IS NOT NULL AND TRIM(url_params) != ''
                """
            )
        )
        return int(row.scalar() or 0)


async def _estimate_table(table: str, *, sample_size: int) -> tuple[int, int, int]:
    """返回 (非空总数, 抽样条数, 抽样中需迁移条数)。"""
    total = await _count_nonempty(table)
    if total == 0 or sample_size <= 0:
        return total, 0, 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                f"""
                SELECT id, url_params
                FROM `{table}`
                WHERE url_params IS NOT NULL AND TRIM(url_params) != ''
                ORDER BY id
                LIMIT :sample_size
                """
            ),
            {"sample_size": sample_size},
        )
        rows = result.fetchall()

    need = sum(
        1 for _, up in rows if canonicalize_url_params_json_text(up) is not None
    )
    return total, len(rows), need


async def _migrate_table(
    table: str,
    *,
    dry_run: bool,
    batch_size: int,
    start_id: int,
    end_id: int | None,
    max_rows: int | None,
    max_batches: int | None,
    sleep_ms: int,
    verbose: bool,
    sample_limit: int,
) -> tuple[int, int, int]:
    """
    返回 (scanned, updated, last_id)。
    last_id 可用于 --start-id 断点续跑。
    """
    scanned = 0
    updated = 0
    last_id = start_id
    batches = 0
    dry_run_samples = 0

    async with AsyncSessionLocal() as session:
        while True:
            if max_batches is not None and batches >= max_batches:
                break
            if max_rows is not None and scanned >= max_rows:
                break

            limit = batch_size
            if max_rows is not None:
                limit = min(limit, max_rows - scanned)

            params: dict = {
                "last_id": last_id,
                "batch_size": limit,
            }
            end_clause = ""
            if end_id is not None:
                end_clause = " AND id <= :end_id"
                params["end_id"] = end_id

            result = await session.execute(
                text(
                    f"""
                    SELECT id, url_params
                    FROM `{table}`
                    WHERE id > :last_id
                      AND url_params IS NOT NULL
                      AND TRIM(url_params) != ''
                      {end_clause}
                    ORDER BY id
                    LIMIT :batch_size
                    """
                ),
                params,
            )
            rows = result.fetchall()
            if not rows:
                break

            batches += 1
            batch_updated = 0

            for row_id, url_params in rows:
                scanned += 1
                last_id = int(row_id)
                new_text = canonicalize_url_params_json_text(url_params)
                if new_text is None:
                    continue
                updated += 1
                batch_updated += 1
                if dry_run:
                    if verbose and dry_run_samples < sample_limit:
                        print(
                            f"[dry-run] {table} id={row_id} "
                            f"len {len(url_params)} -> {len(new_text)}"
                        )
                        dry_run_samples += 1
                else:
                    await session.execute(
                        text(f"UPDATE `{table}` SET url_params = :up WHERE id = :id"),
                        {"up": new_text, "id": row_id},
                    )

            if not dry_run:
                await session.commit()
                print(
                    f"[apply] {table} batch={batches} "
                    f"last_id={last_id} batch_updated={batch_updated} "
                    f"total_scanned={scanned} total_updated={updated}"
                )
            elif batches % 20 == 0 or not rows:
                print(
                    f"[dry-run] {table} progress last_id={last_id} "
                    f"scanned={scanned} need_update={updated}"
                )

            if sleep_ms > 0 and not dry_run:
                await asyncio.sleep(sleep_ms / 1000.0)

    return scanned, updated, last_id


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="迁移 clicks.url_params 存库形态（支持大数据量分批/断点）"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览（默认；静默汇总，加 --verbose 看样例）",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="实际写入数据库",
    )
    mode_group.add_argument(
        "--estimate",
        action="store_true",
        help="仅统计非空 url_params 总量与抽样需迁移比例（不写库）",
    )
    parser.add_argument(
        "--table",
        choices=["clicks", "clicks_archive", "both"],
        default="both",
        help="要迁移的表",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="每批 SELECT 条数（apply 建议 500~2000）",
    )
    parser.add_argument(
        "--start-id",
        type=int,
        default=0,
        help="从该 id 之后继续（断点续跑，用上一批输出的 last_id）",
    )
    parser.add_argument(
        "--end-id",
        type=int,
        default=None,
        help="只处理 id <= end-id 的记录（可选，用于分段）",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="本次最多扫描条数（分批多次执行时用）",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="本次最多批次数（dry-run 快速抽样时用）",
    )
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=0,
        help="每批 commit 后休眠毫秒数，降低 DB 压力（apply 时建议 100~500）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="dry-run 时打印前 N 条需迁移样例（见 --sample-limit）",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="--verbose 时最多打印几条样例",
    )
    parser.add_argument(
        "--estimate-sample",
        type=int,
        default=5000,
        help="--estimate 时抽样条数，用于估算需迁移比例",
    )
    args = parser.parse_args()

    tables = list(ALLOWED_TABLES) if args.table == "both" else [args.table]

    if args.estimate:
        print(f"估算模式, 表: {tables}, 抽样={args.estimate_sample}")
        for table in tables:
            total, sampled, need = await _estimate_table(
                table, sample_size=args.estimate_sample
            )
            ratio = (need / sampled * 100) if sampled else 0.0
            est_need = int(total * need / sampled) if sampled else 0
            print(
                f"{table}: 非空 url_params={total:,} 条, "
                f"抽样 {sampled:,} 条中需迁移 {need:,} 条 ({ratio:.1f}%), "
                f"估算全表需迁移约 {est_need:,} 条"
            )
        return

    dry_run = not args.apply
    mode = "dry-run" if dry_run else "APPLY"
    print(
        f"模式: {mode}, 表: {tables}, batch={args.batch_size}, "
        f"start_id={args.start_id}, end_id={args.end_id}, "
        f"max_rows={args.max_rows}, max_batches={args.max_batches}, "
        f"sleep_ms={args.sleep_ms}"
    )

    total_scanned = 0
    total_updated = 0
    for table in tables:
        scanned, updated, last_id = await _migrate_table(
            table,
            dry_run=dry_run,
            batch_size=args.batch_size,
            start_id=args.start_id,
            end_id=args.end_id,
            max_rows=args.max_rows,
            max_batches=args.max_batches,
            sleep_ms=args.sleep_ms if args.apply else 0,
            verbose=args.verbose,
            sample_limit=args.sample_limit,
        )
        print(f"{table}: 扫描 {scanned:,} 条, 需更新 {updated:,} 条, last_id={last_id}")
        total_scanned += scanned
        total_updated += updated
        if args.apply and updated < scanned:
            print(
                f"  续跑示例: python3 tests/migrate_clicks_url_params_storage.py "
                f"--apply --table {table} --start-id {last_id} "
                f"--batch-size {args.batch_size} --sleep-ms {args.sleep_ms}"
            )

    print(f"合计: 扫描 {total_scanned:,}, 需更新 {total_updated:,}")
    if dry_run and total_updated:
        print(
            "确认后分批执行:\n"
            "  python3 tests/migrate_clicks_url_params_storage.py --apply "
            f"--table clicks --batch-size 1000 --sleep-ms 200 --max-rows 50000"
        )
    elif args.apply and total_updated == 0 and total_scanned > 0:
        print("本段已无需要迁移的记录（可能已是标准形态）。")


if __name__ == "__main__":
    asyncio.run(main())
