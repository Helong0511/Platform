"""
通百世家（TBSJ）第三方数据 API 联调脚本。

流程：POST /token 获取 access_token → 带 Bearer 请求日报等接口。
仅用于开发环境手工验证，凭证请勿提交到版本库。
"""
import requests

url = 'https://data.tongbaishijia.com/api/thirdservice'

Headers = {'Content-Type': 'application/json;charset=utf-8'}

username = 'BOFIT1'
password = 'f8034e342a8e6070aadaee559c3c95eb'

token_post = {
    "username": username,
    "password": password
}

response = requests.post(url + '/token', data=token_post)
json_data = response.json()
access_token = json_data.get('access_token', '')

Headers['Authorization'] = f'Bearer {access_token}'

tbsj_params = {
    "page": 1,
    "limit": 1000,
    "start": '2025-11-24 00:00:00',
    "end": '2025-11-24 23:59:59'
}

response = requests.post(url + '/adunit',headers=Headers, json=tbsj_params)
print(response.json())

response = requests.post(url + '/unit_data',headers=Headers, json=tbsj_params)
print(response.json())

response = requests.post(url + '/country',headers=Headers, json=tbsj_params)
print(response.json())