"""客户 1028：查今日是否有 clubx/cluba.vershnik.com（正式 client_data）。"""
import hashlib
import hmac
import json
import time
import urllib.request
from datetime import date

# —— 配置 ——
URL = "https://client.btfrx.online/api/v1/client_data"  # 正式客户数据接口
CLIENT_ID = 1028
SECRET_KEY = "65006a7c-1083-41b4-a255-3e9904eea930"  # 客户密钥（参与签名，勿泄露）
TARGETS = ("puzzle25.editing.web.id", "puzzle26.editing.web.id")  # 要查找的产品名
SAMPLE_N = 5  # 每个产品打印几条示例
TODAY = date.today().isoformat()  # 查询日期，也可写成 '2026-08-10'


def fetch(page: int, page_size: int = 5000) -> dict:
    """请求一页数据：拼参数 → 签名 → POST。"""
    req_time = int(time.time())  # 秒级时间戳，与服务器差不能太大

    # 参与签名的参数（空值不参与；键名按字母序拼接）
    params = {
        "client_id": str(CLIENT_ID),
        "data_type": "all",
        "dimension": "ad_unit_country",
        "end_date": TODAY,
        "page": str(page),
        "page_size": str(page_size),
        "req_time": str(req_time),
        "start_date": TODAY,
    }
    # 签名串：k=v&...&key=密钥，再 HMAC-SHA256
    sign_str = "&".join(f"{k}={params[k]}" for k in sorted(params)) + f"&key={SECRET_KEY}"
    sign = hmac.new(SECRET_KEY.encode(), sign_str.encode(), hashlib.sha256).hexdigest()

    # 实际请求体（类型保持接口要求：数字用 int）
    body = {
        "client_id": CLIENT_ID,
        "req_time": req_time,
        "sign": sign,
        "data_type": "all",
        "dimension": "ad_unit_country",
        "start_date": TODAY,
        "end_date": TODAY,
        "page": page,
        "page_size": page_size,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    # 每个目标产品各自收集示例
    samples = {name: [] for name in TARGETS}

    # 先拉第 1 页，拿到总数、总页数
    first = fetch(1)
    assert first.get("code") == 200, first
    total = first.get("total")
    pages = int(first.get("total_pages") or 1)
    print(f"API获取日期={TODAY} 共有={total}条记录 页数={pages}")

    def collect(items):
        """从本页挑出目标产品；凑满 SAMPLE_N 条返回 True（可提前结束）。"""
        for x in items:
            name = (x.get("product_name") or "").strip()
            if name in samples and len(samples[name]) < SAMPLE_N:
                samples[name].append(x)
        return all(len(samples[n]) >= SAMPLE_N for n in TARGETS)

    # 第 1 页先收集；不够再翻页，够了就停（避免全量拉取过慢）
    done = collect(first.get("data") or [])
    for p in range(2, pages + 1):
        if done:
            break
        done = collect(fetch(p).get("data") or [])

    # 打印每个产品是否找到，以及示例数据
    for name in TARGETS:
        rows = samples[name]
        print(f"\n产品名称：{name}: 是否有记录={bool(rows)} 样例数={len(rows)}")
        for i, row in enumerate(rows, 1):
            print(f"  sample[{i}]={json.dumps(row, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
