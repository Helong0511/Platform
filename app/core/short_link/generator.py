"""
短链接生成器
使用 Base62 编码生成短链接代码
"""
import string
import random
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Base62 字符集：0-9, a-z, A-Z
# 排除容易混淆的字符，提高可读性：
# 数字：0（零）、1（一）、2（二）、5（五）、6（六）、8（八）
#   0 vs O/o, 1 vs I/l, 2 vs Z, 5 vs S, 6 vs G, 8 vs B
# 小写字母：o（小写o）、i（小写i）、l（小写L）、u（小写u）、v（小写v）
#   容易混淆：o vs 0/O, i vs 1/I, l vs 1/I, u vs v, v vs u
# 大写字母：O（大写O）、I（大写i）、Z（大写Z）、S（大写S）、G（大写G）、B（大写B）、Q（大写Q）、D（大写D）、U（大写U）、V（大写V）
#   容易混淆：O vs 0/o, I vs 1/i/l, Z vs 2, S vs 5, G vs 6, B vs 8, Q vs O, D vs O, U vs V, V vs U
# 保留的字符：3, 4, 7, 9, a-h, j-k, m, n, p-r, t, w-z, A-H, J-K, M, N, P-R, T, W-X, Y
BASE62_CHARS = (
    '3479' +  # 数字（排除0,1,2,5,6,8）
    'abcdefghjkmnprtwxyz' +  # 小写字母（排除o, i, l, u, v, s, q, d）
    'ABCDEFGHJKMNPRTWXY'  # 大写字母（排除O, I, Z, S, G, B, Q, D, U, V）
)
BASE62_BASE = len(BASE62_CHARS)


def encode_base62(num: int) -> str:
    """
    将数字编码为 Base62 字符串
    
    Args:
        num: 要编码的数字
        
    Returns:
        Base62 编码的字符串
    """
    if num == 0:
        return BASE62_CHARS[0]
    
    result = []
    while num > 0:
        result.append(BASE62_CHARS[num % BASE62_BASE])
        num //= BASE62_BASE
    
    return ''.join(reversed(result))


def decode_base62(encoded: str) -> int:
    """
    将 Base62 字符串解码为数字
    
    Args:
        encoded: Base62 编码的字符串
        
    Returns:
        解码后的数字
    """
    num = 0
    for char in encoded:
        num = num * BASE62_BASE + BASE62_CHARS.index(char)
    return num


def generate_short_code(length: int = 6) -> str:
    """
    生成随机短链接代码
    
    Args:
        length: 代码长度（默认6位）
        
    Returns:
        随机生成的短链接代码
    """
    return ''.join(random.choices(BASE62_CHARS, k=length))


def generate_short_code_from_id(link_id: int, min_length: int = 4) -> str:
    """
    从链接ID生成短链接代码（使用Base62编码）
    
    Args:
        link_id: 链接ID
        min_length: 最小长度（不足时前面补0）
        
    Returns:
        短链接代码
    """
    code = encode_base62(link_id)
    
    # 如果长度不足，前面补随机字符（避免可预测性）
    if len(code) < min_length:
        padding_length = min_length - len(code)
        padding = ''.join(random.choices(BASE62_CHARS, k=padding_length))
        code = padding + code
    
    return code


def generate_unique_short_code(
    existing_codes: set,
    length: int = 6,
    max_attempts: int = 100
) -> Optional[str]:
    """
    生成唯一的短链接代码
    
    Args:
        existing_codes: 已存在的代码集合
        length: 代码长度
        max_attempts: 最大尝试次数
        
    Returns:
        唯一的短链接代码，如果生成失败返回 None
    """
    for _ in range(max_attempts):
        code = generate_short_code(length)
        if code not in existing_codes:
            return code
    
    logger.warning(f"生成唯一短链接代码失败，已尝试 {max_attempts} 次")
    return None

