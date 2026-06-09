"""
短链接路径参数（short_code）校验模块。

功能说明：
- ``validate_route_short_code``：进入重定向前校验路径段 short_code 的合法性
- 拒绝空串、纯空白及 null/undefined/none 等前端占位值，直接抛 404

在系统中的位置：
- 由 ``router`` 在查缓存/数据库前调用，减少无效请求对 Redis 与 DB 的压力

注意事项：
1. 校验失败使用 ``raise_short_link_not_found``，与「短链不存在」对外表现一致
2. 比较时对无效码做 lower()，大小写不敏感拦截
"""
from app.routes.short_link.errors import raise_short_link_not_found

_INVALID_SHORT_CODES = frozenset({"null", "undefined", "none"})


def validate_route_short_code(short_code: str) -> str:
    """校验路径短码：去空白、拒绝 null/undefined 等占位值，无效则抛 404。"""
    code = (short_code or "").strip()
    if not code or code.lower() in _INVALID_SHORT_CODES:
        raise_short_link_not_found("无效的短链接代码")
    return code
