"""
本地 daily-summary 性能冒烟（只连 127.0.0.1 MySQL + Redis）。

用法（项目根目录，需本地 API 或直连 DB）：
    python tests/test_daily_summary_perf_local.py
    python tests/test_daily_summary_perf_local.py --skip-cache-second
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlparse

import pymysql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))


def _assert_local_db():
    raw = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI") or ""
    raw = raw.replace("mysql+aiomysql://", "mysql://").replace("mysql+pymysql://", "mysql://")
    parsed = urlparse(raw)
    if parsed.hostname not in ("127.0.0.1", "localhost", None):
        raise SystemExit(f"拒绝连接非本机库: {parsed.hostname}")


async def _run_daily_summary(skip_cache_second: bool) -> None:
    from app.core.database import AsyncSessionLocal
    from app.models.models import User
    from app.services.ad_data.queries.daily_summary_query import DailySummaryQuery
    from sqlalchemy import select

    _assert_local_db()

    async with AsyncSessionLocal() as db:
        admin = (
            await db.execute(select(User).where(User.username == "admin").limit(1))
        ).scalar_one_or_none()
        if admin is None:
            raise SystemExit("本地库缺少 admin 用户，请先初始化")

        q = DailySummaryQuery(db)
        kwargs = dict(
            current_user=admin,
            page=1,
            page_size=20,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            dimension="country",
            skip_cache=True,
        )

        t0 = time.perf_counter()
        items, total, grand = await q.fetch(**kwargs)
        cold_ms = (time.perf_counter() - t0) * 1000
        print(f"冷路径 skip_cache=True: {cold_ms:.0f}ms, total={total}, items={len(items)}")

        if skip_cache_second:
            return

        kwargs["skip_cache"] = False
        t1 = time.perf_counter()
        await q.fetch(**kwargs)
        first_ms = (time.perf_counter() - t1) * 1000

        t2 = time.perf_counter()
        await q.fetch(**kwargs)
        warm_ms = (time.perf_counter() - t2) * 1000
        print(f"缓存写入后首次: {first_ms:.0f}ms")
        print(f"缓存命中二次: {warm_ms:.0f}ms")
        if warm_ms > 2000:
            print("WARN: 缓存命中仍 >2s，请检查 Redis 或索引是否已应用")


def _print_index_status() -> None:
    raw = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI") or ""
    raw = raw.replace("mysql+aiomysql://", "mysql://").replace("mysql+pymysql://", "mysql://")
    parsed = urlparse(raw)
    if parsed.hostname not in ("127.0.0.1", "localhost", None):
        return
    conn = pymysql.connect(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=(parsed.path or "/platform").lstrip("/").split("?")[0],
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT index_name FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = 'ad_data'
                  AND index_name IN (
                    'idx_ad_data_date_id',
                    'idx_ad_data_date_country',
                    'idx_ad_data_date_ad_unit',
                    'idx_ad_data_date_source'
                  )
                GROUP BY index_name
                ORDER BY index_name
                """
            )
            names = [r[0] for r in cur.fetchall()]
            print("已存在性能索引:", ", ".join(names) or "(无，请运行 tests/apply_ad_data_optimize.py)")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-cache-second", action="store_true")
    args = parser.parse_args()
    _print_index_status()
    asyncio.run(_run_daily_summary(skip_cache_second=args.skip_cache_second))


if __name__ == "__main__":
    main()
