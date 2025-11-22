# -*- coding: utf-8 -*-
# !/usr/bin/env python
import datetime
import time
import requests
import json

from Cryptodome.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5
from Crypto.Hash import SHA256
import base64

pay_currency = "BRL"

DEBUG = False

if DEBUG:
    Merchant_ID = "100000"
else:
    Merchant_ID = "A0110007"

SYS_PUBLIC_KEY = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAroupTD8Acdbs0AwPWvAnYziQRRJJ4/gLOXgoDIDOHpqDDhqPYZ6GVVjGEdwqGwc2NgE51w+aU47QYM/4T/tgaIcF+TEmySYOy3/dVcvhh23GPi7oZMsHTTWokfTFPhvXfxEcLd8bRHdJMU2JoEw9qy+fJiZSzifxzBpZpXRuEn644ti+v/JfTQo19TAL4ROGRDkfRjK/tA8S2Y4C1CgaxOJodG/+d0bVf/0VCubkcPrR2TlLI3tFSIKQx5NqKpD/AGc0e0OiryMbv2utIEgoRDRJfM5Jy9Cv2bYPxxyPtj4M081y79DeNw8OunKrHJamYU7yjJ+ft6UzfDqc/7srXQIDAQAB"

PUBLIC_KEY = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1SksAOFlkMD+s1MPpp4DwOUKBdmLhaz9zFZHugd6drPkW7nn+UVCUmadbRQgfg0Ltt6YK0roIf09me8cDa4QjS9bC3/sNL41ZgnDvzlB+r7zBK9ea6FUsoHf89Mppi/BKfiY7ZoeHbzsHvx67EkomM85v4AS6LuIVGyhPKbpxrc3N4cbZ4awpxv11b8wqkhGtMTT/ipci0aYYH3Xg7hUETm3cY4KXgjovEz8q0kBHvQhsPgh+H06EySTz2A6D/JPadYB17I+fUnPw+MoBjIZKUvPP0I/1MfD8FXLHG2Cw0EKGGnhZYMZEnfCzKWL7j27ZTKXlZ10G+W+G+1SJrnwuwIDAQAB"

if DEBUG:
    PRIVATE_KEY = "MIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQC2Fr43Dj/+CEmCJKgN81uUS3vyUp4BRI3Vzi2ZZlOCwmWuigfHLHW2K49qoKy7TOB84l/rj3NvU6vCioMLl2OK88nfXCmfQQCIu7ZHStNh1RglgXhP/f4L/rq0EjNulK4qD4Us3FBO+7/s0OfYXncd/RI8UAm1ptGf5V4uqAkaxhZr806aed4KwpXFZU4iReFJYT2XXO8CZKfQN2Uh14jr1b79r0bOAHEuk5+EhQgT9KjtufMJjnQMoXTpMcxzfA0qkp4X2Qc61WnwT4l4k4XpYF+erMvO5rays7VwxLgHI+QThm1tCi0gkff3o1/z/ce3XqpuyuHdwRfiuF1gfw7XAgMBAAECggEBAIepXCByqnSeQf4HR3nVVOagcoDw0q2JIM8pZEnEtfVW1iD6z56x3iVSQPClMuv888e3dNVwtAU+ZlpzjfzF1rEAvud9p7jx2e8FQ2HMOr7J38qZskSOrIbNSta8NLtvZG8LzyHEJsUhxTUv03wdrUuXb82lqAZBei5R2iCSqu3ZY187ZfjCJiNCICRWQaS0wubEnXXQa88cWF3ftb2aCqegPzwD0Ko2zaCC3367w/Yk4zJsrTxVzlyM6PZlcaJdqSg/6b6jH10ngDYFxxo+AQ4bagyRVWdQ84K8Fn0q9IjhKVtp7+82YzvGTpAa4dDK4e2/EGfUxXRL7nLxUuVca7ECgYEAzWKwi0BY41/d6E+EKTnCQRXPVACVL8a1vqf1eQ5laSHkhvjS8OgAKYgu2rbwxvz1B0vHUO5vNS5cdqOLgnLf0mHH9fpZq4TKdOjKlA7xvXgVD5Jjm9jLgSK7VVBNBKp7LnCh2aCuVfjv7Ydho162OcWQVgzJzYaxryw/TvT3GbkCgYEA4vZRrFGZC1/206XnPJSib4sq1Xgmudct6isCeogqp830I9D7Hm69yKL6UfECjDDpBupOnkNEeku4kTimaNUMxJTT79TTMEbRiKy9+xnmrgBjkjxYskBzPtAMCnMZpeNn3jrWt9/kedgiwTJlxFgvNRqWCOOwXKljljT7gMbbdQ8CgYEAnEsNreo5uk2pwK9CE10wxfai33nSDZlZlMybsJOT+H0iOtP/MfRaq0BG54lvkP3OOM8hziSj3AR7uIycDZj9WkuurzDkK/HRX0YHYsQ8kcJfxInR4zcHJi4YAMQq1/Ij6yMrB0GPaT0W19q+ImRgp3YAcHsq1ow5iuRRCPTBVYECgYAgvYO+pe6781X55h7bYF2mVZ8SOEjt2hqngxjScD4nAtDLMeRn2XXLMaeGlovViWC0PKymq/F+6tlvKYrn6IP0/7srB7qHZk/ntXOae3wJccjrWYU6AY4ea4ixITV79rgPGNHMqKGe6gzpbcm8bzQwJuup0J6qX00cZ/w38XfLBQKBgQCRGpCY37e0rm7aFfGCDjRnAhMfHCRNGW6PUaTvZinNmhf5d+PwFEbCcESNQjzz2NSExhiNGHeGh5gTE4jWN9seaxD+K7SKPjFBEy6fUu/+eqveIXCMWkbxaizeFrvf9H4Y4PZtgCQUZcMMnuxfZXfM/8SSm4mzxsOG9ruaMx7KMQ=="
