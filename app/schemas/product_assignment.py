from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional


class ProductAssignmentBase(BaseModel):
    product_id: int
    client_id: int
    start_date: date
    end_date: Optional[date] = None


class ProductAssignmentCreate(ProductAssignmentBase):
    pass


class ProductAssignmentUpdate(BaseModel):
    end_date: Optional[date] = None


class ProductAssignmentDateUpdate(BaseModel):
    """更新产品分配历史日期的请求模型"""
    start_date: Optional[date] = Field(None, description="开始日期")
    end_date: Optional[date] = Field(None, description="结束日期（NULL表示当前有效）")


class BatchAssignmentDateUpdate(BaseModel):
    """批量更新产品分配历史日期的请求模型"""
    assignment_id: int = Field(..., description="分配记录ID")
    start_date: Optional[date] = Field(None, description="开始日期")
    end_date: Optional[date] = Field(None, description="结束日期（NULL表示当前有效）")


class BatchAssignmentsDateUpdateRequest(BaseModel):
    """批量更新产品分配历史日期的请求"""
    updates: list[BatchAssignmentDateUpdate] = Field(..., description="要更新的分配记录列表", min_length=1)


class ProductAssignmentInDBBase(ProductAssignmentBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ProductAssignmentResponse(ProductAssignmentInDBBase):
    """产品分配历史响应"""
    client_name: Optional[str] = None  # 客户名称（从关联查询中获取）
    company_name: Optional[str] = None  # 公司名称（从关联查询中获取）
    contact_person: Optional[str] = None  # 联系人（从关联查询中获取）
    phone: Optional[str] = None  # 电话（从关联查询中获取）
    user_full_name: Optional[str] = None  # 用户全名（从关联查询中获取）


class ProductAssignmentListResponse(BaseModel):
    """产品分配历史列表响应"""
    data: list[ProductAssignmentResponse]
    total: int

