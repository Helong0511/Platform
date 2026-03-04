"""
渠道服务层
封装渠道相关的业务逻辑
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, String, or_, and_
from sqlalchemy.orm import selectinload, joinedload

from app.models.models import Publisher, Client, User, UserRole, OfferPublisherAssignment
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.audit_log import log_user_action
from app.core.validation import validate_postback_url_placeholders
from app.core.infrastructure.cache import CacheInvalidator
import logging

logger = logging.getLogger(__name__)


class PublisherService(BaseService[Publisher]):
    """渠道服务"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(db, Publisher)
    
    async def get_publisher_by_id(
        self,
        publisher_id: int,
        current_user: User,
        include_client: bool = True
    ) -> Publisher:
        """
        根据ID获取渠道详情
        
        Args:
            publisher_id: 渠道ID
            current_user: 当前用户
            include_client: 是否包含客户信息
        
        Returns:
            Publisher: 渠道对象
        """
        query = select(Publisher).where(Publisher.id == publisher_id)
        
        # 如果需要客户信息，使用selectinload优化查询
        if include_client:
            query = query.options(selectinload(Publisher.client).selectinload(Client.user))
        
        result = await self.db.execute(query)
        publisher = result.scalar_one_or_none()
        
        if not publisher:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"渠道ID {publisher_id} 不存在"
            )
        
        return publisher
    
    async def get_publishers(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> tuple[List[Publisher], int]:
        """
        获取渠道列表（支持分页、筛选、搜索）
        
        Args:
            current_user: 当前用户
            page: 页码
            page_size: 每页数量
            search: 搜索关键词
            is_active: 激活状态过滤
        
        Returns:
            tuple: (渠道列表, 总数)
        """
        query = select(Publisher)
        
        # 筛选条件
        conditions = []
        
        if search:
            # 搜索：名称或ID
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    Publisher.publisher_name.like(search_pattern),
                    Publisher.id.cast(String).like(search_pattern)
                )
            )
        
        if is_active is not None:
            conditions.append(Publisher.is_active == is_active)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 总数查询
        count_query = select(func.count(Publisher.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页查询（使用selectinload优化客户信息加载）
        offset = (page - 1) * page_size
        query = query.options(
            selectinload(Publisher.client).selectinload(Client.user)
        )
        query = query.order_by(Publisher.created_at.desc())
        query = query.offset(offset).limit(page_size)
        
        result = await self.db.execute(query)
        publishers = result.scalars().all()
        
        return publishers, total
    
    async def create_publisher(
        self,
        publisher_data: Dict[str, Any],
        current_user: User
    ) -> Publisher:
        """
        创建渠道
        
        Args:
            publisher_data: 渠道数据字典
            current_user: 当前用户
        
        Returns:
            Publisher: 创建的渠道对象
        """
        # 权限检查：仅管理员可创建
        self.require_admin(current_user)
        
        # 验证Postback URL占位符
        if publisher_data.get('postback_url'):
            is_valid, error_msg = validate_postback_url_placeholders(
                publisher_data['postback_url']
            )
            if not is_valid:
                raise_api_exception(
                    ErrorCode.INVALID_INPUT,
                    detail=error_msg
                )
        
        # 创建渠道
        publisher = Publisher(
            publisher_name=publisher_data['publisher_name'],
            email=publisher_data.get('email'),
            price_discount=publisher_data.get('price_discount', 0.0),
            postback_url=publisher_data.get('postback_url'),
            postback_method=publisher_data.get('postback_method', 'GET'),
            client_id=publisher_data.get('client_id'),
            is_active=publisher_data.get('is_active', True)
        )
        
        self.db.add(publisher)
        await self.db.commit()
        await self.db.refresh(publisher)
        
        # 记录审计日志
        await log_user_action(
            db=self.db,
            action_type="CREATE",
            user=current_user,
            username=current_user.username,
            resource_type="PUBLISHER",
            resource_id=publisher.id,
            resource_name=publisher.publisher_name,
            success=True
        )
        
        logger.info(f"渠道已创建: {publisher.publisher_name} (ID: {publisher.id})")
        return publisher
    
    async def update_publisher(
        self,
        publisher_id: int,
        publisher_data: Dict[str, Any],
        current_user: User
    ) -> Publisher:
        """
        更新渠道信息
        
        Args:
            publisher_id: 渠道ID
            publisher_data: 更新的数据字典
            current_user: 当前用户
        
        Returns:
            Publisher: 更新后的渠道对象
        """
        # 权限检查
        self.require_admin(current_user)
        
        # 获取渠道
        publisher = await self.get_publisher_by_id(publisher_id, current_user, include_client=False)
        
        # 验证Postback URL占位符（如果修改）
        if 'postback_url' in publisher_data and publisher_data['postback_url']:
            is_valid, error_msg = validate_postback_url_placeholders(
                publisher_data['postback_url']
            )
            if not is_valid:
                raise_api_exception(
                    ErrorCode.INVALID_INPUT,
                    detail=error_msg
                )
        
        # 更新字段
        if 'publisher_name' in publisher_data:
            publisher.publisher_name = publisher_data['publisher_name']
        if 'email' in publisher_data:
            publisher.email = publisher_data['email']
        if 'price_discount' in publisher_data:
            publisher.price_discount = publisher_data['price_discount']
        if 'postback_url' in publisher_data:
            publisher.postback_url = publisher_data['postback_url']
        if 'postback_method' in publisher_data:
            publisher.postback_method = publisher_data['postback_method']
        elif publisher.postback_method is None:
            # 如果 postback_method 为 None，设置为默认值 GET
            publisher.postback_method = 'GET'
        if 'client_id' in publisher_data:
            publisher.client_id = publisher_data['client_id']
        if 'is_active' in publisher_data:
            publisher.is_active = publisher_data['is_active']
        
        await self.db.commit()
        await self.db.refresh(publisher)
        
        # 记录审计日志
        await log_user_action(
            db=self.db,
            action_type="UPDATE",
            user=current_user,
            username=current_user.username,
            resource_type="PUBLISHER",
            resource_id=publisher.id,
            resource_name=publisher.publisher_name,
            success=True
        )
        
        logger.info(f"渠道已更新: {publisher.publisher_name} (ID: {publisher.id})")
        return publisher
    
    async def delete_publisher(
        self,
        publisher_id: int,
        current_user: User
    ) -> None:
        """
        删除渠道
        
        Args:
            publisher_id: 渠道ID
            current_user: 当前用户
        """
        # 权限检查
        self.require_admin(current_user)
        
        # 获取渠道
        publisher = await self.get_publisher_by_id(publisher_id, current_user, include_client=False)
        
        # 检查是否有关联的Offer分配
        assignment_count = await self.db.execute(
            select(func.count(OfferPublisherAssignment.id)).where(
                OfferPublisherAssignment.publisher_id == publisher_id
            )
        )
        if assignment_count.scalar() > 0:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"渠道 {publisher.publisher_name} 有关联的Offer分配，无法删除"
            )
        
        # 记录审计日志（在删除前）
        await log_user_action(
            db=self.db,
            action_type="DELETE",
            user=current_user,
            username=current_user.username,
            resource_type="PUBLISHER",
            resource_id=publisher.id,
            resource_name=publisher.publisher_name,
            success=True
        )
        
        # 删除渠道
        await self.db.delete(publisher)
        await self.db.commit()
        
        logger.info(f"渠道已删除: {publisher.publisher_name} (ID: {publisher_id})")