else:
    PRIVATE_KEY = "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDVKSwA4WWQwP6zUw+mngPA5QoF2YuFrP3MVke6B3p2s+Rbuef5RUJSZp1tFCB+DQu23pgrSugh/T2Z7xwNrhCNL1sLf+w0vjVmCcO/OUH6vvMEr15roVSygd/z0ymmL8Ep+Jjtmh4dvOwe/HrsSSiYzzm/gBLou4hUbKE8punGtzc3hxtnhrCnG/XVvzCqSEa0xNP+KlyLRphgfdeDuFQRObdxjgpeCOi8TPyrSQEe9CGw+CH4fToTJJPPYDoP8k9p1gHXsj59Sc/D4ygGMhkpS88/Qj/Ux8PwVcscbYLDQQoYaeFlgxkSd8LMpYvuPbtlMpeVnXQb5b4b7VImufC7AgMBAAECggEAQXNZ4o9S20aXLkKzzIo6RtFM6YzprUr3xvU7IuDG9om39X44vy5H9fsyHVsPuwSQcz8X5Dsk2cLjVk+4Am9O/7rprrdBtNQumz0mUKHpI2/cOLUMPeoUkpcUR86vvCpvmk6Nzm8DDkiDC+Skbcbs4zbF2YoexD1I1/te6rupjm0FsWQkWN81KgLCnC8+LZcxhTRLuDP43wmg9yE7cRypj5pYUlJuM01ZJZhOCFuZBTawYG3nb4MndF5HFojT1SReNZuH0InaU8w2VjU9WqwE2gv0xaqtF24UQUjsCJC7gq2P8Wkbo5Q70EegQe7CP3QZRu/dTaJVHmmVqiVR2p3KMQKBgQD1pA7O2fn5DNTXH+/La1jwE3mRRPMRcS4cpTqOAfgU2cxuNdZRd47oG2QSDvPKD8mbHJVjl3nEywZ1Schxhf7zDjLLiABn2cVUoYd/6Mmuyhicn6Fdfh5C6e5slpHgvxpBrefPLWgrt6orZtqikh2yjG9iGMVg1zjHn8XJAZjV4wKBgQDeJnWRMwo+Cx7sjIro3gdOBmvuW/GnS+HbJdSc/tE40GhDDgLzvemhVJ/Y7oUomNT9YvvJxblkeDjXgujhQfSkJazWT+CEKwKXENu4MkEMN6ACX+zFw5vvE4sJeMHr1dsoJcwV81vAlI3mQLIdU1e73ez/MpQ7tsfoExxt/CGxSQKBgQC/00VJHgpLBk00ThlqJsOGf/7ghhK3nUYgUpveiAUe61LtAhgC+LXd5n4IaCrTse6DthendYQ/PTkm4N6qYLTPRFhAf02py/OA+r+hEL5nRCViMnrGUxX4tUxe+lqjQzmS7ubm8JO4CC7Yw/KbIDYW1/qnhaal0Izjv46qQRgEdwKBgG3nawy9yphtWgw/b83LYqPIa4dON5zD3uZTrf9J1eqcuKhL+0vpLfeh7T8eqgQusFj3qoflaVX6YGzGmD4xKj43YW3ZsMLSoIJqVbmoKyRHNMNX/8TLhI7gBU5XTuFFORqAsJo/fqolFJrQcQ4vGF2aatDKjimIwRfgtJT5QxX5AoGBAMWjhQeUFTs+OFWDiyVZisZhVAEtHZwG+u82IvtX54Un8wE295QES54Sg+NinSDogbrlUeeSGKbRgEI0NQCDdSX92xuc/Up8usNe2SmYOCaMMC2YrOu1CCcOXEP6hClxHm1sqC/SHPAqMIVIqPQfKUFYt7ZLBtUaMkjmLcP/7S52"

