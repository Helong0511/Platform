"""
短链接服务API端点
提供短链接的生成、重定向、管理功能
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Path, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.short_link.generator import (
    generate_short_code,
    generate_short_code_from_id,
    generate_unique_short_code
)
from app.models.models import User, UserRole, ShortLink
from app.schemas.short_link import (
    ShortLinkCreate,
    ShortLinkUpdate,
    ShortLinkResponse,
    ShortLinkListResponse,
    ShortLinkStatsResponse
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

# 创建路由实例
router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== 短链接工具接口（必须在动态路径之前） ====================

@router.get("/generate-code",
            summary="生成短链接代码")
async def generate_short_code(
    db: AsyncSession = Depends(get_db)
):
    """生成唯一的短链接代码（公开接口，用于前端自动生成）"""
    from app.core.short_link.generator import generate_short_code, generate_unique_short_code
    
    # 获取所有已存在的代码
    result = await db.execute(select(ShortLink.short_code))
    existing_codes = {row[0] for row in result.all()}
    
    # 生成唯一代码（尝试最多100次）
    code = generate_unique_short_code(existing_codes, length=6, max_attempts=100)
    
    if not code:
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail="生成短链接代码失败，请稍后重试"
        )
    
    return ResponseBaseSchema.success(data={"short_code": code})


@router.get("/check-code/{short_code}",
            summary="检查短链接代码是否存在")
async def check_short_code(
    short_code: str = Path(..., description="短链接代码"),
    db: AsyncSession = Depends(get_db)
):
    """检查短链接代码是否存在（公开接口，用于前端验证）"""
    result = await db.execute(
        select(ShortLink).where(ShortLink.short_code == short_code)
    )
    exists = result.scalars().first() is not None
    
    return ResponseBaseSchema.success(data={"exists": exists, "short_code": short_code})


# ==================== 短链接重定向 ====================

@router.get("/{short_code}", summary="短链接重定向")
async def redirect_short_link(
    short_code: str = Path(..., description="短链接代码"),
    db: AsyncSession = Depends(get_db)
):
    """
    短链接重定向（公开接口，无需认证）
    访问短链接时自动重定向到原始URL
    """
    # 查询短链接
    result = await db.execute(
        select(ShortLink).where(ShortLink.short_code == short_code)
    )
    short_link = result.scalars().first()
    
    if not short_link:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"短链接不存在: {short_code}"
        )
    
    # 检查是否激活
    if not short_link.is_active:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail="短链接已禁用"
        )
    
    # 检查是否过期
    if short_link.expires_at:
        # 确保 expires_at 是 aware datetime（有时区信息）
        expires_at = short_link.expires_at
        if expires_at.tzinfo is None:
            # 如果是 naive datetime，假设它是 UTC 时区（数据库通常存储 UTC 时间）
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            # 如果已经是 aware datetime，转换为 UTC 以确保一致性
            expires_at = expires_at.astimezone(timezone.utc)
        
        now = datetime.now(timezone.utc)
        if expires_at < now:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="短链接已过期"
            )
    
    # 增加点击次数
    try:
        short_link.click_count += 1
        await db.commit()
    except Exception as e:
        logger.warning(f"更新短链接点击次数失败: {str(e)}")
        # 点击次数更新失败不影响重定向
    
    # 重定向到原始URL
    return RedirectResponse(url=short_link.original_url, status_code=302)


# ==================== 短链接管理 ====================

@router.post("/", 
             response_model=ResponseBaseSchema[ShortLinkResponse],
             summary="创建短链接")
async def create_short_link(
    request: Request,
    link_in: ShortLinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建短链接"""
    # 如果提供了自定义短链接代码，检查是否已存在
    if link_in.short_code:
        result = await db.execute(
            select(ShortLink).where(ShortLink.short_code == link_in.short_code)
        )
        existing = result.scalars().first()
        if existing:
            raise_api_exception(
                ErrorCode.RESOURCE_ALREADY_EXISTS,
                detail=f"短链接代码 '{link_in.short_code}' 已存在，请使用其他代码"
            )
        short_code = link_in.short_code
    else:
        # 自动生成短链接代码
        # 先尝试从ID生成（需要先插入获取ID）
        # 如果失败，使用随机生成
        short_code = None
    
    # 创建短链接
    short_link = ShortLink(
        original_url=link_in.original_url,
        title=link_in.title,
        description=link_in.description,
        short_code=short_code or "temp",  # 临时代码，稍后更新
        created_by=current_user.id,
        is_active=link_in.is_active,
        expires_at=link_in.expires_at,
        click_count=0
    )
    
    try:
        db.add(short_link)
        await db.flush()  # 先flush以获取ID
        
        # 如果没有提供自定义代码，生成唯一代码
        if not link_in.short_code:
            # 获取所有已存在的代码
            result = await db.execute(select(ShortLink.short_code))
            existing_codes = {row[0] for row in result.all()}
            
            # 尝试从ID生成
            code_from_id = generate_short_code_from_id(short_link.id, min_length=4)
            if code_from_id not in existing_codes:
                short_link.short_code = code_from_id
            else:
                # 如果ID生成的代码已存在，使用随机生成
                unique_code = generate_unique_short_code(existing_codes, length=6)
                if not unique_code:
                    raise_api_exception(
                        ErrorCode.OPERATION_FAILED,
                        detail="生成短链接代码失败，请稍后重试"
                    )
                short_link.short_code = unique_code
        
        await db.commit()
        await db.refresh(short_link)
        
        # 构建完整的短链接URL
        base_url = str(request.base_url).rstrip('/')
        short_url = f"{base_url}/s/{short_link.short_code}"
        
        response_data = ShortLinkResponse.model_validate(short_link)
        response_data.short_url = short_url
        
        logger.info(f"短链接创建成功: {short_link.short_code} -> {short_link.original_url}")
        return ResponseBaseSchema.success(data=response_data)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"创建短链接失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建短链接失败: {str(e)}"
        )


