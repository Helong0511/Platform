"""诊断 TBSJ 2026-06-13 入库与列表可见性。"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TARGET_DATE = "2026-06-13"


def parse_db_url(url: str) -> dict:
    m = re.match(r"mysql\+aiomysql://([^:]+):([^@]+)@([^:/]+):(\d+)/([^?]+)", url)
    if not m:
        raise ValueError(f"无法解析 DATABASE_URL: {url}")
    user, pwd, host, port, db = m.groups()
    return dict(host=host, port=int(port), user=user, password=pwd, database=db, charset="utf8mb4")


def main() -> None:
    conn = pymysql.connect(**parse_db_url(os.environ["DATABASE_URL"]))
    cur = conn.cursor()

    print(f"=== ad_data 按产品 ({TARGET_DATE}) ===")
    cur.execute(
        """
        SELECT p.name, c.company_name, COUNT(a.id)
        FROM ad_data a
        JOIN products p ON a.product_id = p.id
        JOIN clients c ON p.client_id = c.id
        WHERE DATE(a.date) = %s
        GROUP BY p.name, c.company_name
        ORDER BY COUNT(a.id) DESC
        """,
        (TARGET_DATE,),
    )
    rows = cur.fetchall()
    total = sum(r[2] for r in rows)
    for name, client, cnt in rows:
        print(f"  {cnt:4d}  {client}  |  {name}")
    print(f"合计: {total}")

    print("\n=== 详情报表 JOIN（含 ProductAssignment）可见条数 ===")
    cur.execute(
        """
        SELECT p.name, c.company_name, COUNT(a.id)
        FROM ad_data a
        JOIN products p ON a.product_id = p.id
        JOIN product_assignments pa ON pa.product_id = p.id
            AND a.date >= pa.start_date
            AND (pa.end_date IS NULL OR a.date < DATE_ADD(pa.end_date, INTERVAL 1 DAY))
        JOIN clients c ON pa.client_id = c.id
        WHERE DATE(a.date) = %s AND p.is_active = 1
        GROUP BY p.name, c.company_name
        ORDER BY COUNT(a.id) DESC
        """,
        (TARGET_DATE,),
    )
    vis_rows = cur.fetchall()
    vis_total = sum(r[2] for r in vis_rows)
    for name, client, cnt in vis_rows:
        print(f"  {cnt:4d}  {client}  |  {name}")
    print(f"可见合计: {vis_total}")

    print("\n=== 相关 products ===")
    cur.execute(
        """
        SELECT p.id, p.name, p.is_active, c.company_name
        FROM products p
        JOIN clients c ON p.client_id = c.id
        WHERE p.name LIKE '%ibobin%' OR p.name LIKE '%infompost%' OR p.name LIKE '%pethouseinfo%'
        ORDER BY p.name
        """
    )
    for pid, name, active, client in cur.fetchall():
        print(f"  id={pid} active={active} client={client} | {name}")

    print("\n=== game2 产品分配 ===")
    cur.execute(
        """
        SELECT pa.id, p.name, c.company_name, pa.start_date, pa.end_date
        FROM product_assignments pa
        JOIN products p ON pa.product_id = p.id
        JOIN clients c ON pa.client_id = c.id
        WHERE p.name LIKE '%game2.ibobin%'
        ORDER BY pa.start_date
        """
    )
    for row in cur.fetchall():
        print(" ", row)

    print("\n=== 客户 Huying / 互赢 ===")
    cur.execute(
        """
        SELECT id, company_name FROM clients
        WHERE company_name LIKE %s OR company_name LIKE %s
        """,
        ("%Huying%", "%互赢%"),
    )
    for row in cur.fetchall():
        print(" ", row)

    print("\n=== 最近 ad_data 日期 ===")
    cur.execute(
        "SELECT DATE(date) d, COUNT(*) FROM ad_data GROUP BY DATE(date) ORDER BY d DESC LIMIT 10"
    )
    for row in cur.fetchall():
        print(" ", row)

    print(f"\n=== ad_data 2026-06-12 按产品 ===")
    cur.execute(
        """
        SELECT p.name, c.company_name, COUNT(a.id)
        FROM ad_data a
        JOIN products p ON a.product_id = p.id
        JOIN clients c ON p.client_id = c.id
        WHERE DATE(a.date) = %s
        GROUP BY p.name, c.company_name
        ORDER BY COUNT(a.id) DESC
        """,
        ("2026-06-12",),
    )
    for row in cur.fetchall():
        print(f"  {row[2]:4d}  {row[1]}  |  {row[0]}")

    print("\n=== ibobin / game 产品 ===")
    cur.execute(
        "SELECT id, name, is_active FROM products WHERE name LIKE %s OR name LIKE %s",
        ("%ibobin%", "%game%"),
    )
    for row in cur.fetchall():
        print(" ", row)

    print("\n=== yangyangdeyi 定时任务 ===")
    cur.execute("SHOW COLUMNS FROM scheduled_tasks")
    cols = [r[0] for r in cur.fetchall()]
    print("columns:", cols)
    if "last_result" in cols:
        time_col = "last_run_time" if "last_run_time" in cols else (
            "last_executed_at" if "last_executed_at" in cols else None
        )
        sel = f"task_name, {time_col}, LEFT(last_result, 200)" if time_col else "task_name, last_result"
        cur.execute(f"SELECT {sel} FROM scheduled_tasks WHERE task_name LIKE %s", ("%yangyangdeyi%",))
        for row in cur.fetchall():
            print(" ", row)

    conn.close()


if __name__ == "__main__":
    main()