Request_Order = "https://v2.okeypay.net/pay"
Request_Query = "https://v2.okeypay.net/pay/query"
Request_Balance = "https://v2.okeypay.net/balance"
Request_Proof = "https://v2.okeypay.net/transfer/proof"

Request_headers = {'Content-Type': 'application/json'}


def encrypt_with_rsa(message, private_key):
    private_key_bytes = base64.b64decode(private_key)
    pri_key = RSA.importKey(private_key_bytes)
    signer = PKCS1_v1_5.new(pri_key, )
    hash_obj = SHA256.new(message.encode('utf-8'))
    sign_ture = base64.b64encode(signer.sign(hash_obj))
    return sign_ture.decode('utf8')


def get_str_time_number():
    temp_str = str(datetime.datetime.now().year).rjust(4, "0") + \
               str(datetime.datetime.now().month).rjust(2, "0") + \
               str(datetime.datetime.now().day).rjust(2, "0") + \
               str(datetime.datetime.now().hour).rjust(2, "0") + \
               str(datetime.datetime.now().minute).rjust(2, "0") + \
               str(datetime.datetime.now().second).rjust(2, "0") + "-" + \
               str(datetime.datetime.now().microsecond).zfill(6)
    if DEBUG:
        return "Test" + Merchant_ID + temp_str
    else:
        return temp_str


def rsa_sign(data, private_key, connect="&", sign_name="sign"):
    temp_dict = []
    if type(data) is dict:
        for key in data.keys():
            temp_dict.append(key)
        temp_dict.sort()
        post_order = {}
        temp_str = ""
        for key in temp_dict:
            if type(data[key]) is str:
                if len(data[key]) > 0:
                    post_order[key] = data[key]
                    if len(temp_str) == 0:
                        temp_str = temp_str + f"{key}={data[key]}"
                    else:
                        temp_str = temp_str + f"{connect}{key}={data[key]}"
            elif type(data[key]) is float or type(data[key]) is int:
                if data[key] > 0:
                    post_order[key] = data[key]
                    if len(temp_str) == 0:
                        temp_str = temp_str + f"{key}={data[key]}"
                    else:
                        temp_str = temp_str + f"{connect}{key}={data[key]}"
            else:
                if len(data[key]) > 0:
                    post_order[key] = data[key]
                    if len(temp_str) == 0:
                        temp_str = temp_str + f"{key}={data[key]}"
                    else:
                        temp_str = temp_str + f"{connect}{key}={data[key]}"
        post_order[sign_name] = encrypt_with_rsa(temp_str, private_key)
        data[sign_name] = encrypt_with_rsa(temp_str, private_key)
        # return post_order
        return data
    else:
        return temp_dict


