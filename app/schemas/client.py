from pydantic import BaseModel, Field, EmailStr


class ClientBase(BaseModel):
    company_name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    address: str | None = None
    allowed_ips: str | None = Field(None, description="IP白名单，多个IP用逗号分隔，为空则不限制。127.0.0.1始终允许")
    is_active: bool | None = True
    api_enabled: bool | None = Field(False, description="是否允许API访问（开启后允许客户通过API查询产品和广告数据，并显示API对接菜单）")
    password_change_enabled: bool | None = Field(True, description="是否允许客户修改密码（开启后客户可以修改自己的密码）")
    user_id: int | None = None


class ClientCreate(ClientBase):
    company_name: str
    # 用户ID（如果提供，则关联已有用户；如果不提供，则创建新用户）
    user_id: int | None = None

    # 创建新用户的字段（当user_id为空时使用）
    username: str | None = None  # 登录名
    password: str | None = None  # 登录密码
    email: EmailStr | None = None  # 邮箱
    full_name: str | None = None  # 全名


class ClientUpdate(ClientBase):
    key: str | None = None  # 客户唯一标识UUID（可选，允许更新）


class ClientInDBBase(ClientBase):
    id: int
    key: str | None = None  # 客户唯一标识UUID

    class Config:
        from_attributes = True


class ClientResponse(ClientInDBBase):
    pass


class ClientListResponse(BaseModel):
    data: list[ClientResponse]
    total: int
    page: int
    page_size: int
