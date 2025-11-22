import json
import requests

from Utils.handle_md5 import generate_post_sign
from need import get_str_order_number

Merchant_ID = 'lucky'
Share_Key = "CbMe5clurxoTTFki"
Request_Domain = 'https://openapi-a.linkpayment.net/v2'

order_url = Request_Domain + '/collection'

headers = {'mid': Merchant_ID}

order_data = dict()

# 统一订单创建
order_data['merchant_order_id'] = get_str_order_number(test=True)  # String(30) 商户生成的订单号

order_data['amount'] = 500  # int 支付金额,单位分

order_data['customer_name'] = 'john'
order_data['customer_phone'] = '5511912345678'
order_data['customer_email'] = 'hello@example.com'

order_data['notify_url'] = 'https://notify.king-sms.com/global_pay_in_notify'

order_request_data = generate_post_sign(
    data=order_data,
    secure_key=Share_Key,
    is_upper=True  # 签名是否大写 True:大写 False:小写
)
print(order_request_data)
headers['signature'] = order_request_data.get('sign', '')

order_request_data.pop('sign', None)

try:
    request_return = requests.post(
        url=order_url,
        headers=headers,
        json=order_request_data,
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
        if return_json.get('code', 1) == 0:
            print('商户订单号:', return_json.get('merchant_order_id', ''))
            print('平台订单号:', return_json.get('tx_id', ''))
            print('支付链接:', return_json.get('payment_link', ''))
            print('参考码(商户可以根据该值自己生成二维支付码):', return_json.get('reference', ''))
        else:
            print("下单失败")
            print(return_json)
    else:
        print(request_return.status_code)
        print(request_return.text)

'''
{
  'code': 0,  # 返回代码	
  'message': 'Success',  # 返回代码描述	
  'merchant_order_id': 'Test-20250823160055897179',  # 商户订单号
  'tx_id': '457IN711883385198469',  # 平台订单号
  'payment_link': 'https://cashier-a.linkpayin.com/cashier-page?order_id=457IN711883385198469',  # 支付页面地址	
  'reference': '00020126860014br.gov.bcb.pix2564pix.bancoe2.com.br/qr/v3/at/f6b09855-d818-4d3d-84c5-fb6fa45cd1605204000053039865802BR5915VELOCI_NET_LTDA6014SENHOR_DO_BONF62070503***63043153'  # 参考码（二维码内容）
}
'''