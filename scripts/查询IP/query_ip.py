country_map = {
    "US": "美国",
    "CN": "中国",
    "JP": "日本",
    "KR": "韩国",
    "GB": "英国",
}


def ipinfo_to_zh(data: dict) -> dict:
    return {
        "IP地址": data.get("ip"),
        "主机名": data.get("hostname"),
        "城市": data.get("city"),
        "州/省": data.get("region"),
        "国家": country_map.get(data.get("country"), data.get("country")),
        "经纬度": data.get("loc"),
        "运营商": data.get("org"),
        "邮编": data.get("postal"),
        "时区": data.get("timezone"),
        "是否Anycast": "是" if data.get("anycast") else "否"
    }


def get_ip_info_zh(ip: str) -> dict:
    import requests
    raw = requests.get(f"https://ipinfo.io/{ip}/json", timeout=10).json()
    return ipinfo_to_zh(raw)


for i in range(10):
    info = get_ip_info_zh("8.8.8.8")
    print(info)