@router.get("/", 
            response_model=PaginatedResponseBaseSchema[list[ShortLinkResponse]],
            summary="获取短链接列表")
async def get_short_links(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    search: Optional[str] = Query(None, description="搜索关键词（标题、URL、代码）"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    created_by: Optional[int] = Query(None, description="创建者ID过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取短链接列表"""
    # 权限检查：管理员可以查看所有，普通用户只能查看自己的
    query = select(ShortLink)
    
    if current_user.role != UserRole.ADMIN:
        query = query.where(ShortLink.created_by == current_user.id)
    
    # 应用过滤条件
    conditions = []
    
    if is_active is not None:
        conditions.append(ShortLink.is_active == is_active)
    
    if created_by:
        conditions.append(ShortLink.created_by == created_by)
    
    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                ShortLink.title.like(search_pattern),
                ShortLink.original_url.like(search_pattern),
                ShortLink.short_code.like(search_pattern),
                ShortLink.description.like(search_pattern)
            )
        )
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # 排序：最新的在前
    query = query.order_by(ShortLink.created_at.desc())
    
    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    # 执行查询
    result = await db.execute(query)
    short_links = result.scalars().all()
    
    # 构建完整的短链接URL
    base_url = str(request.base_url).rstrip('/')
    links_data = []
    for link in short_links:
        link_data = ShortLinkResponse.model_validate(link)
        link_data.short_url = f"{base_url}/s/{link.short_code}"
        links_data.append(link_data)
    
    return PaginatedResponseBaseSchema.success(
        data=links_data,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{link_id}/detail",
            response_model=ResponseBaseSchema[ShortLinkResponse],
            summary="获取短链接详情")
async def get_short_link_detail(
    request: Request,
    link_id: int = Path(..., ge=1, description="短链接ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取短链接详情"""
    result = await db.execute(
        select(ShortLink).where(ShortLink.id == link_id)
    )
    short_link = result.scalars().first()
    
    if not short_link:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"短链接ID {link_id} 不存在"
        )
    
    # 权限检查
    if current_user.role != UserRole.ADMIN:
        if short_link.created_by != current_user.id:
            raise_api_exception(
                ErrorCode.ACCESS_DENIED,
                detail="无权访问该短链接"
            )
    
    # 构建完整的短链接URL
    base_url = str(request.base_url).rstrip('/')
    response_data = ShortLinkResponse.model_validate(short_link)
    response_data.short_url = f"{base_url}/s/{short_link.short_code}"
    
    return ResponseBaseSchema.success(data=response_data)


@router.put("/{link_id}",
            response_model=ResponseBaseSchema[ShortLinkResponse],
            summary="更新短链接")
async def update_short_link(
    request: Request,
    link_id: int = Path(..., ge=1, description="短链接ID"),
    link_in: ShortLinkUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新短链接"""
    result = await db.execute(
        select(ShortLink).where(ShortLink.id == link_id)
    )
    short_link = result.scalars().first()
    
    if not short_link:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"短链接ID {link_id} 不存在"
        )
    
    # 权限检查
    if current_user.role != UserRole.ADMIN:
        if short_link.created_by != current_user.id:
            raise_api_exception(
                ErrorCode.ACCESS_DENIED,
                detail="无权修改该短链接"
            )
    
    # 更新字段
    update_data = link_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(short_link, key, value)
    
    try:
        await db.commit()
        await db.refresh(short_link)
        
        # 构建完整的短链接URL
        base_url = str(request.base_url).rstrip('/')
        response_data = ShortLinkResponse.model_validate(short_link)
        response_data.short_url = f"{base_url}/s/{short_link.short_code}"
        
        logger.info(f"短链接更新成功: {short_link.short_code}")
        return ResponseBaseSchema.success(data=response_data)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"更新短链接失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新短链接失败: {str(e)}"
        )


@router.delete("/{link_id}",
                response_model=ResponseBaseSchema[dict],
                summary="删除短链接")
async def delete_short_link(
    link_id: int = Path(..., ge=1, description="短链接ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除短链接"""
    result = await db.execute(
        select(ShortLink).where(ShortLink.id == link_id)
    )
    short_link = result.scalars().first()
    
    if not short_link:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"短链接ID {link_id} 不存在"
        )
    
    # 权限检查
    if current_user.role != UserRole.ADMIN:
        if short_link.created_by != current_user.id:
            raise_api_exception(
                ErrorCode.ACCESS_DENIED,
                detail="无权删除该短链接"
            )
    
    try:
        from sqlalchemy import delete
        await db.execute(delete(ShortLink).where(ShortLink.id == link_id))
        await db.commit()
        logger.info(f"短链接删除成功: {link_id}")
        return ResponseBaseSchema.success(data={"message": "短链接已删除"})
    except Exception as e:
        await db.rollback()
        logger.error(f"删除短链接失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除短链接失败: {str(e)}"
        )


@router.get("/stats/summary",
            response_model=ResponseBaseSchema[ShortLinkStatsResponse],
            summary="获取短链接统计")
async def get_short_link_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取短链接统计信息"""
    query = select(ShortLink)
    
    # 权限检查：普通用户只能查看自己的统计
    if current_user.role != UserRole.ADMIN:
        query = query.where(ShortLink.created_by == current_user.id)
    
    # 计算总数
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total_links = total_result.scalar() or 0
    
    # 计算总点击次数
    click_result = await db.execute(
        select(func.sum(ShortLink.click_count)).select_from(query.subquery())
    )
    total_clicks = click_result.scalar() or 0
    
    # 计算激活数量
    active_query = query.where(ShortLink.is_active == True)
    active_result = await db.execute(select(func.count()).select_from(active_query.subquery()))
    active_links = active_result.scalar() or 0
    
    # 计算过期数量
    now = datetime.now(timezone.utc)
    expired_query = query.where(
        and_(
            ShortLink.expires_at.isnot(None),
            ShortLink.expires_at < now
        )
    )
    expired_result = await db.execute(select(func.count()).select_from(expired_query.subquery()))
    expired_links = expired_result.scalar() or 0
    
    return ResponseBaseSchema.success(data=ShortLinkStatsResponse(
        total_links=total_links,
        total_clicks=total_clicks,
        active_links=active_links,
        expired_links=expired_links
    ))

