"""认证相关请求/响应 Schema。

供 app/api_v1/auth 使用：登录、令牌载荷、用户信息等 JSON 结构定义。

说明：用户认证，含登录、刷新令牌、登出及 JWT 校验。"""
from pydantic import Field

# Python 3.10+ 使用内置类型注解
from app.schemas.base import BaseSchema


class TokenPayload(BaseSchema):
    """
    令牌载荷模型
    
    请求载荷模型，封装批量或特殊操作的输入参数。
    """
    sub: int | None = None
    exp: int | None = None


class Token(BaseSchema):
    """
    令牌响应模型
    
    业务数据模型，用于 API 请求/响应的序列化与校验。
    """
    access_token: str
    token_type: str = "bearer"
    expires_at: int | None = None


class UserInfoResponse(BaseSchema):
    """
    用户信息响应模型
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    id: int
    username: str
    full_name: str | None = None
    email: str | None = None
    role: str
    api_enabled: bool | None = Field(False, description="客户API访问开关状态（仅客户角色有效）")
    has_publisher: bool | None = Field(False, description="是否有关联的渠道（仅客户角色有效，用于前端菜单显示）")


class LoginResponse(BaseSchema):
    """
    登录/刷新成功响应（令牌仅存 HttpOnly Cookie，不在 JSON 中返回）。
    """
    token_type: str = "bearer"
    user: UserInfoResponse
    access_token: str | None = Field(
        None,
        description="已弃用：访问令牌仅通过 HttpOnly Cookie 下发",
    )
    refresh_token: str | None = Field(
        None,
        description="已弃用：刷新令牌仅通过 HttpOnly Cookie 下发",
    )


class LoginRequest(BaseSchema):
    """
    登录请求模型
    
    API 请求体，描述客户端提交的参数格式与约束。
    """
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)


class RefreshTokenRequest(BaseSchema):
    """
    刷新令牌请求模型（兼容旧客户端；浏览器端优先使用 Cookie）。
    """
    refresh_token: str | None = Field(None, description="刷新令牌（Cookie 缺失时使用）")
