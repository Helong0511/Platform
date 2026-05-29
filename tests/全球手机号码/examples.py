"""
全球手机号码生成示例 — 运行: python examples.py
"""

import csv
import hashlib
import random
import sys
from pathlib import Path

# 确保同目录可导入 phone_number
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phone_number import (
    ALL_COUNTRIES,
    COMMON_COUNTRIES,
    build_country_pool,
    find_countries,
    generate_batch,
    generate_phone,
    get_country_name,
    list_countries,
)


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def demo_formats() -> None:
    section("1. 三种号码格式")
    samples = ["CN", "US", "IN", "GB", "JP"]
    for code in samples:
        name = get_country_name(code)
        intl_plus = generate_phone(code)
        intl_digits = generate_phone(code, with_plus=False)
        local = generate_phone(code, include_country_code=False)
        print(f"{name:20} +E.164: {intl_plus}")
        print(f"{'':20} 纯数字: {intl_digits}")
        print(f"{'':20} 本国号: {local}")
        print()


def demo_country_codes() -> None:
    section("2. 国家名三种写法")
    for raw in ["China", "CN", "CHN"]:
        name = get_country_name(raw)
        print(f"  {raw:8} -> {name:20} {generate_phone(raw)}")


def demo_narrow_pool() -> None:
    section("3. 缩小国家范围")
    print("指定一国:", generate_phone("IN"))
    print("常用池:  ", generate_phone(pool="common"))
    print("仅亚洲:  ", generate_phone(region="asia"))
    print("自定义:  ", generate_phone(countries=["US", "MX", "CA"]))
    print(f"常用池共 {len(build_country_pool(pool='common'))} 国")


def demo_search() -> None:
    section("4. 搜索国家")
    for kw in ["united", "+86", "saudi", "korea"]:
        print(f"  find_countries('{kw}'): {find_countries(kw)}")


def demo_batch() -> None:
    section("5. 批量生成")
    print("美国 5 个:", generate_batch(5, "US"))
    print("常用池 5 个:", generate_batch(5, pool="common", with_plus=False))
    print("东南亚 5 个:", generate_batch(5, countries=["ID", "PH", "VN", "TH", "MY"]))


def demo_fb_hash() -> None:
    section("6. Facebook 像素 ph 哈希示例")

    def hash_phone(ph: str) -> str:
        normalized = ph.replace("+", "").replace(" ", "").replace("-", "").strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    for code in ["US", "CN", "GB"]:
        ph = generate_phone(code, with_plus=False)
        print(f"  {code}: {ph}")
        print(f"       sha256: {hash_phone(ph)[:32]}...")


def demo_weighted() -> None:
    section("7. 按权重随机国家")
    weighted = [("US", 50), ("IN", 30), ("ID", 20)]
    codes, weights = zip(*weighted)
    counts = {c: 0 for c in codes}
    for _ in range(100):
        code = random.choices(codes, weights=weights, k=1)[0]
        counts[code] += 1
    print("  100 次抽样分布:", counts)


def demo_export_csv() -> None:
    section("8. 导出 CSV（前 20 条）")
    out = Path(__file__).parent / "test_phones_sample.csv"
    rows = []
    for _ in range(20):
        country = random.choice(build_country_pool(pool="common"))
        cfg = ALL_COUNTRIES[country]
        rows.append({
            "country": country,
            "alpha2": cfg["alpha2"],
            "dial_code": cfg["code"],
            "phone_e164": generate_phone(country, with_plus=False),
            "phone_local": generate_phone(country, include_country_code=False),
        })
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  已写入: {out}")
    for row in rows[:3]:
        print(f"  {row}")


def demo_stats() -> None:
    section("9. 库统计")
    print(f"  全部国家: {len(ALL_COUNTRIES)}")
    print(f"  常用国家: {len(COMMON_COUNTRIES)}（池内有效 {len(build_country_pool(pool='common'))}）")
    for region in ["africa", "asia", "europe", "north_america"]:
        print(f"  {region:15}: {len(list_countries(region))} 国")


def main() -> None:
    print("全球手机号码生成 — 示例演示")
    demo_formats()
    demo_country_codes()
    demo_narrow_pool()
    demo_search()
    demo_batch()
    demo_fb_hash()
    demo_weighted()
    demo_export_csv()
    demo_stats()
    print("\n完成。修改 examples.py 可继续加自己的业务示例。")


if __name__ == "__main__":
    main()
