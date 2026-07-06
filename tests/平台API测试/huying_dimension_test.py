"""
Huying 客户 API 维度组合详细测试（本地/线上均可，读取 Huying.py 配置）。

用法（项目根目录）：
    python tests/平台API测试/huying_dimension_test.py
"""
from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HUYING_PATH = Path(__file__).resolve().parent / "Huying.py"

spec = importlib.util.spec_from_file_location("huying", HUYING_PATH)
huying = importlib.util.module_from_spec(spec)
spec.loader.exec_module(huying)

START_DATE = "2026-07-01"
END_DATE = "2026-07-06"
TARGET_PRODUCTS = {"food.fanquer.com", "design.fanquer.com"}


def _has_val(s: str | None) -> bool:
    return bool((s or "").strip())


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


def classify_row(country_code: str, ad_unit: str) -> str:
    hc, ha = _has_val(country_code), _has_val(ad_unit)
    if hc and not ha:
        return "country_only"
    if not hc and ha:
        return "ad_unit_only"
    if hc and ha:
        return "cross"
    return "plain"


def shape_violations(dimension: str | None, rows: list[dict]) -> list[str]:
    """检查 all 模式下各行是否符合 dimension 字段形态规则。"""
    violations: list[str] = []
    for i, row in enumerate(rows[:50]):  # 抽样前 50 条
        cc = row.get("country_code") or ""
        au = row.get("ad_unit") or ""
        kind = classify_row(cc, au)
        if dimension == "country" and kind != "country_only":
            violations.append(f"#{i} {row.get('product_name')} kind={kind} cc={cc!r} au={au!r}")
        elif dimension == "ad_unit" and kind != "ad_unit_only":
            violations.append(f"#{i} {row.get('product_name')} kind={kind} cc={cc!r} au={au!r}")
        elif dimension == "ad_unit_country" and kind != "cross":
            violations.append(f"#{i} {row.get('product_name')} kind={kind} cc={cc!r} au={au!r}")
    return violations


def run_case(data_type: str, dimension: str | None) -> dict:
    label = f"data_type={data_type!r:4} dimension={dimension!r}"
    _safe_print(f"\n{'='*60}")
    _safe_print(label)
    _safe_print("=" * 60)

    result = huying.get_all_ad_data(
        data_type=data_type,
        start_date=START_DATE,
        end_date=END_DATE,
        dimension=dimension,
        page_size=5000,
    )
    code = result.get("code")
    if code != 200:
        _safe_print(f"  FAIL code={code} msg={result.get('message')}")
        return {"label": label, "ok": False, "code": code}

    rows = result.get("data") or []
    total = result.get("total", len(rows))
    products = {r.get("product_name", "") for r in rows}
    target_hit = TARGET_PRODUCTS & products

    kinds = Counter(classify_row(r.get("country_code"), r.get("ad_unit")) for r in rows)
    sample = rows[0] if rows else None

    _safe_print(f"  code=200 total={total} fetched={len(rows)}")
    _safe_print(f"  行形态分布: {dict(kinds)}")
    _safe_print(f"  fanquer命中: {sorted(target_hit) or '无'}")

    if sample:
        au = (sample.get("ad_unit") or "")[:40]
        _safe_print(
            f"  样例: product={sample.get('product_name')} "
            f"date={sample.get('date')} cc={sample.get('country_code')!r} "
            f"au={au!r} revenue={sample.get('revenue')}"
        )

    shape_ok = True
    if data_type == "all" and dimension in ("country", "ad_unit", "ad_unit_country"):
        bad = shape_violations(dimension, rows)
        if bad:
            shape_ok = False
            _safe_print(f"  形态违规(前几条): {bad[:5]}")
        else:
            _safe_print("  形态校验: PASS（抽样前50条）")

    return {
        "label": label,
        "ok": True,
        "code": code,
        "total": total,
        "kinds": dict(kinds),
        "target_hit": target_hit,
        "shape_ok": shape_ok,
    }


def main() -> int:
    _safe_print(f"BASE_URL = {huying.BASE_URL}")
    _safe_print(f"CLIENT_ID = {huying.CLIENT_ID}")
    _safe_print(f"日期范围 = {START_DATE} ~ {END_DATE}")

    # 产品列表
    prod = huying.get_products()
    if prod.get("code") == 200:
        names = [p.get("name") for p in (prod.get("data") or [])]
        _safe_print(f"产品数: {len(names)}")
        for t in sorted(TARGET_PRODUCTS):
            _safe_print(f"  目标产品 {t}: {'在列表中' if t in names else '不在列表中'}")
    else:
        _safe_print(f"产品列表失败: {prod}")

    cases = [
        ("all", None),
        ("all", "country"),
        ("all", "ad_unit"),
        ("all", "ad_unit_country"),
        ("day", None),
        ("day", "country"),
        ("day", "ad_unit"),
        ("day", "ad_unit_country"),
    ]

    results = [run_case(dt, dim) for dt, dim in cases]

    _safe_print(f"\n{'='*60}")
    _safe_print("汇总")
    _safe_print("=" * 60)
    _safe_print(f"{'组合':<45} {'总数':>6} {'fanquer':>8} {'形态':>6}")
    _safe_print("-" * 70)
    for r in results:
        if not r.get("ok"):
            _safe_print(f"{r['label']:<45} {'ERR':>6}")
            continue
        fanquer = "Y" if r.get("target_hit") else "-"
        shape = "PASS" if r.get("shape_ok", True) else "FAIL"
        if not r["label"].startswith("data_type='all'"):
            shape = "-"
        _safe_print(f"{r['label']:<45} {r['total']:>6} {fanquer:>8} {shape:>6}")

    failed = [r for r in results if not r.get("ok") or r.get("shape_ok") is False]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
