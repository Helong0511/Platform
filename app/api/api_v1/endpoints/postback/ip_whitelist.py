"""
Postback IP 白名单管理接口
用于管理允许接收 postback 数据的 IP 地址列表
"""
import logging
import ipaddress
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Request, Query, Depends, HTTPException, Path
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.constants import MAX_PAGE_SIZE
from app.core.pagination import paginate_query
from app.models.models import PostbackIpWhitelist, User
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.core.security import require_admin

# 创建路由实例
router = APIRouter()
logger = logging.getLogger(__name__)


# ====== Schema 定义 ======

class PostbackIpWhitelistCreate(BaseModel):
    """创建 IP 白名单请求"""
    ip_address: str = Field(..., description="IP地址（支持IPv4和IPv6）")
    description: Optional[str] = Field(None, max_length=255, description="IP地址描述/备注")
    is_active: bool = Field(True, description="是否启用")
    
    @validator('ip_address')
    def validate_ip_address(cls, v):
        """验证 IP 地址格式"""
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            raise ValueError(f"无效的 IP 地址格式: {v}")


class PostbackIpWhitelistUpdate(BaseModel):
    """更新 IP 白名单请求"""
    ip_address: Optional[str] = Field(None, description="IP地址（支持IPv4和IPv6）")
    description: Optional[str] = Field(None, max_length=255, description="IP地址描述/备注")
    is_active: Optional[bool] = Field(None, description="是否启用")
    
    @validator('ip_address')
    def validate_ip_address(cls, v):
        """验证 IP 地址格式"""
        if v is None:
            return v
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            raise ValueError(f"无效的 IP 地址格式: {v}")


class PostbackIpWhitelistResponse(BaseModel):
    """IP 白名单响应"""
    id: int
    ip_address: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PostbackIpWhitelistBatchCreate(BaseModel):
    """批量创建 IP 白名单请求"""
    ip_addresses: List[str] = Field(..., description="IP地址列表（支持IPv4和IPv6）")
    description: Optional[str] = Field(None, max_length=255, description="IP地址描述/备注（应用于所有IP）")
    is_active: bool = Field(True, description="是否启用（应用于所有IP）")
    
    @validator('ip_addresses')
    def validate_ip_addresses(cls, v):
        """验证 IP 地址列表格式"""
        if not v or len(v) == 0:
            raise ValueError("IP地址列表不能为空")
        if len(v) > 100:
            raise ValueError("一次最多只能添加100个IP地址")
        
        validated_ips = []
        for ip in v:
            if not ip or not ip.strip():
                continue
            trimmed_ip = ip.strip()
            try:
                ipaddress.ip_address(trimmed_ip)
                validated_ips.append(trimmed_ip)
            except ValueError:
                raise ValueError(f"无效的 IP 地址格式: {trimmed_ip}")
        
        if len(validated_ips) == 0:
            raise ValueError("没有有效的IP地址")
        
        # 去重
        unique_ips = list(dict.fromkeys(validated_ips))
        return unique_ips


class PostbackIpWhitelistBatchCreateResponse(BaseModel):
    """批量创建 IP 白名单响应"""
    success_count: int = Field(..., description="成功创建的数量")
    failed_count: int = Field(..., description="创建失败的数量")
    total_count: int = Field(..., description="总数量")
    created_items: List[PostbackIpWhitelistResponse] = Field(..., description="成功创建的记录")
    failed_items: List[dict] = Field(default_factory=list, description="创建失败的记录（包含IP和错误信息）")
    
    class Config:
        from_attributes = True


# ====== API 端点 ======

@router.get("/postback/ip-whitelist",
            response_model=PaginatedResponseBaseSchema[list[PostbackIpWhitelistResponse]],
            summary="查询 Postback IP 白名单列表（管理员）")
