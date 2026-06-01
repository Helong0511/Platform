"""短链接路径参数校验（避免 null/undefined 等无效短码进入业务逻辑）"""
from app.routes.short_link.errors import raise_short_link_not_found

_INVALID_SHORT_CODES = frozenset({"null", "undefined", "none"})


def validate_route_short_code(short_code: str) -> str:
    code = (short_code or "").strip()
    if not code or code.lower() in _INVALID_SHORT_CODES:
        raise_short_link_not_found("无效的短链接代码")
    return code
