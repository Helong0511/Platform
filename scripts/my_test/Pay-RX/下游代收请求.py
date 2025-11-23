import hashlib
import json
import os
import random
import requests
from typing import Dict, Any

from need import (
    Merchant_ID,
    appId,
    Share_Key,
    Request_Headers,
    Request_Order_url,
    get_str_order_number,
    in_notify_url, get_brazil_random_name, get_brazil_random_mobile_number, Time_Out, get_str_md5
)


def get_file_md5_str(file: str) -> str:
    """
    计算文件的 MD5 哈希值

    参数:
        file_path (str): 文件路径

    返回:
        str: 文件的 MD5 哈希值（十六进制字符串）
        或 None: 如果计算过程中出错

    可能出现的错误:
        - 文件不存在
        - 权限不足
        - 路径是目录而非文件
        - 磁盘读取错误
        - 内存不足（对于极大文件）
    """
    # 检查文件是否存在
    if not os.path.exists(file):
        return f"错误: 文件 '{file}' 不存在"

    # 检查是否为文件（而非目录）
    if not os.path.isfile(file):
        return f"错误: '{file}' 是目录而非文件"

    # 检查是否有读取权限
    if not os.access(file, os.R_OK):
        return f"错误: 没有读取文件 '{file}' 的权限"

    try:
        md5_hash = hashlib.md5()
        with open(file, "rb") as f:
            # 分块读取文件，避免大文件内存占用
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    except PermissionError:
        return f"错误: 没有读取文件 '{file}' 的权限"

    except IOError as e:
        return f"错误: 读取文件时发生I/O错误: {e}"

    except MemoryError:
        return f"错误: 内存不足，无法处理大文件 '{file}'"

    except Exception as e:
        return f"错误: 计算MD5时发生未知错误: {e}"


def verify_sign(
        data: Dict[str, Any],
        secure_key: str,
        secure_key_name: str = "key",
        connect: str = "&",
        sign_name: str = "sign",
        is_upper: bool = False  # 新增参数：与生成签名时的 upper 保持一致
) -> bool:
    """
    验证签名是否合法（支持控制 MD5 大小写）

    :param data: 包含签名字段（sign）的字典
    :param secure_key: 用于验签的密钥（需与签名时一致）
    :param secure_key_name: 用于验签的密钥（需与签名时一致）
    :param connect: 用于验签的密钥（需与签名时一致）
    :param sign_name: 用于验签的密钥（需与签名时一致）
    :param is_upper: 是否将 MD5 结果转为大写（需与生成签名时的 upper 一致，默认 False）
    :return: 签名合法返回 True，否则返回 False
    """
    if not isinstance(data, dict):
        return False

    # 检查是否包含签名字段
    if sign_name not in data:
        return False

    # 复制数据并移除签名字段（避免干扰验证）
    data_copy = data.copy()
    original_sign = data_copy.pop(sign_name)

    # 重新生成签名（逻辑与 generate_sign 完全一致，包括 upper 参数）
    sorted_keys = sorted(data_copy.keys())
    params = [f"{key}={str(data_copy[key])}" for key in sorted_keys]
    sign_str = connect.join(params) + f"{connect}{secure_key_name}={secure_key}"

    # 计算生成的签名（使用相同的 upper 参数）
    generated_sign = get_str_md5(sign_str).upper() if is_upper else get_str_md5(sign_str)  # 关键修改点

    # 比较签名是否一致（严格区分大小写）
    return generated_sign == original_sign


