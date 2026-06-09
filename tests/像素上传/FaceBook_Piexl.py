#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Facebook Pixel CAPI 事件上报测试（含 Purchase 金额、SHA256 用户数据）。

支持主/备 Pixel 双路上报；文件内注释含 curl 验证 Token 示例。
"""
import datetime
import hashlib
import random
import time
import uuid

import requests

"""
# 验证 Access Token 有效性
curl -X GET "https://graph.facebook.com/v21.0/1273446968230624?access_token=EAAUIMcFRZAnsBRHOaK1QiLoGB7UVYKBmXadOIfdtIXNlZCMZBbV8XZBeELobgrUmaX03gt8zataZBdXXh64lZA9ZCJZBVL3Wyts0WPbaAWAuI2AQbziBMJfLdNrjWvZCVoAlrhtfd6Nl3erx2PVzE9eA89tZC02io5ETgvGnM2ZCsXF2djT2TbcW3ao6dKkpHOlgrG9OgZDZD"
"""


# ==========================
# 工具函数
# ==========================

def generate_ip() -> str:
    """模拟生成用户真实外网 IP"""
    return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def hash_data(data: str) -> str:
    """Facebook 要求隐私数据必须 SHA-256 哈希，且需先转小写并去除空格"""
    if not data:
        return ""
    # 官方要求：小写、trimmed、SHA256
    cleaned = str(data).lower().strip()
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def generate_email_en() -> str:
    domains = ["gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com"]
    username = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=random.randint(6, 12)))
    return f"{username}@{random.choice(domains)}"


def generate_user_agent() -> str:
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile Safari/604.1",
    ]
    return random.choice(user_agents)


def generate_us_phone_number():
    """生成符合规范的电话格式（带国家码）"""
    line = "".join(str(random.randint(0, 9)) for _ in range(10))
    return f"+1{line}"


# ==========================
# 事件发送逻辑 (升级至 v19.0)
# ==========================

def send_facebook_event(
        pixel_id: str,
        access_token: str,
        event_name: str,
        amount: float = None,
        currency: str = "USD",
        test_code: str = None,
        is_debug: bool = False
):
    # 升级至最新版本 v19.0
    url = f"https://graph.facebook.com/v19.0/{pixel_id}/events"
    params = {"access_token": access_token}

    # ------ user_data (匹配标识符) ------
    user_data = {
        "em": [hash_data(generate_email_en())],
        "ph": [hash_data(generate_us_phone_number())],
        "client_ip_address": generate_ip(),
        "client_user_agent": generate_user_agent(),
        # 模拟 fbp 以提升匹配率
        "fbp": f"fb.1.{int(time.time())}.{random.randint(100, 999)}",
    }

    # ------ event_data (单个事件对象) ------
    event_data = {
        "event_name": event_name,
        "event_time": int(time.time()),
        "action_source": "website",
        "event_id": str(uuid.uuid4()),  # 去重关键 ID
        "user_data": user_data,
    }

    # ------ 根据事件类型配置 custom_data ------
    if event_name in ["Purchase", "finishPayment"]:
        event_data["custom_data"] = {
            "currency": currency,
            "value": float(amount or 0.0)
        }
    elif event_name == "CompleteRegistration":
        event_data["custom_data"] = {
            "content_name": "Standard_Registration",
            "status": True,
            "currency": currency,
            "value": 0.00
        }

    # ------ 构造请求 Payload ------
    payload = {
        "data": [event_data]
    }

    # test_event_code 必须在顶层，与 data 平级
    if is_debug and test_code:
        payload["test_event_code"] = test_code

    print(f"--- 🚀 正在上报: {event_name} ---")
    print(f"📍 节点/ID: {pixel_id}")

    # ========== 自动重试机制 ==========
    for attempt in range(3):
        try:
            response = requests.post(url, params=params, json=payload, timeout=10)
            result = response.json()

            if response.status_code == 200:
                print(f"✅ 发送成功: {result}")
                return result
            else:
                # 处理常见的 ID 不存在或权限问题
                print(f"⚠️ 第 {attempt + 1}/3 次失败 (HTTP {response.status_code}): {result}")
                if "error" in result and result["error"]["code"] == 100:
                    break  # ID 不存在等配置错误无需重试

        except requests.exceptions.RequestException as e:
            print(f"⚠️ 网络错误（尝试 {attempt + 1}/3）: {e}")

        time.sleep(1)

    return None


# ==========================
# 调用示例
# ==========================

if __name__ == "__main__":
    # 2. 配置字典 (引用原始配置)
    FB_PIXEL_CONFIG = {
        "lp1": {
            "pixel_id": "1257748189780933",
            "token": "EAAXW0mecENUBRH0Gy6RgpASivlDaQzk44YXK2lb2LigiE7ZAUmNo7m3ogsAsZCn8LL1xCKnFJ1uulvKAduXKv8YO9K0C5tg6cUiCXXEIpVqwLnsD66GObgzrZClgYSbwB1ewJXqyQzSuJxvktAHjZBKA4a2VCsoqigTA3tLFtHau1Nk8Htuiro6FRCkKqPAZAMQZDZD",
            "test_code": "TEST62818"
        },
        "lp2": {
            "pixel_id": "954610956923027",
            "token": "EAAXW0mecENUBRH0Gy6RgpASivlDaQzk44YXK2lb2LigiE7ZAUmNo7m3ogsAsZCn8LL1xCKnFJ1uulvKAduXKv8YO9K0C5tg6cUiCXXEIpVqwLnsD66GObgzrZClgYSbwB1ewJXqyQzSuJxvktAHjZBKA4a2VCsoqigTA3tLFtHau1Nk8Htuiro6FRCkKqPAZAMQZDZD",
            "test_code": "TEST8537"
        },
        "lp3": {
            "pixel_id": "2005216250339191",
            "token": "EAAXW0mecENUBRH0Gy6RgpASivlDaQzk44YXK2lb2LigiE7ZAUmNo7m3ogsAsZCn8LL1xCKnFJ1uulvKAduXKv8YO9K0C5tg6cUiCXXEIpVqwLnsD66GObgzrZClgYSbwB1ewJXqyQzSuJxvktAHjZBKA4a2VCsoqigTA3tLFtHau1Nk8Htuiro6FRCkKqPAZAMQZDZD",
            "test_code": "TEST85813"
        },
        "lp4": {
            "pixel_id": "959099563289055",
            "token": "EAAXW0mecENUBRH0Gy6RgpASivlDaQzk44YXK2lb2LigiE7ZAUmNo7m3ogsAsZCn8LL1xCKnFJ1uulvKAduXKv8YO9K0C5tg6cUiCXXEIpVqwLnsD66GObgzrZClgYSbwB1ewJXqyQzSuJxvktAHjZBKA4a2VCsoqigTA3tLFtHau1Nk8Htuiro6FRCkKqPAZAMQZDZD",
            "test_code": "TEST68485"
        },
        "lp5": {
            "pixel_id": "936337029099219",
            "token": "EAAXW0mecENUBRH0Gy6RgpASivlDaQzk44YXK2lb2LigiE7ZAUmNo7m3ogsAsZCn8LL1xCKnFJ1uulvKAduXKv8YO9K0C5tg6cUiCXXEIpVqwLnsD66GObgzrZClgYSbwB1ewJXqyQzSuJxvktAHjZBKA4a2VCsoqigTA3tLFtHau1Nk8Htuiro6FRCkKqPAZAMQZDZD",
            "test_code": "TEST99970"
        },
        "lp6": {
            "pixel_id": "1273446968230624",
            "token": "EAAUIMcFRZAnsBRHOaK1QiLoGB7UVYKBmXadOIfdtIXNlZCMZBbV8XZBeELobgrUmaX03gt8zataZBdXXh64lZA9ZCJZBVL3Wyts0WPbaAWAuI2AQbziBMJfLdNrjWvZCVoAlrhtfd6Nl3erx2PVzE9eA89tZC02io5ETgvGnM2ZCsXF2djT2TbcW3ao6dKkpHOlgrG9OgZDZD",
            "test_code": "TEST98863"
        },
        "lp7": {
            "pixel_id": "1483729203107246",
            "token": "EAAcMW7Vvha4BRGUAZBYDMY9bS0VsenzFP2MeR9ylIVjXPPJKGA6FkydDhMPWPefhZC6lmY5ZB13HaB0K8WdHY8aT7z7UFgrfxM8bz3f4XYZApxDPaatAJuTBme3AZC1tLXH8Ns5TV6AtnNcI3bRVRZCoFEaWZAyAVjpReNKHEo8ro7vBwA07XHtQgCBnJNLHr6bNwZDZD",
            "test_code": "TEST98863"
        },
        "lp8": {
            "pixel_id": "1520900059429448",
            "token": "EAAKF7xZAa0yIBRMJbfJsJQrHD4XmLd8dEKPOKyvx2KqHaOKIToZCLgh45QXKEly5Gy2cHRrhfkZBD147NZAzVnFthNTZB42YY0QaUThVPHfZAsBosZCg31Jq57DvgpiZAz9bomqg4mIHmRpMxiVzP13CTwAFk6SoPlyJcSDfrfViOSVVwvZCms7cyIPZCZCuZCtROILALgZDZD",
            "test_code": "TEST98863"
        },
        "lp9": {
            "pixel_id": "1124622134062236",
            "token": "EAAifTOaIZCfQBRUvZBp4OmlIpYfCX4kSOITYbBXpMEvR9hGVABb40DnmZAuOGfXCghiOmtbU9IOzVfNX4UixokNPAzRIoAJ5Wd0dXdxZBZCGoYzycyIQTx68xNOpkYc37320gqQB2SzocbiT60YEZARK9DVHLFYV83XTU6uZBHbSwnhpZCmQ4YSGTF1H7DdlFLn8iQZDZD",
            "test_code": "TEST98863"
        }
    }

    # 3. 指定测试节点
    # for i in range(1, 7):

    # 1. 统一全局测试开关
    TEST_SWITCH = False  # True False

    target_key = "lp9"

    print("-" * 80)
    if TEST_SWITCH:
        print(f"{target_key} 测试上报：")
    else:
        print(f"{target_key} 正式上报：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if target_key in FB_PIXEL_CONFIG:
        config = FB_PIXEL_CONFIG[target_key]

        # 4. 执行发送
        send_facebook_event(
            pixel_id=config["pixel_id"],
            access_token=config["token"],
            event_name="Purchase",  # Purchase  CompleteRegistration
            test_code=config["test_code"],
            is_debug=TEST_SWITCH
        )
    else:
        print(f"❌ 未找到配置: {target_key}")