async def get_ip_whitelist(
    request: Request,
    ip_address: Optional[str] = Query(None, description="IP地址（模糊搜索）"),
    is_active: Optional[bool] = Query(None, description="是否启用"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    查询 Postback IP 白名单列表（仅管理员）
    """
    
    try:
        # 构建查询
        query = select(PostbackIpWhitelist)
        
        # 应用过滤条件
        conditions = []
        
        if ip_address:
            conditions.append(PostbackIpWhitelist.ip_address.like(f"%{ip_address}%"))
        if is_active is not None:
            conditions.append(PostbackIpWhitelist.is_active == is_active)
        
        # 使用通用分页查询函数
        whitelist_items, total = await paginate_query(
            db=db,
            query=query,
            page=page,
            page_size=page_size,
            order_by=PostbackIpWhitelist.created_at.desc(),
            conditions=conditions if conditions else None,
            model_class=PostbackIpWhitelist
        )
        
        logger.info(
            f"管理员 {current_user.username} 查询 IP 白名单: "
            f"total={total}, page={page}, page_size={page_size}"
        )
        
        return PaginatedResponseBaseSchema.success(
            data=[PostbackIpWhitelistResponse.model_validate(item) for item in whitelist_items],
            total=total,
            page=page,
            page_size=page_size,
            message=f"成功获取 {len(whitelist_items)} 条记录，共 {total} 条"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询 IP 白名单失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"查询失败：{str(e)}"
        )


@router.post("/postback/ip-whitelist",
             response_model=ResponseBaseSchema[PostbackIpWhitelistResponse],
             summary="创建 Postback IP 白名单（管理员）")
async def create_ip_whitelist(
    request: Request,
    data: PostbackIpWhitelistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    创建 Postback IP 白名单（仅管理员）
    """
    
    try:
        # 检查 IP 是否已存在
        existing = await db.execute(
            select(PostbackIpWhitelist).where(
                PostbackIpWhitelist.ip_address == data.ip_address
            )
        )
        if existing.scalars().first():
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail=f"IP 地址 {data.ip_address} 已存在于白名单中"
            )
        
        # 创建新记录
        whitelist_item = PostbackIpWhitelist(
            ip_address=data.ip_address,
            description=data.description,
            is_active=data.is_active
        )
        
        db.add(whitelist_item)
        await db.commit()
        await db.refresh(whitelist_item)
        
        logger.info(
            f"管理员 {current_user.username} 创建 IP 白名单: "
            f"ip_address={data.ip_address}, id={whitelist_item.id}"
        )
        
        return ResponseBaseSchema.success(
            data=PostbackIpWhitelistResponse.model_validate(whitelist_item),
            message="IP 白名单创建成功"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建 IP 白名单失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建失败：{str(e)}"
        )


@router.put("/postback/ip-whitelist/{whitelist_id}",
            response_model=ResponseBaseSchema[PostbackIpWhitelistResponse],
            summary="更新 Postback IP 白名单（管理员）")
async def update_ip_whitelist(
    request: Request,
    whitelist_id: int = Path(..., ge=1, description="白名单ID"),
    data: PostbackIpWhitelistUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    更新 Postback IP 白名单（仅管理员）
    """
    
    try:
        # 查询记录
        result = await db.execute(
            select(PostbackIpWhitelist).where(PostbackIpWhitelist.id == whitelist_id)
        )
        whitelist_item = result.scalars().first()
        
        if not whitelist_item:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"IP 白名单 ID {whitelist_id} 不存在"
            )
        
        # 如果更新 IP 地址，检查是否与其他记录冲突
        if data.ip_address and data.ip_address != whitelist_item.ip_address:
            existing = await db.execute(
                select(PostbackIpWhitelist).where(
                    PostbackIpWhitelist.ip_address == data.ip_address,
                    PostbackIpWhitelist.id != whitelist_id
                )
            )
            if existing.scalars().first():
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=f"IP 地址 {data.ip_address} 已存在于其他白名单记录中"
                )
        
        # 更新字段
        if data.ip_address is not None:
            whitelist_item.ip_address = data.ip_address
        if data.description is not None:
            whitelist_item.description = data.description
        if data.is_active is not None:
            whitelist_item.is_active = data.is_active
        
        await db.commit()
        await db.refresh(whitelist_item)
        
        logger.info(
            f"管理员 {current_user.username} 更新 IP 白名单: "
            f"id={whitelist_id}, ip_address={whitelist_item.ip_address}"
        )
        
        return ResponseBaseSchema.success(
            data=PostbackIpWhitelistResponse.model_validate(whitelist_item),
            message="IP 白名单更新成功"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新 IP 白名单失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新失败：{str(e)}"
        )


@router.post("/postback/ip-whitelist/batch",
             response_model=ResponseBaseSchema[PostbackIpWhitelistBatchCreateResponse],
             summary="批量创建 Postback IP 白名单（管理员）")
async def batch_create_ip_whitelist(
    request: Request,
    data: PostbackIpWhitelistBatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    批量创建 Postback IP 白名单（仅管理员）
    支持一次添加多个IP地址，自动跳过已存在的IP
    """
    
    try:
        created_items = []
        failed_items = []
        
        # 查询所有已存在的IP地址
        existing_result = await db.execute(
            select(PostbackIpWhitelist.ip_address)
        )
        existing_ips = {row.ip_address.strip() for row in existing_result.all()}
        
        # 批量创建
        for ip_address in data.ip_addresses:
            trimmed_ip = ip_address.strip()
            
            # 检查是否已存在
            if trimmed_ip in existing_ips:
                failed_items.append({
                    "ip_address": trimmed_ip,
                    "error": "IP地址已存在于白名单中"
                })
                continue
            
            try:
                # 创建新记录
                whitelist_item = PostbackIpWhitelist(
                    ip_address=trimmed_ip,
                    description=data.description,
                    is_active=data.is_active
                )
                
                db.add(whitelist_item)
                # 添加到已存在集合，避免同一批次重复
                existing_ips.add(trimmed_ip)
                created_items.append(whitelist_item)
                
            except Exception as e:
                failed_items.append({
                    "ip_address": trimmed_ip,
                    "error": str(e)
                })
                logger.warning(f"创建IP白名单失败: {trimmed_ip}, 错误: {str(e)}")
        
        # 提交所有成功的记录
        if created_items:
            await db.commit()
            # 刷新所有创建的记录
            for item in created_items:
                await db.refresh(item)
        
        success_count = len(created_items)
        failed_count = len(failed_items)
        total_count = len(data.ip_addresses)
        
        logger.info(
            f"管理员 {current_user.username} 批量创建 IP 白名单: "
            f"总数={total_count}, 成功={success_count}, 失败={failed_count}"
        )
        
        return ResponseBaseSchema.success(
            data=PostbackIpWhitelistBatchCreateResponse(
                success_count=success_count,
                failed_count=failed_count,
                total_count=total_count,
                created_items=[PostbackIpWhitelistResponse.model_validate(item) for item in created_items],
                failed_items=failed_items
            ),
            message=f"批量创建完成：成功 {success_count} 个，失败 {failed_count} 个，共 {total_count} 个"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"批量创建 IP 白名单失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"批量创建失败：{str(e)}"
        )


@router.delete("/postback/ip-whitelist/{whitelist_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除 Postback IP 白名单（管理员）")
async def delete_ip_whitelist(
    request: Request,
    whitelist_id: int = Path(..., ge=1, description="白名单ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    删除 Postback IP 白名单（仅管理员）
    """
    
    try:
        # 查询记录
        result = await db.execute(
            select(PostbackIpWhitelist).where(PostbackIpWhitelist.id == whitelist_id)
        )
        whitelist_item = result.scalars().first()
        
        if not whitelist_item:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"IP 白名单 ID {whitelist_id} 不存在"
            )
        
        ip_address = whitelist_item.ip_address
        
        # 删除记录
        await db.delete(whitelist_item)
        await db.commit()
        
        logger.info(
            f"管理员 {current_user.username} 删除 IP 白名单: "
            f"id={whitelist_id}, ip_address={ip_address}"
        )
        
        return ResponseBaseSchema.success(
            data={"id": whitelist_id, "ip_address": ip_address},
            message="IP 白名单删除成功"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除 IP 白名单失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除失败：{str(e)}"
        )
