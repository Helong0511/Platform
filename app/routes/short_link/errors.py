"""
短链接路由统一错误抛出（保留浏览器所需的 HTTP 404/500 状态码）
"""
from fastapi import status

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception


def raise_short_link_not_found(detail: str) -> None:
    raise_api_exception(
        ErrorCode.NOT_FOUND,
        detail=detail,
        status_code=status.HTTP_404_NOT_FOUND,
    )


def raise_short_link_bad_config(detail: str) -> None:
    raise_api_exception(
        ErrorCode.INTERNAL_ERROR,
        detail=detail,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
