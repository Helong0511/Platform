"""
智索（Zhisuo）渠道 API 联调脚本。

按 clientId + key 签名，请求 channeldaily / channelcountry / channelunit 等报表接口。
"""
import hashlib
import time

import requests

url = "https://ch.tecnee.xyz"

day_report = "/api/channeldaily"
country = "/api/channelcountry"
unit = "/api/channelunit"
country_and_unit = "/api/channeldata"  # 国家+广告单元交叉

## 替换后的参数
# clientId = 'zhisuo24'                              # 客户ID（替换）
# key = '913453ad411f016cf4c3899bc1177e9d'           # 私钥（替换）


clientId = 'KE11'  # 客户ID（替换）
key = 'cded7587a3b1aad269b9c9f5248f8b7e'  # 私钥（替换）

# start_date = date.today().isoformat()              # 当前日期，例如 '2026-05-29'
# end_date = date.today().isoformat()                # 结束日期（可根据需要调整）

start_date = '2026-07-08'
end_date = '2026-07-08'

timestamp = int(time.time() * 1000)  # 当前13位毫秒时间戳
page = 1
limit = 5000

# 构建参数字典（key 在排序前添加）
params = {
    'clientId': clientId,
    'start_date': start_date,
    'end_date': end_date,
    'timestamp': timestamp,
    'limit': limit,
    'page': page,
    'key': key
}

# 按 ASCII 码排序（参数名排序）
sorted_params = sorted(params.items())

# 拼接查询字符串
query_parts = [f"{k}={v}" for k, v in sorted_params]
query = '&'.join(query_parts)

# 生成签名（MD5，输出小写）
sign = hashlib.md5(query.encode('utf-8')).hexdigest()
del params['key']
params['sign'] = sign

need = [
    'freegame.rueik.top',
    'freegame02.rueik.top',
    'freegame03.rueik.top',
    'freegame35.rueik.top',
    'freegame36.rueik.top'
]

# 日报表
# response = requests.get(url + day_report, params=params).json()
# print(response)
# data = response.get('data', []).get('list', [])
# for item in data:
#     if item.get('domain_name','') in need:
#         print(item)

# 广告单元
# response = requests.get(url + unit, params=params).json()
# print(response)
# data = response.get('data', []).get('list', [])
# for item in data:
#     if item.get('domain_name', '') in need:
#         print(item)

# 国家数据
response = requests.get(url + country, params=params).json()
data = response.get('data', []).get('list', [])
for item in data:
    print(item)
    # if item.get('domain_name', '') in need:
    #     print(item)
