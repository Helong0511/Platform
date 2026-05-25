"""
兼容层：广告追踪令牌实现已迁入生产代码。

请使用::
    from app.core.tracking.ad_tracking_codec import AdTrackingCodec
    from app.core.tracking.click_token import generate_tracking_click_id, resolve_click_from_token

本文件仅 re-export，避免与 ``app/core/tracking/ad_tracking_codec.py`` 双份维护。
"""
from app.core.tracking.ad_tracking_codec import (  # noqa: F401
    AdTrackingCodec,
    REASON_BAD_HEADER,
    REASON_BAD_PAYLOAD_KIND,
    REASON_BAD_USER_JSON,
    REASON_BAD_USER_ZLIB_JSON,
    REASON_BAD_VERSION,
    REASON_CANNOT_DECODE_TOKEN,
    REASON_DECODE_FALLBACK,
    REASON_EMPTY_TOKEN,
    REASON_EXPIRED,
    REASON_INVALID,
    REASON_INVALID_SIG_OR_FORMAT,
    REASON_INVALID_SIGNATURE,
    REASON_LENGTH_MISMATCH,
    REASON_OK,
    REASON_TOO_SHORT,
    REASON_TRUNCATED,
    TOKEN_OUTER_ALPHABET,
)

__all__ = [
    "AdTrackingCodec",
    "TOKEN_OUTER_ALPHABET",
    "REASON_OK",
    "REASON_INVALID",
    "REASON_EMPTY_TOKEN",
    "REASON_CANNOT_DECODE_TOKEN",
    "REASON_DECODE_FALLBACK",
    "REASON_INVALID_SIG_OR_FORMAT",
    "REASON_TOO_SHORT",
    "REASON_INVALID_SIGNATURE",
    "REASON_TRUNCATED",
    "REASON_BAD_HEADER",
    "REASON_BAD_VERSION",
    "REASON_LENGTH_MISMATCH",
    "REASON_BAD_USER_JSON",
    "REASON_BAD_USER_ZLIB_JSON",
    "REASON_BAD_PAYLOAD_KIND",
    "REASON_EXPIRED",
]
