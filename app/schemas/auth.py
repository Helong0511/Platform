from pydantic import Field
# Python 3.10+ 使用内置类型注解
from datetime import datetime
from app.schemas.base import BaseSchema


class TokenPayload(BaseSchema):
    """令牌载荷模型"""
    sub: int | None = None
    exp: int | None = None


class Token(BaseSchema):
    """令牌响应模型"""
    access_token: str
    token_type: str = "bearer"
    expires_at: int | None = None


class UserInfoResponse(BaseSchema):
    """用户信息响应模型"""
    id: int
    username: str
    full_name: str | None = None
    email: str | None = None
    role: str
    api_enabled: bool | None = Field(False, description="客户API访问开关状态（仅客户角色有效）")


class LoginResponse(BaseSchema):
    """登录响应模型"""
    access_token: str
    token_type: str = "bearer"
    user: UserInfoResponse


class LoginRequest(BaseSchema):
    """登录请求模型"""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