def get_oder(amount):
    order_json = {
        'merchant_code': Merchant_ID,
        'merchant_order_no': get_str_time_number(),
        'name': 'AdnanSami',
        'mobile': '9882223456',
        'email': 'heisenbergenterprise88@gmail.com',
        'amount': amount,
        'notify_url': 'https://api.okeypay.top/okeyPay/payin',
        'page_url': 'https://api.okeypay.top/pay',
        'order_time': int(time.time()),
        'description': '',
        'customer_ip': '119.136.114.111'
    }

    if pay_currency == "INR":  # 印度-卢比
        order_json['account_type'] = 'UPI/IFSC'
    elif pay_currency == "BRL":  # 巴西-雷亚尔
        order_json['account_type'] = ''
        order_json['account_code'] = '99999999999'  # 巴西必填：用户CPF/CNPJ个人税号
        order_json['is_cpf_valid'] = 0  # 巴西独有参数，值为1时用户支付会校验CPF（account_code参数），0不做校验
    # elif pay_currency == "PHP":  # 菲律宾
    #     order_json['account_type'] = ''
    # elif pay_currency == "BDT":  # 孟加拉
    #     order_json['account_type'] = ''
    # elif pay_currency == "IDR":  # 印尼
    #     order_json['account_type'] = ''
    # elif pay_currency == "MXN":  # 墨西哥
    #     order_json['account_type'] = ''
    # elif pay_currency == "RUB":  # 俄罗斯
    #     order_json['account_type'] = ''
    # elif pay_currency == "THB":  # 泰国
    #     order_json['account_type'] = ''
    # elif pay_currency == "NGN":  # 尼日利亚
    #     order_json['account_type'] = ''
    # elif pay_currency == "VND":  # 越南
    #     order_json['account_type'] = ''
    # else:
    #     order_json['account_type'] = ''

    try:
        d_return = requests.post(
            url=Request_Order,
            headers=Request_headers,
            json=rsa_sign(data=order_json, private_key=PRIVATE_KEY),  # PUBLIC_KEY  PRIVATE_KEY
            timeout=(5, 10)  # 请求连接超时 5秒  等待 10秒
        )
        return_json = json.loads(d_return.content.decode())
    except requests.exceptions.Timeout:
        print("连接超时异常")
    except requests.exceptions.ConnectionError:
        print("连接错误异常")
    except json.decoder.JSONDecodeError:
        print("返回数据错误")
    else:
        if return_json['code'] == 200:
            print(f"本地订单号：{return_json['data']['merchant_order_no']}")
            print(f"商户号：{return_json['data']['merchant_code']}")
            print(f"平台订单号：{return_json['data']['order_no']}")
            print(f"订单 金额：{return_json['data']['amount']}")
            print(f"支付地址：{return_json['data']['pay_link']}")
        else:
            print(return_json)
            print(return_json['message'])


def query_order(order_no):  # 查询代收订单号
    query_json = {
        'merchant_code': Merchant_ID,
        'merchant_order_no': order_no
    }

    try:
        d_return = requests.post(
            url=Request_Query,
            headers=Request_headers,
            json=rsa_sign(data=query_json, private_key=PRIVATE_KEY),  # PUBLIC_KEY  PRIVATE_KEY
            timeout=(5, 10)  # 请求连接超时 5秒  等待 10秒
        )
        return_json = json.loads(d_return.content.decode())
    except requests.exceptions.Timeout:
        print("连接超时异常")
    except requests.exceptions.ConnectionError:
        print("连接错误异常")
    except json.decoder.JSONDecodeError:
        print("返回数据错误")
    else:
        if return_json['code'] == 200:
            print(f"本地订单号：{return_json['data']['merchant_order_no']}")
            print(f"商户号：{return_json['data']['merchant_code']}")
            print(f"平台订单号：{return_json['data']['order_no']}")
            print(f"订单 金额：{return_json['data']['amount']}")
            if return_json['data']['status'] == -1:
                print(f"订单 状态：支付失败")
            elif return_json['data']['status'] == 0:
                print(f"订单 状态：待支付")
            elif return_json['data']['status'] == 2:
                print(f"订单 状态：支付成功")
            elif return_json['data']['status'] == 3:
                print(f"订单 状态：订单异常（只有代收有，比如用户支付金额与实际不符）")
            print(f"下单时间戳：{return_json['data']['timestamp']}")
        else:
            print(return_json['message'])


def query_balance():  # 查询商户余额
    query_json = {'merchant_code': Merchant_ID}

    try:
        d_return = requests.post(
            url=Request_Balance,
            headers=Request_headers,
            json=rsa_sign(data=query_json, private_key=PRIVATE_KEY),  # PUBLIC_KEY  PRIVATE_KEY
            timeout=(5, 10)  # 请求连接超时 5秒  等待 10秒
        )
        return_json = json.loads(d_return.content.decode())
    except requests.exceptions.Timeout:
        print("连接超时异常")
    except requests.exceptions.ConnectionError:
        print("连接错误异常")
    except json.decoder.JSONDecodeError:
        print("返回数据错误")
    else:
        if return_json['code'] == 200:
            print(f"商户号：{return_json['data']['merchant_code']}")
            print(f"可用余额：{return_json['data']['available_balance']}")
            print(f"待结算金额：{return_json['data']['unsettled_amount']}")
            print(f"提现中金额：{return_json['data']['withdrawing_amount']}")
            print(f"冻结金额：{return_json['data']['frozen_amount']}")
        else:
            print(return_json['message'])


