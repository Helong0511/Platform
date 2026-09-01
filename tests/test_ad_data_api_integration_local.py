"""
前后端联调冒烟：登录、daily-summary 冷/热路径、筛选项、dashboard。

用法（需本地 API 8960 已启动）：
    python tests/test_ad_data_api_integration_local.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

API = os.getenv("TEST_API_BASE", "http://127.0.0.1:8960")
ADMIN_USER = os.getenv("FIRST_SUPERUSER", "admin")
ADMIN_PASS = os.getenv("FIRST_SUPERUSER_PASSWORD", "yinghexinxi123")
CLIENT_USER = "Dellimobi"
CLIENT_PASS = "Dellimobi123456"


class FailCollector:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.notes: list[str] = []

    def ok(self, msg: str) -> None:
        print(f"  OK  {msg}")

    def fail(self, msg: str) -> None:
        print(f"  FAIL {msg}")
        self.errors.append(msg)

    def note(self, msg: str) -> None:
        print(f"  ..  {msg}")
        self.notes.append(msg)


def login(client: httpx.Client, username: str, password: str) -> dict | None:
    r = client.post(
        f"{API}/api/v1/auth/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if r.status_code != 200:
        return None
    token = r.cookies.get("access_token")
    if not token:
        body = r.json()
        token = body.get("data", {}).get("access_token") or body.get("access_token")
    if not token:
        return None
    client.headers["Authorization"] = f"Bearer {token}"
    csrf = r.headers.get("X-CSRF-Token") or client.cookies.get("csrf_token")
    if csrf:
        client.headers["X-CSRF-Token"] = csrf
    return r.json()


def main() -> int:
    fc = FailCollector()
    print(f"=== 广告数据 API 联调 ({API}) ===")

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        # health
        try:
            hr = client.get(f"{API}/api/v1/health")
            if hr.status_code == 200 and hr.json().get("status") == "ok":
                fc.ok("health")
            else:
                fc.fail(f"health 异常: {hr.status_code} {hr.text[:200]}")
        except Exception as exc:
            fc.fail(f"health 不可达: {exc}")
            print("\n请先启动后端: python -m app.main")
            return 1

        # admin login
        if not login(client, ADMIN_USER, ADMIN_PASS):
            fc.fail("管理员登录失败")
            return 1
        fc.ok("管理员登录")

        me = client.get(f"{API}/api/v1/users/me")
        if me.status_code == 200:
            role = me.json().get("data", {}).get("role") or me.json().get("role")
            fc.ok(f"/users/me role={role}")
        else:
            fc.fail(f"/users/me {me.status_code}")

        params = {
            "page": 1,
            "page_size": 20,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "dimension": "country",
        }

        t0 = time.perf_counter()
        r1 = client.get(f"{API}/api/v1/ad-data/daily-summary", params=params)
        cold_ms = (time.perf_counter() - t0) * 1000
        if r1.status_code != 200:
            fc.fail(f"daily-summary 首次 {r1.status_code}: {r1.text[:300]}")
        else:
            body1 = r1.json()
            items1 = body1.get("data") or []
            if isinstance(items1, dict):
                items1 = items1.get("items") or items1.get("list") or []
            total1 = body1.get("total")
            grand1 = body1.get("grand_total")
            fc.ok(
                f"daily-summary 冷路径 {cold_ms:.0f}ms total={total1} items={len(items1)} "
                f"grand={'有' if grand1 else '无'}"
            )
            if not items1:
                fc.fail("daily-summary 返回空列表")
            if grand1 is None:
                fc.fail("daily-summary 缺少 grand_total")

        t1 = time.perf_counter()
        r2 = client.get(f"{API}/api/v1/ad-data/daily-summary", params=params)
        warm_ms = (time.perf_counter() - t1) * 1000
        if r2.status_code != 200:
            fc.fail(f"daily-summary 二次 {r2.status_code}")
        else:
            body2 = r2.json()
            total2 = body2.get("total")
            fc.ok(f"daily-summary 缓存命中 {warm_ms:.0f}ms total={total2}")
            if total1 != total2:
                fc.fail(f"daily-summary 冷/热 total 不一致: {total1} vs {total2}")
            if warm_ms > 3000:
                fc.note(f"缓存命中仍偏慢 ({warm_ms:.0f}ms)，可能 Redis 未连上走进程内缓存")

        pw = client.get(
            f"{API}/api/v1/ad-data/products-with-data",
            params={"start_date": "2026-08-01", "end_date": "2026-08-31"},
        )
        if pw.status_code == 200:
            pdata = pw.json().get("data") or []
            fc.ok(f"products-with-data count={len(pdata)}")
        else:
            fc.fail(f"products-with-data {pw.status_code}")

        cw = client.get(
            f"{API}/api/v1/ad-data/clients-with-data",
            params={"start_date": "2026-08-01", "end_date": "2026-08-31"},
        )
        if cw.status_code == 200:
            fc.ok(f"clients-with-data count={len(cw.json().get('data') or [])}")
        else:
            fc.fail(f"clients-with-data {cw.status_code}")

        dash = client.get(f"{API}/api/v1/dashboard/stats", params={"period": "week"})
        if dash.status_code == 200:
            fc.ok("dashboard/stats")
        else:
            fc.fail(f"dashboard/stats {dash.status_code}")

        # 客户角色
        client2 = httpx.Client(timeout=60.0, follow_redirects=True)
        try:
            if not login(client2, CLIENT_USER, CLIENT_PASS):
                fc.fail("客户 Dellimobi 登录失败")
            else:
                fc.ok("客户 Dellimobi 登录")
                cr = client2.get(f"{API}/api/v1/ad-data/daily-summary", params={**params, "page_size": 5})
                if cr.status_code == 200:
                    cbody = cr.json()
                    citems = cbody.get("data") or []
                    if isinstance(citems, dict):
                        citems = citems.get("items") or citems.get("list") or []
                    fc.ok(f"客户 daily-summary items={len(citems)}")
                    for it in citems[:3]:
                        blob = str(it)
                        if any(x in blob for x in ("扣减后", "减扣后", "(扣)")):
                            fc.fail("客户 daily-summary 含扣减暴露文案")
                            break
                else:
                    fc.fail(f"客户 daily-summary {cr.status_code}")
        finally:
            client2.close()

    print("\n=== 汇总 ===")
    if fc.errors:
        for e in fc.errors:
            print(f"  x {e}")
        return 1
    print("  全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
