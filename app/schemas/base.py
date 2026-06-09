"""Pydantic 基础 Schema 与统一 API 响应封装。

本模块提供：
- BaseSchema：全局 json 编码（datetime 带时区 ISO8601）
- PaginatedResponseBaseSchema / ResponseBaseSchema：列表分页与单条成功/失败响应
- 各业务 Schema 应继承 BaseSchema 以保持序列化行为一致。

说明：请求/响应 JSON 结构定义，供 FastAPI 校验与 OpenAPI 文档生成。"""
from datetime import datetime
from typing import Generic, TypeVar  # Generic 和 TypeVar 仍需从 typing 导入

from pydantic import BaseModel, ConfigDict

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
    """
    全项目 Pydantic 模型基类。

    配置要点：
    - from_attributes=True：支持从 SQLAlchemy ORM 对象直接构造
    - json_encoders：datetime 统一经 datetime_encoder 输出带时区的 ISO8601 字符串
    所有业务 Schema 应继承此类以保持 API 序列化行为一致。
    """
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
        json_encoders={
            datetime: datetime_encoder
        }
    )


class IDBaseSchema(BaseSchema):
    """含主键 id 的响应/详情模型基类，标识数据库已持久化记录。（详见字段 Field description）。"""
    id: int


class CreateBaseSchema(BaseSchema):
    """创建资源请求体基类；子类声明必填字段与校验规则。（详见字段 Field description）。"""
    pass


class UpdateBaseSchema(BaseSchema):
    """更新资源请求体基类；字段均为可选，仅提交需变更的列。（详见字段 Field description）。"""
    pass


class ResponseBaseSchema(BaseSchema, Generic[T]):
    """
    单条 API 响应统一包装：code + message + data。

    使用 success()/error() 类方法构造，前端可统一判断 code==200。
    """
    code: int = 200
    message: str = "success"
    data: T | None = None

    @classmethod
    def success(cls, data: T | None = None, message: str = "success") -> 'ResponseBaseSchema':
        """构造成功响应：code=200，可自定义 message 与 data 载荷。"""
        return cls(code=200, message=message, data=data)

    @classmethod
    def error(cls, code: int = 400, message: str = "error") -> 'ResponseBaseSchema':
        """构造失败响应：设置非 200 的 code 与错误 message，data 为 None。"""
        return cls(code=code, message=message, data=None)


class ListResponseBaseSchema(BaseSchema, Generic[T]):
    """非分页列表响应：含 data 与 count，适用于下拉选项等全量较短列表。"""
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
        """构造非分页列表成功响应；count 缺省时从 data 长度推断。用于 API 请求/响应序列化与 OpenAPI 文档生成。"""
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
    """
    分页列表响应：含 total、page、page_size、total_pages。

    success() 会根据 total 与 page_size 自动计算 total_pages。
    """
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
        """构造分页成功响应，根据 total 与 page_size 自动计算 total_pages。"""
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
