"""产品-客户归属时间段（ProductAssignment）Schema。

记录某产品在指定日期区间内归属哪个下游客户，用于历史数据归属与报表切分。

说明：请求/响应 JSON 结构定义，供 FastAPI 校验与 OpenAPI 文档生成。"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class ProductAssignmentBase(BaseModel):
    """
    产品归属时间段基础字段
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    product_id: int
    client_id: int
    start_date: date
    end_date: Optional[date] = None


class ProductAssignmentCreate(ProductAssignmentBase):
    """
    创建产品归属记录请求
    
    创建请求体：包含新建记录所需字段，提交前由 Pydantic 自动校验类型与取值范围。
    """
    pass


class ProductAssignmentUpdate(BaseModel):
    """
    更新归属结束日期（NULL 表示当前仍有效）
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    end_date: Optional[date] = None


class ProductAssignmentDateUpdate(BaseModel):
    """
    更新产品分配历史日期的请求模型
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    start_date: Optional[date] = Field(None, description="开始日期")
    end_date: Optional[date] = Field(None, description="结束日期（NULL表示当前有效）")


class BatchAssignmentDateUpdate(BaseModel):
    """
    批量更新产品分配历史日期的请求模型
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    assignment_id: int = Field(..., description="分配记录ID")
    start_date: Optional[date] = Field(None, description="开始日期")
    end_date: Optional[date] = Field(None, description="结束日期（NULL表示当前有效）")


class BatchAssignmentsDateUpdateRequest(BaseModel):
    """
    批量更新产品分配历史日期的请求
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    updates: list[BatchAssignmentDateUpdate] = Field(..., description="要更新的分配记录列表", min_length=1)


class ProductAssignmentInDBBase(ProductAssignmentBase):
    """
    数据库归属记录，含主键与时间戳
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductAssignmentResponse(ProductAssignmentInDBBase):
    """
    产品分配历史响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    client_name: Optional[str] = None  # 客户名称（从关联查询中获取）
    company_name: Optional[str] = None  # 公司名称（从关联查询中获取）
    contact_person: Optional[str] = None  # 联系人（从关联查询中获取）
    phone: Optional[str] = None  # 电话（从关联查询中获取）
    user_full_name: Optional[str] = None  # 用户全名（从关联查询中获取）


class ProductAssignmentListResponse(BaseModel):
    """
    产品分配历史列表响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    data: list[ProductAssignmentResponse]
    total: int
