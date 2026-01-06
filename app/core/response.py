"""
统一响应格式模块
提供标准化的API响应格式
"""
from typing import Generic, TypeVar, Optional, Any, Dict
from pydantic import BaseModel, Field

T = TypeVar('T')


class ResponseBase(BaseModel, Generic[T]):
    """
    统一响应格式基类
    
    所有API响应都应该使用此格式，确保前端能够统一处理
    """
    success: bool = Field(description="请求是否成功")
    code: int = Field(description="错误码，0表示成功")
    message: str = Field(description="响应消息")
    data: Optional[T] = Field(default=None, description="响应数据")
    detail: Optional[str] = Field(default=None, description="详细信息（错误时使用）")
    timestamp: Optional[str] = Field(default=None, description="响应时间戳")

    @classmethod
    def success(
        cls,
        data: Optional[T] = None,
        message: str = "操作成功",
        code: int = 0
    ) -> "ResponseBase[T]":
        """
        创建成功响应
        
        Args:
            data: 响应数据
            message: 响应消息
            code: 响应码（0表示成功）
        
        Returns:
            ResponseBase实例
        """
        from datetime import datetime
        from app.core.utils import APP_TIMEZONE
        
        return cls(
            success=True,
            code=code,
            message=message,
            data=data,
            timestamp=datetime.now(APP_TIMEZONE).isoformat()
        )
    
    @classmethod
    def error(
        cls,
        code: int,
        message: str,
        detail: Optional[str] = None,
        data: Optional[Any] = None
    ) -> "ResponseBase[None]":
        """
        创建错误响应
        
        Args:
            code: 错误码
            message: 错误消息
            detail: 详细信息
            data: 额外数据
        
        Returns:
            ResponseBase实例
        """
        from datetime import datetime
        from app.core.utils import APP_TIMEZONE
        
        return cls(
            success=False,
            code=code,
            message=message,
            detail=detail,
            data=data,
            timestamp=datetime.now(APP_TIMEZONE).isoformat()
        )


class PaginatedResponse(BaseModel, Generic[T]):
    """
    分页响应格式
    
    用于返回分页列表数据
    """
    items: list[T] = Field(description="数据列表")
    total: int = Field(description="总记录数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页数量")
    total_pages: int = Field(description="总页数")
    
    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int
    ) -> "PaginatedResponse[T]":
        """
        创建分页响应
        
        Args:
            items: 数据列表
            total: 总记录数
            page: 当前页码
            page_size: 每页数量
        
        Returns:
            PaginatedResponse实例
        """
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )


def create_success_response(
    data: Optional[T] = None,
    message: str = "操作成功",
    code: int = 0
) -> ResponseBase[T]:
    """
    创建成功响应的便捷函数
    
    Args:
        data: 响应数据
        message: 响应消息
        code: 响应码
    
    Returns:
        ResponseBase实例
    """
    return ResponseBase.success(data=data, message=message, code=code)


def create_error_response(
    code: int,
    message: str,
    detail: Optional[str] = None,
    data: Optional[Any] = None
) -> ResponseBase[None]:
    """
    创建错误响应的便捷函数
    
    Args:
        code: 错误码
        message: 错误消息
        detail: 详细信息
        data: 额外数据
    
    Returns:
        ResponseBase实例
    """
    return ResponseBase.error(code=code, message=message, detail=detail, data=data)


def create_paginated_response(
    items: list[T],
    total: int,
    page: int,
    page_size: int
) -> ResponseBase[PaginatedResponse[T]]:
    """
    创建分页响应的便捷函数
    
    Args:
        items: 数据列表
        total: 总记录数
        page: 当前页码
        page_size: 每页数量
    
    Returns:
        包含PaginatedResponse的ResponseBase实例
    """
    paginated_data = PaginatedResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )
    return ResponseBase.success(data=paginated_data, message="查询成功")

