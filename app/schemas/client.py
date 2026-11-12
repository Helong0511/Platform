"""下游客户（Client）Schema：公司信息、IP 白名单、API 开关、关联用户等。

客户 = 渠道 = 商户，与 User 一对一或关联已有用户创建。

说明：请求/响应 JSON 结构定义，供 FastAPI 校验与 OpenAPI 文档生成。"""
from typing import Optional

from pydantic import BaseModel, Field, EmailStr, ConfigDict


class ClientBase(BaseModel):
    """
    客户公共字段：公司信息、IP 白名单、API/改密开关
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    company_name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    address: str | None = None
    allowed_ips: str | None = Field(None, description="IP白名单，多个IP用逗号分隔；为空则不限制。启用白名单后仅允许明确列出的 IP（包括回环地址）")
    is_active: bool | None = True
    api_enabled: bool | None = Field(False,
                                     description="是否允许API访问（开启后允许客户通过API查询产品和广告数据，并显示API对接菜单）")
    password_change_enabled: bool | None = Field(True, description="是否允许客户修改密码（开启后客户可以修改自己的密码）")
    user_id: int | None = None


class ClientCreate(ClientBase):
    """
    创建客户：可关联已有 user_id，或同时创建新登录账号
    
    创建请求体：包含新建记录所需字段，提交前由 Pydantic 自动校验类型与取值范围。
    """
    company_name: str
    # 用户ID（如果提供，则关联已有用户；如果不提供，则创建新用户）
    user_id: int | None = None

    # 创建新用户的字段（当user_id为空时使用）
    username: str | None = None  # 登录名
    password: str | None = None  # 登录密码
    email: EmailStr | None = None  # 邮箱
    full_name: str | None = None  # 全名


class ClientUpdate(ClientBase):
    """
    更新客户信息，key 为可选 UUID 字段
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    key: str | None = None  # 客户唯一标识UUID（可选，允许更新）


class ClientInDBBase(ClientBase):
    """
    数据库客户记录
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    id: int
    key: str | None = None  # 客户唯一标识UUID

    model_config = ConfigDict(from_attributes=True)


class ClientResponse(ClientInDBBase):
    """
    客户详情 API 响应，附带关联用户全名
    """
    user_full_name: Optional[str] = None
    has_api_key: Optional[bool] = Field(None, description="是否已配置 API 密钥（列表/详情脱敏）")


class ClientCreateResponse(ClientResponse):
    """创建客户响应，一次性返回明文 API 密钥。"""
    key: str | None = Field(None, description="API 密钥（仅创建时返回一次）")


class ClientListResponse(BaseModel):
    """
    客户分页列表响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    data: list[ClientResponse]
    total: int
    page: int
    page_size: int
