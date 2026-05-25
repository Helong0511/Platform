#!/usr/bin/env python
# -*- coding: utf-8 -*-
import hashlib
import random
import time

import requests

DEBUG = False  # 测试开关 True 就是测试   False 就是正式


def generate_ip() -> str:
    """生成随机 IP 地址"""
    return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def hash_data(data: str) -> str:
    if not data:
        return ""

    # 清理数据 (小写，去空格)
    cleaned = data.lower().strip()

    # SHA-256 哈希
    hashed = hashlib.sha256(cleaned.encode('utf-8')).hexdigest()

    return hashed


def generate_email_en(name: str = None) -> str:
    """生成英文用户邮箱"""
    domains = ["gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com"]
    if name:
        username = name.replace(" ", "").lower()
    else:
        username = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=random.randint(6, 12)))
    domain = random.choice(domains)
    return f"{username}@{domain}"


def generate_user_agent() -> str:
    """生成随机 User Agent"""
    user_agents = [
        # Windows Chrome
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Windows Edge
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        # macOS Safari
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        # macOS Chrome
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # iPhone Safari
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        # Android Chrome
        "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    ]
    return random.choice(user_agents)


def generate_us_phone_number(include_country_code=True):
    area_code = ""
    area_code += str(random.randint(2, 9))  # 第一位不能是0或1
    area_code += str(random.randint(0, 8))  # 第二位不能是9
    area_code += str(random.randint(0, 9))

    # 生成交换码 (第一位: 2-9, 后两位: 0-9)
    exchange_code = ""
    exchange_code += str(random.randint(2, 9))  # 第一位不能是0或1
    exchange_code += str(random.randint(0, 9))
    exchange_code += str(random.randint(0, 9))

    # 生成线路号 (任意4位数字)
    line_number = ""
    for _ in range(4):
        line_number += str(random.randint(0, 9))

    # 根据选择的格式进行格式化
    formatted_number = f"{area_code}{exchange_code}{line_number}"

    # 添加国际区号
    if include_country_code:
        formatted_number = f"+1 {formatted_number}"

    return formatted_number


FIRST_NAMES_EN = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica",
    "Thomas", "Charles", "Christopher", "Daniel", "Matthew", "Anthony", "Donald", "Mark",
    "Sarah", "Karen", "Nancy", "Lisa", "Betty", "Margaret", "Sandra", "Ashley",
]

LAST_NAMES_EN = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
]

pixel_id = "1273446968230624"

access_token = "EAAUIMcFRZAnsBRHOaK1QiLoGB7UVYKBmXadOIfdtIXNlZCMZBbV8XZBeELobgrUmaX03gt8zataZBdXXh64lZA9ZCJZBVL3Wyts0WPbaAWAuI2AQbziBMJfLdNrjWvZCVoAlrhtfd6Nl3erx2PVzE9eA89tZC02io5ETgvGnM2ZCsXF2djT2TbcW3ao6dKkpHOlgrG9OgZDZD"

api_version = "v18.0"

proxies = None  # 例如："http://127.0.0.1:8080"

TEST_EVENT_CODE = "TEST56374"

url = f"https://graph.facebook.com/{api_version}/{pixel_id}/events"

params = {"access_token": access_token}

event_data = {
    'event_name': 'Purchase',  #  ViewContent：查看内容      
    'event_time': int(time.time()),
    'action_source': 'website',
    'event_id': f'Purchase{int(time.time())}',
    'user_data': {
        'em': hash_data(generate_email_en()),
        'ph': hash_data(generate_us_phone_number()),
        'fn': hash_data(random.choice(FIRST_NAMES_EN)),
        'ln': hash_data(random.choice(LAST_NAMES_EN)),
        'client_ip_address': generate_ip(),
        'client_user_agent': generate_user_agent()
    }
}

"""
action_source:
website	网站事件（Pixel、CAPI）
app	App 内事件（SDK 或 CAPI）
physical_store	线下实体店
chat	聊天（WhatsApp, Messenger）
email	邮件触发
phone_call	电话销售
system_generated	自动生成（后台系统）
other	其他
"""

if DEBUG:
    payload = {
        "data": [event_data],
        "test_event_code": TEST_EVENT_CODE,  # ← 加这里！
        "test": True
    }
else:
    payload = {
        "data": [event_data],
        "test": False
    }

try:
    print("params:", params)
    print("json:", payload)
    print("proxies:", proxies)

    response = requests.post(
        url,
        params=params,
        json=payload,
        proxies=proxies,
        timeout=5
    )
    result = response.json()

    if response.status_code == 200:
        print("发送成功!")
        print(result)
    else:
        print(response.status_code)
except requests.exceptions.RequestException as e:
    print(f"❌ 网络错误：{e}")
