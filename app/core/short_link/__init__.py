"""
短链接服务核心模块
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

