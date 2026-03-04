"""
令牌刷新端点
提供刷新访问令牌的功能
"""
import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.security import JWTUtils
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.schemas.auth import LoginResponse, UserInfoResponse, RefreshTokenRequest
from app.models.models import User, UserRole, Publisher
from sqlalchemy.future import select
from sqlalchemy import func, and_
from sqlalchemy.orm import selectinload

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/refresh", response_model=LoginResponse, summary="刷新访问令牌")
async def refresh_token(
    request: Request,
    token_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    使用刷新令牌获取新的访问令牌
    
    功能说明：
    - 验证刷新令牌的有效性
    - 检查用户状态
    - 生成新的访问令牌和刷新令牌
    - 返回新的令牌对
    
    请求格式：
    - Content-Type: application/json
    - Body: {"refresh_token": "..."}
    
    安全特性：
    - 验证刷新令牌签名
    - 检查刷新令牌类型
    - 验证用户状态
    - 支持令牌黑名单（可选）
    
    Args:
        request: FastAPI请求对象
        refresh_token: 刷新令牌字符串
        db: 数据库会话
    
    Returns:
        LoginResponse: 包含新的访问令牌、刷新令牌和用户信息
    
    Raises:
        HTTPException:
            - 401: 刷新令牌无效或过期
            - 403: 用户被禁用或限制登录
    """
    try:
        # 从请求体中获取刷新令牌
        refresh_token = token_data.refresh_token
        
        # 验证刷新令牌
        payload = await JWTUtils.verify_token(refresh_token, db=db)
        
        # 检查令牌类型
        token_type = payload.get("type")
        if token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的刷新令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 获取用户ID
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无法从令牌中获取用户ID",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 查询用户（如果是客户角色，同时加载客户信息）
        result = await db.execute(
            select(User)
            .options(selectinload(User.clients))
            .where(User.id == int(user_id))
        )
        user = result.scalars().first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 检查用户状态
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="用户已被禁用",
            )
        
        if user.login_restricted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=user.login_message or "登录已被限制",
            )
        
        # 生成新的访问令牌和刷新令牌
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        new_access_token = JWTUtils.create_access_token(
            user.id, expires_delta=access_token_expires
        )
        new_refresh_token = JWTUtils.create_refresh_token(
            user.id, expires_delta=timedelta(days=7)
        )
        
        # 获取客户相关信息（如果是客户角色）
        api_enabled = False
        has_publisher = False
        if user.role == UserRole.CLIENT and user.clients:
            client = user.clients[0]
            if client:
                api_enabled = client.api_enabled
                publisher_check = await db.execute(
                    select(func.count(Publisher.id)).where(
                        and_(
                            Publisher.client_id == client.id,
                            Publisher.is_active == True
                        )
                    )
                )
                publisher_count = publisher_check.scalar() or 0
                has_publisher = publisher_count > 0
        
        # 构建响应
        response_data = {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role.value,
                "api_enabled": api_enabled,
                "has_publisher": has_publisher
            }
        }
        
        # 设置 HttpOnly Cookie
        json_response = JSONResponse(content=response_data)
        json_response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=settings.is_production,
            samesite="lax",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
        logger.info(f"用户 {user.username} 刷新令牌成功")
        return json_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刷新令牌失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌失败，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
