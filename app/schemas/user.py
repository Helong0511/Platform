"""用户（User）CRUD 与密码修改相关的 Pydantic 模型。

覆盖管理端用户创建/更新、客户创建时附带的公司信息等字段校验。

说明：请求/响应 JSON 结构定义，供 FastAPI 校验与 OpenAPI 文档生成。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.core.constants import BCRYPT_MAX_PASSWORD_LENGTH, PASSWORD_MIN_LENGTH


class UserBase(BaseModel):
    """
    用户公共字段（创建/更新共用）
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    username: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = True
    is_admin: bool | None = False
    full_name: str | None = None
    role: str | None = None


class UserCreate(UserBase):
    """
    创建用户请求；创建客户角色时可附带公司信息字段
    
    创建请求体：包含新建记录所需字段，提交前由 Pydantic 自动校验类型与取值范围。
    """
    username: str  # 登录名（必填）
    email: EmailStr  # 邮箱（必填）
    password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=BCRYPT_MAX_PASSWORD_LENGTH,
        description=f"密码（{PASSWORD_MIN_LENGTH}-{BCRYPT_MAX_PASSWORD_LENGTH}个字符，建议包含大小写字母、数字和特殊字符）",
    )
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
    """
    更新用户请求，密码可选
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    password: str | None = None


class PasswordChange(BaseModel):
    """
    修改密码请求模型
    
    业务数据模型，用于 API 请求/响应的序列化与校验。
    """
    old_password: str = Field(
        ...,
        max_length=BCRYPT_MAX_PASSWORD_LENGTH,
        description="当前密码",
    )
    new_password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=BCRYPT_MAX_PASSWORD_LENGTH,
        description=f"新密码（{PASSWORD_MIN_LENGTH}-{BCRYPT_MAX_PASSWORD_LENGTH}个字符）",
    )


class UserInDBBase(UserBase):
    """
    数据库用户记录，含主键与时间戳
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ClientInfo(BaseModel):
    """
    客户信息模型（用于 UserResponse）
    """
    id: int
    has_api_key: bool | None = Field(False, description="是否已配置 API 密钥")
    company_name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    address: str | None = None
    is_active: bool | None = True
    api_enabled: bool | None = Field(False, description="是否允许API访问")
    password_change_enabled: bool | None = Field(False, description="是否允许客户修改密码")
    has_publisher: bool | None = Field(False, description="是否有关联的渠道（用于前端菜单显示）")


class UserResponse(UserInDBBase):
    """
    用户详情 API 响应，客户角色附带 ClientInfo 与前端菜单开关
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    username: str
    role: str
    created_at: datetime | None = None
    api_enabled: bool | None = Field(False, description="客户API访问开关状态（仅客户角色有效，用于前端菜单显示）")
    password_change_enabled: bool | None = Field(False, description="客户密码修改开关状态（仅客户角色有效）")
    has_publisher: bool | None = Field(False, description="是否有关联的渠道（仅客户角色有效，用于前端菜单显示）")
    client: Optional[ClientInfo] = None  # 客户信息（仅当用户是客户角色时才有值）


class UserListResponse(BaseModel):
    """
    用户分页列表响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    data: list[UserResponse]
    total: int
    page: int
    page_size: int