def generate_sign(
        data: Dict[str, Any],
        secure_key: str,
        secure_key_name: str = "key",
        connect: str = "&",
        is_upper: bool = False  # 新增参数：是否输出大写 MD5 签名（默认小写）
) -> str:
    """
    生成签名并添加到原始字典中（支持控制 MD5 大小写）

    :param data: 待签名的原始字典（必须为 dict 类型）
    :param secure_key: 用于签名的密钥
    :param secure_key_name: 密钥在签名字符串中的名称
    :param connect: 连接符，默认 "&"
    :param sign_name: 签名字段名称，默认 "sign"
    :param is_upper: 是否将 MD5 结果转为大写（默认 False，即小写）
    :return: 添加了签名字段（sign）的新字典
    """
    if not isinstance(data, dict):
        raise TypeError("参数 data 必须为字典类型")

    # 复制原始数据避免修改原字典
    data_copy = data.copy()

    # 过滤掉空的key 和 sign
    data_copy.pop("sign", None)
    # 1. 按 key 升序排序
    sorted_keys = sorted(data_copy.keys())

    # 2. 拼接键值对（格式：key1=val1&key2=val2...）
    params = []
    for key in sorted_keys:
        value = data_copy[key]
        # 所有值统一转为字符串（避免数字、布尔值等类型问题）
        param = f"{key}={str(value)}"
        params.append(param)

    # 3. 拼接密钥（格式：key1=val1&key2=val2&key=secret_key）
    sign_str = connect.join(params) + f"{connect}{secure_key_name}={secure_key}"

    # 4. MD5 加密并根据 upper 参数转换大小写
    sign = get_str_md5(sign_str).upper() if is_upper else get_str_md5(sign_str)  # 关键修改点

    return sign


open_country = [
    {'country': 'HK',  # 国家代码
     'currency': 'HKD',  # 货币代码
     },
    {'country': 'TW',  # 国家代码
     'currency': 'TWD',  # 货币代码
     },
    {'country': 'KR',  # 国家代码
     'currency': 'KRW',  # 货币代码
     }
]
# ✅ 随机选择一个国家/货币
selected_country_info = random.choice(open_country)
selected_country = selected_country_info['country']
selected_currency = selected_country_info['currency']

order_data = {
    'mchId': Merchant_ID,  # 支付中心分配的商户号
    'appId': appId,  # 商户应用ID
    'mchOrderNo': get_str_order_number(test=True),  # 商户生成的代收号
    'amount': random.randint(10, 100) * 100,  # 支付金额,单位分
    'country': 'HK',  # 国家代码  'HK'    selected_country
    'currency': 'HKD',  # 货币代码  'HKD'    selected_currency
    'userId': 'Test-001',  # 用户ID
    'name': get_brazil_random_name(),  # 用户姓名
    'phone': get_brazil_random_mobile_number(),  # 电话
    'email': 'test@test.com',  # 邮箱
    'clientIp': '18.141.198.202',  # 用户IP
    'notifyUrl': in_notify_url,  # 异步回调地址
    'subject': 'Test-subject',  # 充值标题
    'body': 'Test-body'  # 充值描述
}

order_data['sign'] = generate_sign(
    data=order_data,
    secure_key=Share_Key,
    is_upper=True, )  # 签名字段，必须有，值为空字符串

# 验证签名
if verify_sign(data=order_data, secure_key=Share_Key, is_upper=True):
    print("签名验证通过")
    print(order_data)
else:
    print("签名验证失败")

try:
    request_return = requests.post(
        url=Request_Order_url,
        headers=Request_Headers,
        json=order_data,
        timeout=Time_Out
    )
except requests.exceptions.Timeout:
    print("连接超时异常")
except requests.exceptions.ConnectionError:
    print("连接错误异常")
except json.decoder.JSONDecodeError:
    print("返回数据错误")
else:
    if request_return.status_code == 200:
        print(request_return.json())
    else:
        print(request_return.status_code)
        print(request_return.text)

'''
{
  'code': '200',
  'message': 'SUCCESS',
  'data': {
    'sysOrderNo': 'P3a46b8385d554c67a3eae19c974070d9',
    'payUrl': 'https://open-sea.alipayplus.com/api/open/v1/ac/cashier/self/codevalue/checkout.htm?codeValue=281666040090chqZ7QF5i2t3Js8XpCN7QXGw'
  }
}
'''
