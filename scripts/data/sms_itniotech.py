import hashlib
import time

import requests
import json

base_url = "https://api.itniotech.com/sms"
api_key = "aeeMQsIKtWGP2pYLFHNZgCLKWIlhKUWo"
api_pwd = "rnujxXx1bDW8oPxRvEvhVfWPC9uWS1kO"
appid = "3FZYiE9x"


def create_headers():
    timestamp = int(time.time())
    s = "%s%s%s" % (api_key, api_pwd, str(timestamp))
    sign = hashlib.md5(s.encode(encoding='UTF-8')).hexdigest()
    headers = {
        'Content-Type': 'application/json;charset=utf-8',
        'Sign': sign,
        'Timestamp': str(timestamp),
        'Api-Key': api_key
    }
    return headers


headers = create_headers()

print(headers)

url = "%s/sendSms" % base_url
print(url)

# post method
body = {
    "appId": appid,
    "numbers": "+5585992330734",
    "content": "Hello!",
    "senderId": ""
}
print(body)

# rsp = requests.post(url, json=body, headers=headers)
# if rsp.status_code == 200:
#     res = json.loads(rsp.text)
#     print(res)

url = f"https://api.itniotech.com/sms/getReport?appId={appid}&msgIds=2511251751181017988"

status = requests.get(url, headers=headers)
if status.status_code == 200:
    json_data = status.json()
    print(json_data)
"""
查询
{
  'status': '0',  # 状态码
  'reason': 'success',  # 失败原因说明
  'success': '1',  # 发送成功的条数
  'fail': '0',
  'sending': '0',
  'nofound': '0',
  'array': [
    {
      'msgId': '2511251751181017988',
      'number': '5585992330734',
      'receiveTime': '2025-11-25T17:51:19+08:00',
      'status': '0',
      'statusResult': None,
      'statusReason': None,
      'mcc': 724,
      'mnc': 5,
      'pricedetail': {
        'pay': '0.01',
        'chargeCnt': 1,
        'currency': 'USD',
        'price': '0.01',
        'settleCurrency': None,
        'settlePrice': None,
        'quoteExchange': None,
        'settlePay': None
      }
    }
  ]
}
"""