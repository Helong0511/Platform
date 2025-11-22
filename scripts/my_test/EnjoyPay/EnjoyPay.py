import requests
from models.handle_md5 import generate_post_sign
from models.handle_time import get_ms_int_timestamp
from need import get_str_order_number, in_notify_url

DEBUG = False

CONFIG = {
    True: {
        "Merchant_ID": "M1753344786",
        "appId": "A1753344786001",
        "Share_Key": "swUcG6FjPL7Awc76Y6ku8sneQJpYfGbgACglqaPGz1Kwi0QoPFi380mq13a0YF9phc6SwQ15bk1y95IORcnlQuifmWLafAlrVTTu0Lc4zAuP3XppvM2tDfmlTqIkzUjP",
        "Request_Domain": "https://gateway.sandbox.enjoypayment.com/payment"
    },
    False: {
        "Merchant_ID": "M1755592521",
        "appId": "A1755592521001",
        "Share_Key": "vQit56YXvGw3tapcO0kSLkCTVIM20u3ZuNIw4AiEZUr4zYtGOdXO7Tj7l4OGoMYPndjaNC6b2LJsyhWFtFrCmdUh51Dx1cNDMURrBxlBfDWuOse7VA9J9cFHPjCg6YoI",
        "Request_Domain": "https://gateway.enjoypayment.com/payment"
    }
}

WAY_MAP = {
    "ALI_PAY_HK": ("HK", "HKD"),  # 支付宝香港
    "BANK_TRANSFER_KR": ("KR", "KRW"),  # 韩国银行转账
    "CREDIT_CARD_KR": ("KR", "KRW"),  # 韩国信用卡
    "KAKAO_PAY": ("KR", "KRW"),  # 韩国KAKAO支付
    "NAVER_PAY": ("KR", "KRW"),  # 韩国NAVER支付
    "PAYCO": ("KR", "KRW"),  # 韩国PAYCO支付
    "SAMSUNG_PAY": ("KR", "KRW"),  # 三星支付
    "TOSS": ("KR", "KRW"),  # 韩国TOSS支付
    "T_MONEY": ("KR", "KRW"),  # 韩国T-MONEY支付
    "VIRTUAL_ACCOUNT_KR": ("KR", "KRW"),  # 韩国虚拟账户
    "BANK_TRANSFER_TW": ("TW", "TWD"),  # 台湾银行转账
    "OTC_TW": ("TW", "TWD")  # 台湾柜台支付
}


def create_order():
    conf = CONFIG[DEBUG]
    order_data = {
        "mchNo": conf["Merchant_ID"],
        "appId": conf["appId"],
        "mchOrderNo": get_str_order_number(test=True),
        "amount": 700,
        "wayCode": "ALI_PAY_HK",
        "clientIp": "18.141.198.202",
        "subject": "test-subject",
        "body": "test-body",
        "notifyUrl": in_notify_url,
        "reqTime": get_ms_int_timestamp(),
        "version": "1.0",
        "signType": "MD5"
    }

    way = order_data["wayCode"]
    if way in WAY_MAP:
        order_data["country"], order_data["currency"] = WAY_MAP[way]
    else:
        order_data["country"], order_data["currency"] = "", ""

    order_request_data = generate_post_sign(
        data=order_data,
        secure_key=conf["Share_Key"],
        is_upper=True
    )

    order_url = conf["Request_Domain"] + "/api/pay/unifiedOrder"

    try:
        resp = requests.post(
            url=order_url,
            headers={"Content-Type": "application/json"},
            json=order_request_data,
            timeout=3
        )
        resp.raise_for_status()
        return_json = resp.json()
        print(return_json)
        if return_json.get("code", 1) == 0:
            print("下单成功")
            print("支付链接:", return_json.get("data", {}).get("payData", ""))
        else:
            print("下单失败")
            print(return_json)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        print(f"请求异常: {e}")
    except Exception as e:
        print(f"其他异常: {e}")


if __name__ == "__main__":
    create_order()