def query_proof(order_no):  # 查询代付凭证
    query_json = {'merchant_code': Merchant_ID,
                  'merchant_order_no': order_no}

    try:
        d_return = requests.post(
            url=Request_Proof,
            headers=Request_headers,
            json=rsa_sign(data=query_json, private_key=PRIVATE_KEY),  # PUBLIC_KEY  PRIVATE_KEY
            timeout=(5, 10)  # 请求连接超时 5秒  等待 10秒
        )
        return_json = json.loads(d_return.content.decode())
    except requests.exceptions.Timeout:
        print("连接超时异常")
    except requests.exceptions.ConnectionError:
        print("连接错误异常")
    except json.decoder.JSONDecodeError:
        print("返回数据错误")
    else:
        if return_json['code'] == 200:
            print(f"本地订单号：{query_json['merchant_order_no']}")
            print(f"商户号：{return_json['data']['link']}")
        else:
            print(return_json['message'])


def payment():
    payment_json = {
        'merchant_code': Merchant_ID,
        'merchant_order_no': get_str_time_number(),
        'account_type': '',
        'account_code': '',
        'account_number': '',
        'name': '',
        'mobile': '',
        'email': '',
        'amount': 100.00,
        'notify_url': '',
        'order_time': '',
        'description': '',
        'bank_code': '',
        'branch': '',
        'id_number': '',
        'customer_ip': '',
        'is_cpf_valid': ''
    }

    """
    account_type
        印度：UPI/IFSC
        巴西（填写数字）：1 - CPF，2 - CNPJ，3 - EMAIL，4 - PHONE，5 - EVP， 6 - SLRY, 7 - SVGS, 8 - CACC, 9 - TRAN
        菲律宾：填写GCASH/GRABPAY/PAYMAYA 任选其一
        墨西哥：default - Clabe，40 - Clabe，3 - 银行卡
        越南：default
        印尼：default
        哥伦比亚：1-活期账户，2-储蓄账户
        孟加拉：upay、rocket、nagad、bkash
        巴基斯坦：1 - BANK、2 - WALLET

    account_code
        印度：ifsc编码
        巴西：用户CPF/CNPJ个人税号 （account_type为6/7/8/9时必填）
        菲律宾：default
        墨西哥：收款银行编码，详见银行信息
        越南：收款银行编码，详见银行信息
        印尼：钱包选填 ovo、dana、gopay、shopeepay、linkja，网银选填收款银行编码，详见银行信息
        泰国：收款银行编码，详见银行信息
        哥伦比亚：收款银行编码，详见银行信息
        巴基斯坦：详见银行编码
        尼日利亚：详见银行编码
    
    account_number
        印度：收款账号
        巴西：根据account_type填写相应账户类型的号码；Pix号(支持格式: 用户的邮箱/带国际区号手机号(例如+55XXXXXXX)/CPF/CNPJ/EVP）
        菲律宾：收款账号
        墨西哥：收款账号
        越南：收款账号
        印尼：收款账号
        哥伦比亚：收款账号
    """
    if pay_currency == "INR":  # 印度-卢比
        payment_json['account_type'] = 'UPI/IFSC'
        payment_json['account_code'] = 'UPI/IFSC'
        payment_json['account_number'] = 'UPI/IFSC'
    elif pay_currency == "BRL":  # 巴西-雷亚尔
        payment_json['account_type'] = '1'
        payment_json['account_code'] = '1'
        payment_json['account_number'] = '1'


print("-" * 112)
print("-" * 50, "代收订单请求", "-" * 50)
# 代收订单请求
# get_oder(amount=888.88)

print("-" * 50, "查询代收订单？", "-" * 50)
# # 查询代收订单号
# query_order('Test10000020241028111601-785747')

print("-" * 50, "查询商户余额", "-" * 50)
# 查询商余额
query_balance()
#
# print("-" * 50, "查询代付凭证", "-" * 50)
# # 查询代付凭证
# query_proof('P3ZrmCtqA5Z9Zq5BzMZez0')
print("-" * 112)
