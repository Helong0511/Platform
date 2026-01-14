from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone
from typing import Generic, TypeVar  # Generic 和 TypeVar 仍需从 typing 导入

from app.core.utils import APP_TIMEZONE

# 定义通用类型变量
T = TypeVar('T')


def datetime_encoder(v: datetime) -> str:
    """
    将 datetime 对象编码为 ISO 8601 格式（带时区信息）
    注意：
    - 对于AdData.date等业务日期字段，存储的是系统时区的naive datetime
    - 对于created_at、updated_at等时间戳字段，存储的是应用配置时区（默认北京时间）的naive datetime
    - 如果没有时区信息，假设是应用时区（用于时间戳字段）
    """
    if v.tzinfo is None:
        # 如果没有时区信息，假设是应用时区（默认北京时间）
        # 注意：AdData.date等业务日期字段是系统时区的naive datetime，但为了API兼容性，也标记为应用时区
        v = v.replace(tzinfo=APP_TIMEZONE)
    # 使用 isoformat() 生成 ISO 8601 格式，包含时区信息
    return v.isoformat()


class BaseSchema(BaseModel):
    """基础模型，所有模型继承此类"""
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
        json_encoders={
            datetime: datetime_encoder
        }
    )


class IDBaseSchema(BaseSchema):
    """包含ID字段的基础模型"""
    id: int


class CreateBaseSchema(BaseSchema):
    """创建资源的基础模型"""
    pass


class UpdateBaseSchema(BaseSchema):
    """更新资源的基础模型"""
    pass


class ResponseBaseSchema(BaseSchema, Generic[T]):
    """API响应通用模型"""
    code: int = 200
    message: str = "success"
    data: T | None = None

    @classmethod
    def success(cls, data: T | None = None, message: str = "success") -> 'ResponseBaseSchema':
        return cls(code=200, message=message, data=data)

    @classmethod
    def error(cls, code: int = 400, message: str = "error") -> 'ResponseBaseSchema':
        return cls(code=code, message=message, data=None)


class ListResponseBaseSchema(BaseSchema, Generic[T]):
    """列表响应通用模型（非分页，但包含数据条数）"""
    code: int = 200
    message: str = "success"
    data: T | None = None
    count: int = 0  # 数据条数

    @classmethod
    def success(
            cls,
            data: T | None = None,
            count: int | None = None,
            message: str = "success"
    ) -> 'ListResponseBaseSchema':
        # 如果count为None，尝试从data计算
        if count is None:
            if isinstance(data, list):
                count = len(data)
            else:
                count = 0
        return cls(
            code=200,
            message=message,
            data=data,
            count=count
        )


class PaginatedResponseBaseSchema(BaseSchema, Generic[T]):
    """分页响应通用模型"""
    code: int = 200
    message: str = "success"
    data: T | None = None
    total: int = 0
    page: int = 1
    page_size: int = 10
    total_pages: int = 0

    @classmethod
    def success(
            cls,
            data: T | None = None,
            total: int = 0,
            page: int = 1,
            page_size: int = 10,
            message: str = "success"
    ) -> 'PaginatedResponseBaseSchema':
        total_pages = (total + page_size - 1) // page_size
        return cls(
            code=200,
            message=message,
            data=data,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
