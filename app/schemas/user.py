from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


class UserBase(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = True
    is_admin: bool | None = False
    full_name: str | None = None
    role: str | None = None


class UserCreate(UserBase):
    username: str  # 登录名（必填）
    email: EmailStr  # 邮箱（必填）
    password: str = Field(..., min_length=6, max_length=72,
                          description="密码（6-72个字符，建议包含大小写字母、数字和特殊字符）")
    full_name: str | None = None  # 全名（可选）
    role: str | None = "client"  # 角色，默认为客户
    login_restricted: bool | None = False  # 登录限制（可选，默认False）
    login_message: str | None = None  # 登录提示消息（可选）

    # 客户信息字段（可选，创建客户用户时需要）
    company_name: str | None = None  # 公司名称
    contact_person: str | None = None  # 联系人
    phone: str | None = None  # 联系电话
    address: str | None = None  # 地址


class UserUpdate(UserBase):
    password: str | None = None


class PasswordChange(BaseModel):
    """修改密码请求模型"""
    old_password: str = Field(..., min_length=6, max_length=72, description="当前密码")
    new_password: str = Field(..., min_length=6, max_length=72, description="新密码（6-72个字符）")


class UserInDBBase(UserBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ClientInfo(BaseModel):
    """客户信息模型（用于UserResponse）"""
    id: int
    key: str | None = None  # 客户唯一标识UUID
    company_name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    address: str | None = None
    is_active: bool | None = True
    api_enabled: bool | None = Field(False, description="是否允许API访问")
    password_change_enabled: bool | None = Field(False, description="是否允许客户修改密码")
    has_publisher: bool | None = Field(False, description="是否有关联的渠道（用于前端菜单显示）")


class UserResponse(UserInDBBase):
    username: str
    role: str
    created_at: datetime | None = None
    api_enabled: bool | None = Field(False, description="客户API访问开关状态（仅客户角色有效，用于前端菜单显示）")
    password_change_enabled: bool | None = Field(False, description="客户密码修改开关状态（仅客户角色有效）")
    has_publisher: bool | None = Field(False, description="是否有关联的渠道（仅客户角色有效，用于前端菜单显示）")
    client: Optional[ClientInfo] = None  # 客户信息（仅当用户是客户角色时才有值）


class UserListResponse(BaseModel):
    data: list[UserResponse]
    total: int
    page: int
    page_size: int
