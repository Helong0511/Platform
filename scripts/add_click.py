#!/usr/bin/env python3

import requests

need_add = [
    "https://client.btfrx.online/api/v1/bft/postback?click_id=br7pyFwHYA4ga9w7acyeCdmyDzXbfe9mGMkwGNXEwz&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=br7NyKYdz74g49w7zcHzC9Grd3prznHCexza3rwdb3&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=br9XBKmepg9kjWD9PNbFergzndJxzznHCJwwpCkfX&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=br9XJdnwPB9kjWDb9DnGaJCK7dh3Rat3994wYBcWH&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=branwyDnF39zeaYRtztTJywyJyWeDKdkFApNeTNYmt&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbdEkaDHDwwaj4eB7MMtpPNXwWkXYxKdyp9xFYY&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbjGA9JgkwwajhNPtTWeFj4DRR39bPtyMjmbYkr&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbkdKYEFxwnajhcK77hfyGNwnR4FW4wAxTRPXwJ&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbktYyXFnwnajhDDWTrWxz9dWKGrBcngeK79ryk&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbkwmkEHdwnajhFd7bn4ytKttH3wmxDt3MDG4rN&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbkAHKfg3wwajtpzzzwPMCraPYaJj7gR94z7w3z&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbkPTEH4dwtajdMzCNTTX9Y4B9HKBCEFnGa9GEz&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbm9yBENtwwajzpGyNCMgfA3BBC7NyWweWt3Et3&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbmbfwBGXwwajzRYhjXwGme3dyCeKaYw7WfdKJb&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbmngMFGXwnajkmEBkJTj3Ftc3fPaEmamwftazJ&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbmwpeppKwnajkDddkrEdkWGEmpHDAmFHngbtz3&payout=3.00",
]

# 打印开始提示信息
print("=============================================")
print("PostBack 测试脚本")
print("=============================================")
print("开始测试 BFT 平台的 PostBack 回调接口...")
print(f"共测试 {len(need_add)} 个 URL")
print("=============================================")

# 需要测试的 PostBack URL 列表
# 每个 URL 包含 click_id 和 payout 参数


# 遍历测试每个 URL
for get_url in need_add:
    try:
        # 发送 GET 请求，设置 10 秒超时
        response = requests.get(get_url, timeout=10)

        # 打印测试结果
        print(f"测试 URL: {get_url}")
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        print("-" * 80)  # 分隔线
    except Exception as e:
        # 捕获异常并打印错误信息
        print(f"测试 URL {get_url} 时出错: {str(e)}")
        print("-" * 80)  # 分隔线
