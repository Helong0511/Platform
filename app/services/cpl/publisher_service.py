"""
渠道（下游/商户）服务层。

功能说明：
- 渠道 CRUD、分页搜索、Postback URL 占位符校验
- 与 Offer 分配、转化转发配置联动

在系统中的位置：
- 被管理端渠道 API 调用；继承 ``BaseService``

注意事项：
1. postback_url 保存前须通过 ``validate_postback_url_placeholders`` 校验
2. 渠道与客户的归属关系影响数据可见范围
"""
import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import func, String, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import object_session, selectinload

from app.core.audit_log import log_user_action, commit_audit_log
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.validation import validate_postback_url_placeholders
from app.models.models import Publisher, Client, User, UserRole, OfferPublisherAssignment
from app.services.base_service import BaseService

logger = logging.getLogger(__name__)


def _sanitize_publisher_for_client(publisher: Publisher) -> Publisher:
    """客户可见渠道时脱敏联系方式与 Postback 配置。

    先从 Session expunge，避免 get_db 自动 commit 把 NULL 写回数据库。
    price_discount 响应模型为非 Optional float，脱敏用 0.0 而非 None。
    """
    session = object_session(publisher)
    if session is not None:
        session.expunge(publisher)
    publisher.email = None
    publisher.postback_url = None
    publisher.postback_success_check = None
    publisher.price_discount = 0.0
    return publisher


class PublisherService(BaseService[Publisher]):
    """
    渠道业务服务。

    渠道即下游商户，承载点击追踪与 Postback 回传配置。
    通过 client_id 关联平台客户账号。
    """

    def __init__(self, db: AsyncSession):
        """注入异步数据库会话。"""
        super().__init__(db, Publisher)

    async def _client_ids_for_user(self, user: User) -> List[int]:
        """返回该客户账号全部启用中的客户主体 ID，避免一对多关系只取首项。"""
        if user.role != UserRole.CLIENT:
            return []
        result = await self.db.execute(
            select(Client.id)
            .where(Client.user_id == user.id, Client.is_active.is_(True))
            .order_by(Client.id.asc())
        )
        return [int(value) for value in result.scalars().all()]

    async def get_publisher_by_id(
            self,
            publisher_id: int,
            current_user: User,
            include_client: bool = True
    ) -> Publisher:
        """
        按主键获取渠道详情。

        Args:
            publisher_id: 渠道主键
            current_user: 当前登录用户（预留权限扩展）
            include_client: True 时 selectinload 预加载 Client 及关联 User

        Returns:
            Publisher: 渠道 ORM 对象

        Raises:
            APIException: 记录不存在或无权访问
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

        if current_user.role == UserRole.CLIENT:
            client_ids = await self._client_ids_for_user(current_user)
            if not client_ids or publisher.client_id not in client_ids:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"渠道ID {publisher_id} 不存在"
                )
            return _sanitize_publisher_for_client(publisher)

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
        分页查询渠道列表。

        支持名称/ID 模糊搜索、激活状态过滤，预加载所属客户信息。
        客户仅可见本 client_id 下渠道，并脱敏敏感字段。

        Args:
            current_user: 当前登录用户
            page: 页码，从 1 开始
            page_size: 每页条数
            search: 搜索词，匹配 publisher_name 或 id
            is_active: 激活状态过滤，None 不过滤

        Returns:
            tuple[List[Publisher], int]: (当前页列表, 总条数)
        """
        query = select(Publisher)

        # 筛选条件
        conditions = []

        if current_user.role == UserRole.CLIENT:
            client_ids = await self._client_ids_for_user(current_user)
            if not client_ids:
                return [], 0
            conditions.append(Publisher.client_id.in_(client_ids))

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
        publishers = list(result.scalars().all())

        if current_user.role == UserRole.CLIENT:
            publishers = [_sanitize_publisher_for_client(p) for p in publishers]

        return publishers, total

    async def create_publisher(
            self,
            publisher_data: Dict[str, Any],
            current_user: User
    ) -> Publisher:
        """
        创建渠道（仅管理员）。

        若提供 postback_url，须通过占位符校验。

        Args:
            publisher_data: 含 publisher_name（必填）、postback_url、
                price_discount、client_id、is_active 等
            current_user: 当前登录用户，须为管理员

        Returns:
            Publisher: 已持久化的渠道对象

        Raises:
            APIException: 非管理员、占位符非法或校验失败
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
        await self.db.flush()
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
        await commit_audit_log(self.db)

        logger.info(f"渠道已创建: {publisher.publisher_name} (ID: {publisher.id})")
        return publisher

    async def update_publisher(
            self,
            publisher_id: int,
            publisher_data: Dict[str, Any],
            current_user: User
    ) -> Publisher:
        """
        更新渠道信息（仅管理员）。

        仅更新请求体中出现的字段；postback_method 为空时默认 GET。

        Args:
            publisher_id: 待更新渠道主键
            publisher_data: 部分字段字典
            current_user: 当前登录用户，须为管理员

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

        await self.db.flush()
        await self.db.refresh(publisher)

        try:
            from app.core.postback.forwarding.cache_manager import CacheManager
            await CacheManager.invalidate_publisher(publisher.id)
        except Exception as e:
            logger.debug("失效渠道转发缓存失败: %s", e)

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
        await commit_audit_log(self.db)

        logger.info(f"渠道已更新: {publisher.publisher_name} (ID: {publisher.id})")
        return publisher

    async def delete_publisher(
            self,
            publisher_id: int,
            current_user: User
    ) -> None:
        """
        删除渠道（仅管理员）。

        若仍存在 OfferPublisherAssignment 则拒绝删除。

        Args:
            publisher_id: 待删除渠道主键
            current_user: 当前登录用户，须为管理员

        Raises:
            APIException: 存在 Offer 分配或记录不存在
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
        await self.db.flush()

        logger.info(f"渠道已删除: {publisher.publisher_name} (ID: {publisher_id})")
