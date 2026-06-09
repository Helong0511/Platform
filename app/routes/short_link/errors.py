"""
短链接路由统一错误抛出模块。

功能说明：
- 将业务失败映射为浏览器可直接展示的 HTTP 状态码，而非 API 统一的 JSON 错误体
- ``raise_short_link_not_found``：资源不存在、已禁用、已过期等 → 404
- ``raise_short_link_bad_config``：配置错误、内部异常等 → 500

在系统中的位置：
- 被 ``handlers``、``router``、``short_code_validate`` 等短链接子模块调用

注意事项：
1. 短链接入口面向终端用户浏览器，须保留真实 404/500，便于 CDN 与爬虫识别
2. 勿改用 ``HTTPException(detail=...)`` 的默认 JSON 响应格式
"""
from fastapi import status

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception


def raise_short_link_not_found(detail: str) -> None:
    """抛出短链接 404，供浏览器直接展示未找到页。"""
    raise_api_exception(
        ErrorCode.NOT_FOUND,
        detail=detail,
        status_code=status.HTTP_404_NOT_FOUND,
    )


def raise_short_link_bad_config(detail: str) -> None:
    """抛出短链接配置/内部错误 500，区别于业务 404。"""
    raise_api_exception(
        ErrorCode.INTERNAL_ERROR,
        detail=detail,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
