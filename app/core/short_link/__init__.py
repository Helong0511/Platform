"""
短码生成算法包。

对外导出 Base62 编解码与 short_code 生成函数，供 ``ShortLinkService`` 创建短链时使用。
"""
from app.core.short_link.generator import (
    encode_base62,
    decode_base62,
    generate_short_code,
    generate_short_code_from_id,
    generate_unique_short_code
)

__all__ = [
    "encode_base62",
    "decode_base62",
    "generate_short_code",
    "generate_short_code_from_id",
    "generate_unique_short_code",
]

