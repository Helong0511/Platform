import datetime
import hashlib
import os
import time
from typing import Dict, Any
from fastapi import Response

from passlib.context import CryptContext  # pip install bcrypt==4.0.1

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

success = Response(content="success", media_type="text/plain")
ok = Response(content="ok", media_type="text/plain")


def get_uuid():
    return os.urandom(16).hex()


def get_str_md5(content):
    try:
        md5 = hashlib.md5(content.encode(encoding='utf-8'))  # 创建md5对象
        return md5.hexdigest()
    except Exception as e:
        print(f"MD5生成失败: {e}")
        return None


def generate_post_sign(
        data: Dict[str, Any],
        secure_key: str,
        secure_key_name: str = "key",
        connect: str = "&",
        sign_name: str = "sign",
        is_upper: bool = False  # 新增参数：是否输出大写 MD5 签名（默认小写）
) -> Dict[str, Any]:
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

    # 5. 将签名添加到原始字典（返回新字典，不修改原数据）
    data_copy[sign_name] = sign

    return data_copy


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


def verify_hash_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_hash_password(password: str) -> str:
    return pwd_context.hash(password)


# 使用示例
# file_path = "E:\\FastAPI\\fastapi.service"  # 替换为你的文件路径
# md5_value = get_file_md5_str(file_path)
# print(f"文件的 MD5 值为: {md5_value}")

# print(get_hash_password("123456"))  # True
# print(verify_hash_password("123456", get_hash_password("123456")))  # True


def create_signature(data: dict, secret_key: str) -> str:
    """
    生成一个签名。

    Args:
        data: 包含要签名的数据的字典。
        secret_key: 用于签名的密钥。

    Returns:
        生成的签名字符串（小写）。
    """
    # 1. 过滤掉字典中值为 None 或空字符串的键值对
    filtered_data = {
        k: v for k, v in data.items() if v is not None and v != ''
    }

    # 2. 按键（key）的字母顺序对字典进行排序
    sorted_keys = sorted(filtered_data.keys())
    print('排序后的key:', sorted_keys)

    # 3. 拼接成字符串
    # 格式：key1=value1&key2=value2...
    params_string = '&'.join(
        [f"{key}={filtered_data[key]}" for key in sorted_keys]
    )

    # 4. 拼接密钥，然后进行哈希加密
    # 假设签名规则是：params_string + secret_key
    to_be_signed = params_string + '&' + 'key' + '=' + secret_key
    print('拼接后的字符串:', to_be_signed)

    # 使用 SHA256 进行哈希
    sha256 = hashlib.sha256()
    sha256.update(to_be_signed.encode('utf-8'))

    # 返回小写十六进制字符串
    return sha256.hexdigest()


def get_str_current_time_number(test=False):
    try:
        now_time = datetime.datetime.now()
        temp_str = (str(now_time.year).rjust(4, "0") +
                    str(now_time.month).rjust(2, "0") +
                    str(now_time.day).rjust(2, "0") +
                    str(now_time.hour).rjust(2, "0") +
                    str(now_time.minute).rjust(2, "0") +
                    str(now_time.second).rjust(2, "0") +
                    str(now_time.microsecond).zfill(6))

        if test:
            return "Test-" + temp_str
        else:
            return temp_str
    except Exception as err:
        print(f"获取当前时间字符串失败: {err}")
        return None

print(get_hash_password('helong'))
print(get_str_current_time_number())
# 密钥
# my_secret = 'your_secure_secret_key'
#
# # 生成签名
# signature = create_signature(my_data, my_secret)
#
# print(f"待签名的数据：{my_data}")
# print(f"密钥：{my_secret}")
# print(f"拼接后的字符串（示例）：name=张三&age=30&city=北京{my_secret}")
# print(f"生成的签名：{signature}")
