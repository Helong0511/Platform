import json
import requests

from Utils.handle_md5 import get_uuid, generate_post_sign

Merchant_ID = 'lucky'
Share_Key = "CbMe5clurxoTTFki"
Request_Domain = 'https://openapi-a.linkpayment.net/v2'

query_url = Request_Domain + '/collection'

headers = {'mid': Merchant_ID}

query_data = dict()

query_data['tx_id'] = '457IN717101635489989'
query_data['nonce'] = get_uuid()


query_request_data = generate_post_sign(
    data=query_data,
    secure_key=Share_Key,
    is_upper=True  # 签名是否大写 True:大写 False:小写
)

headers['signature'] = query_request_data.get('sign', '')

query_request_data.pop('sign', None)
print(query_request_data)
print(headers)
try:
    request_return = requests.get(
        url=query_url,
        headers=headers,
        params=query_request_data,
        timeout=3
    )
except requests.exceptions.Timeout:
    print("连接超时异常")
except requests.exceptions.ConnectionError:
    print("连接错误异常")
except json.decoder.JSONDecodeError:
    print("返回数据错误")
else:
    if request_return.status_code == 200:
        return_json = json.loads(request_return.content.decode())
        print(return_json)
    else:
        print(request_return.status_code)
        print(request_return.text)

'''
{
  'code': 0,
  'message': 'Success',
  'merchant_order_id': '20250906-225401-113B97hx8f',
  'tx_id': '457IN717101635489989',
  'order_currency': None,
  'amount': 1000,
  'order_status': '0',
  'order_note': None,
  'payment_link': 'https://cashier-a.linkpayin.com/cashier-page?order_id=457IN717101635489989',
  'customer_email': 'customer@email.com',
  'customer_phone': '1234567890',
  'customer_name': 'John Doe',
  'purpose': 'buy special paid shop item',
  'return_url': None,
  'notify_url': 'https://api.sgbox.top/payment/notify'
}
'''