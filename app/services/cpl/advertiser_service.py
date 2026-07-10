"""
广告主（上游）服务层。

功能说明：
- 广告主 CRUD、分页搜索、关联 Offer 统计
- 变更后失效相关基础设施缓存（Offer、Cap 等）

在系统中的位置：
- 被管理端广告主 API 调用；写操作记录审计日志

注意事项：
1. 删除广告主前须确认无活跃 Offer 与转化数据
2. slug/名称变更会影响 Postback platform 匹配，需同步更新诊断工具提示
"""
import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import func, String, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.audit_log import log_user_action, commit_audit_log
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.infrastructure.cache import CacheInvalidator
from app.models.models import Advertiser, User, Offer
from app.services.base_service import BaseService

logger = logging.getLogger(__name__)


class AdvertiserService(BaseService[Advertiser]):
    """
    广告主业务服务。

    继承 BaseService，以 Advertiser 为实体类型。
    广告主即上游供应方，是 Offer 的归属主体。
    """

    def __init__(self, db: AsyncSession):
        """注入异步数据库会话。"""
        super().__init__(db, Advertiser)

    async def get_advertiser_by_id(
            self,
            advertiser_id: int,
            current_user: User
    ) -> Advertiser:
        """
        按主键获取广告主详情。

        Args:
            advertiser_id: 广告主主键
            current_user: 当前登录用户（预留权限扩展）

        Returns:
            Advertiser: 广告主 ORM 对象

        Raises:
            APIException: 记录不存在时抛出 RESOURCE_NOT_FOUND
        """
        advertiser = await self.get_by_id(advertiser_id)

        if not advertiser:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"广告主ID {advertiser_id} 不存在"
            )

        return advertiser

    async def get_advertisers(
            self,
            current_user: User,
            page: int = 1,
            page_size: int = 20,
            search: Optional[str] = None,
            is_active: Optional[bool] = None
    ) -> tuple[List[Advertiser], int]:
        """
        分页查询广告主列表。

        支持按名称或 ID 模糊搜索、按激活状态过滤，按创建时间倒序。

        Args:
            current_user: 当前登录用户
            page: 页码，从 1 开始
            page_size: 每页条数
            search: 搜索词，匹配 advertiser_name 或 id
            is_active: True/False 过滤激活状态，None 不过滤

        Returns:
            tuple[List[Advertiser], int]: (当前页列表, 符合条件的总条数)
        """
        query = select(Advertiser)

        # 筛选条件
        conditions = []

        if search:
            # 搜索：名称或ID
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    Advertiser.advertiser_name.like(search_pattern),
                    Advertiser.id.cast(String).like(search_pattern)
                )
            )

        if is_active is not None:
            conditions.append(Advertiser.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))

        # 总数查询
        count_query = select(func.count(Advertiser.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页查询
        offset = (page - 1) * page_size
        query = query.order_by(Advertiser.created_at.desc())
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        advertisers = result.scalars().all()

        return advertisers, total

    async def create_advertiser(
            self,
            advertiser_data: Dict[str, Any],
            current_user: User
    ) -> Advertiser:
        """
        创建广告主（仅管理员）。

        Args:
            advertiser_data: 含 advertiser_name（必填）、email、mobile、
                advertiser_params、is_active 等字段
            current_user: 当前登录用户，须为管理员

        Returns:
            Advertiser: 已持久化并 refresh 的广告主对象

        Raises:
            APIException: 非管理员无权限
        """
        # 权限检查：仅管理员可创建
        self.require_admin(current_user)

        # 创建广告主
        advertiser = Advertiser(
            advertiser_name=advertiser_data['advertiser_name'],
            email=advertiser_data.get('email'),
            mobile=advertiser_data.get('mobile'),
            advertiser_params=advertiser_data.get('advertiser_params'),
            is_active=advertiser_data.get('is_active', True)
        )

        self.db.add(advertiser)
        await self.db.flush()
        await self.db.refresh(advertiser)

        # 记录审计日志
        await log_user_action(
            db=self.db,
            action_type="CREATE",
            user=current_user,
            username=current_user.username,
            resource_type="ADVERTISER",
            resource_id=advertiser.id,
            resource_name=advertiser.advertiser_name,
            success=True
        )
        await commit_audit_log(self.db)

        logger.info(f"广告主已创建: {advertiser.advertiser_name} (ID: {advertiser.id})")
        return advertiser

    async def update_advertiser(
            self,
            advertiser_id: int,
            advertiser_data: Dict[str, Any],
            current_user: User
    ) -> Advertiser:
        """
        更新广告主信息（仅管理员）。

        仅更新请求体中出现的字段；成功后失效该广告主下 Offer 相关缓存。

        Args:
            advertiser_id: 待更新广告主主键
            advertiser_data: 部分字段字典，键存在才覆盖
            current_user: 当前登录用户，须为管理员

        Returns:
            Advertiser: 更新后的广告主对象
        """
        # 权限检查
        self.require_admin(current_user)

        # 获取广告主
        advertiser = await self.get_advertiser_by_id(advertiser_id, current_user)

        # 更新字段
        if 'advertiser_name' in advertiser_data:
            advertiser.advertiser_name = advertiser_data['advertiser_name']
        if 'email' in advertiser_data:
            advertiser.email = advertiser_data['email']
        if 'mobile' in advertiser_data:
            advertiser.mobile = advertiser_data['mobile']
        if 'advertiser_params' in advertiser_data:
            advertiser.advertiser_params = advertiser_data['advertiser_params']
        if 'is_active' in advertiser_data:
            advertiser.is_active = advertiser_data['is_active']

        await self.db.flush()
        await self.db.refresh(advertiser)

        # 失效相关缓存
        await CacheInvalidator.invalidate_offer_cache(advertiser_id)

        # 记录审计日志
        await log_user_action(
            db=self.db,
            action_type="UPDATE",
            user=current_user,
            username=current_user.username,
            resource_type="ADVERTISER",
            resource_id=advertiser.id,
            resource_name=advertiser.advertiser_name,
            success=True
        )
        await commit_audit_log(self.db)

        logger.info(f"广告主已更新: {advertiser.advertiser_name} (ID: {advertiser.id})")
        return advertiser

    async def delete_advertiser(
            self,
            advertiser_id: int,
            current_user: User
    ) -> None:
        """
        删除广告主（仅管理员）。

        若仍有关联 Offer 则拒绝删除，避免破坏投放链路。

        Args:
            advertiser_id: 待删除广告主主键
            current_user: 当前登录用户，须为管理员

        Raises:
            APIException: 存在关联 Offer 或记录不存在
        """
        # 权限检查
        self.require_admin(current_user)

        # 获取广告主
        advertiser = await self.get_advertiser_by_id(advertiser_id, current_user)

        # 检查是否有关联的Offer
        offer_count = await self.db.execute(
            select(func.count(Offer.id)).where(Offer.advertiser_id == advertiser_id)
        )
        if offer_count.scalar() > 0:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"广告主 {advertiser.advertiser_name} 有关联的Offer，无法删除"
            )

        # 记录审计日志（在删除前）
        await log_user_action(
            db=self.db,
            action_type="DELETE",
            user=current_user,
            username=current_user.username,
            resource_type="ADVERTISER",
            resource_id=advertiser.id,
            resource_name=advertiser.advertiser_name,
            success=True
        )

        # 删除广告主
        await self.db.delete(advertiser)
        await self.db.flush()

        logger.info(f"广告主已删除: {advertiser.advertiser_name} (ID: {advertiser_id})")
