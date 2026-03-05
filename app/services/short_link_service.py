"""
短链接服务层
封装短链接相关的业务逻辑
"""
import re
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, text
from sqlalchemy.orm import joinedload

from app.models.models import ShortLink, User, UserRole, Offer, Publisher
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.short_link.generator import (
    generate_short_code_from_id,
    generate_unique_short_code
)
from app.core.short_link_cache import invalidate_short_link_cache
import logging

logger = logging.getLogger(__name__)


class ShortLinkService(BaseService[ShortLink]):
    """短链接服务"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(db, ShortLink)
    
    async def get_short_link_by_id(
        self,
        link_id: int,
        current_user: User,
        include_relations: bool = True
    ) -> ShortLink:
        """
        根据ID获取短链接详情
        
        Args:
            link_id: 短链接ID
            current_user: 当前用户
            include_relations: 是否包含关联信息（创建者、渠道）
        
        Returns:
            ShortLink: 短链接对象
        """
        query = select(ShortLink).where(ShortLink.id == link_id)
        
        # 如果需要关联信息，使用joinedload优化查询
        if include_relations:
            query = query.options(
                joinedload(ShortLink.creator),
                joinedload(ShortLink.channel)
            )
        
        result = await self.db.execute(query)
        # 使用joinedload时，为了安全起见使用unique()去重
        # 注意：scalar_one_or_none()用于标量值，这里应该使用scalars().one_or_none()
        if include_relations:
            short_link = result.unique().scalars().one_or_none()
        else:
            short_link = result.scalars().one_or_none()
        
        if not short_link:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"短链接ID {link_id} 不存在"
            )
        
        # 权限检查：非管理员只能查看自己创建的短链接
        if current_user.role != UserRole.ADMIN:
            if short_link.created_by != current_user.id:
                raise_api_exception(
                    ErrorCode.ACCESS_DENIED,
                    detail="无权访问该短链接"
                )
        
        return short_link
    
    async def get_short_links(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        created_by: Optional[int] = None,
        offer_id: Optional[int] = None
    ) -> tuple[List[ShortLink], int]:
        """
        获取短链接列表（支持分页、筛选、搜索）
        
        Args:
            current_user: 当前用户
            page: 页码
            page_size: 每页数量
            search: 搜索关键词（标题、URL、代码、描述）
            is_active: 激活状态过滤
            created_by: 创建者ID过滤
            offer_id: Offer ID过滤
        
        Returns:
            tuple: (短链接列表, 总数)
        """
        query = select(ShortLink)
        
        # 权限检查：管理员可以查看所有，普通用户只能查看自己的
        if current_user.role != UserRole.ADMIN:
            query = query.where(ShortLink.created_by == current_user.id)
        
        # 应用过滤条件
        conditions = []
        
        if is_active is not None:
            conditions.append(ShortLink.is_active == is_active)
        
        if created_by:
            conditions.append(ShortLink.created_by == created_by)
        
        if offer_id:
            conditions.append(ShortLink.offer_id == offer_id)
        
        if search:
            # 优化搜索：优先精确匹配short_code，然后使用全文索引或前缀匹配
            search_trimmed = search.strip()
            
            # 限制搜索关键词长度，防止过长搜索影响性能
            if len(search_trimmed) > 100:
                search_trimmed = search_trimmed[:100]
                logger.warning(f"搜索关键词过长，已截断到100字符: {search}")
            
            # 判断搜索关键词是否像短链接代码（只包含字母、数字、连字符和下划线）
            is_likely_short_code = bool(re.match(r'^[a-zA-Z0-9_-]+$', search_trimmed))
            
            search_conditions = []
            
            if is_likely_short_code:
                # 如果看起来像短链接代码，优先精确匹配（性能最好）
                # 1. 精确匹配short_code（最快，使用唯一索引）
                search_conditions.append(ShortLink.short_code == search_trimmed)
                
                # 2. 前缀匹配short_code（可以使用索引）
                if len(search_trimmed) >= 2:  # 至少2个字符才使用前缀匹配
                    search_conditions.append(ShortLink.short_code.like(f"{search_trimmed}%"))
            else:
                # 如果不是短链接代码格式，只搜索标题、描述和URL
                # 使用全文索引搜索title和description（如果存在全文索引）
                try:
                    # 尝试使用全文索引搜索title
                    fulltext_title = text(
                        "MATCH(title) AGAINST(:search_term IN NATURAL LANGUAGE MODE)"
                    ).bindparams(search_term=search_trimmed)
                    search_conditions.append(fulltext_title)
                    
                    # 尝试使用全文索引搜索description
                    fulltext_desc = text(
                        "MATCH(description) AGAINST(:search_term IN NATURAL LANGUAGE MODE)"
                    ).bindparams(search_term=search_trimmed)
                    search_conditions.append(fulltext_desc)
                except Exception:
                    # 全文索引不存在或查询失败，使用前缀匹配（可以使用普通索引）
                    # title前缀匹配
                    search_conditions.append(ShortLink.title.like(f"{search_trimmed}%"))
                    # description前缀匹配
                    search_conditions.append(ShortLink.description.like(f"{search_trimmed}%"))
            
            # 3. original_url的搜索（性能较差，但保留功能）
            # URL通常很长，LIKE查询性能很差，但为了功能完整性保留
            # 增加最小长度限制到10个字符，减少全表扫描的影响
            if len(search_trimmed) >= 4:  # URL搜索至少10个字符（性能优化）
                search_conditions.append(ShortLink.original_url.like(f"%{search_trimmed}%"))
            
            if search_conditions:
                conditions.append(or_(*search_conditions))
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 计算总数（在加载关联之前）
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 排序：最新的在前
        query = query.order_by(ShortLink.created_at.desc())
        
        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        
        # 加载关联信息（在分页之后）
        query = query.options(
            joinedload(ShortLink.creator),
            joinedload(ShortLink.channel)
        )
        
        result = await self.db.execute(query)
        # 使用joinedload时，为了安全起见使用unique()去重
        short_links = result.unique().scalars().all()
        
        return short_links, total
    
    async def create_short_link(
        self,
        link_data: Dict[str, Any],
        current_user: User
    ) -> ShortLink:
        """
        创建短链接
        
        Args:
            link_data: 短链接数据字典
            current_user: 当前用户
        
        Returns:
            ShortLink: 创建的短链接对象
        """
        logger.info(f"开始创建短链接，数据: {link_data}")
        logger.info(f"当前用户: {current_user.id} ({current_user.username})")
        
        try:
            # 验证必需字段
            if not link_data.get('original_url'):
                logger.error("缺少必需字段: original_url")
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="缺少必需字段: original_url"
                )
            
            # 如果提供了自定义短链接代码，检查是否已存在
            if link_data.get('short_code'):
                logger.debug(f"检查自定义短链接代码: {link_data['short_code']}")
                existing_result = await self.db.execute(
                    select(ShortLink).where(ShortLink.short_code == link_data['short_code'])
                )
                existing = existing_result.scalar_one_or_none()
                if existing:
                    raise_api_exception(
                        ErrorCode.RESOURCE_ALREADY_EXISTS,
                        detail=f"短链接代码 '{link_data['short_code']}' 已存在，请使用其他代码"
                    )
                short_code = link_data['short_code']
            else:
                short_code = None
            
            # 验证 Offer 是否存在（如果提供了 offer_id）
            if link_data.get('offer_id'):
                logger.debug(f"验证Offer是否存在: {link_data['offer_id']}")
                offer_result = await self.db.execute(
                    select(Offer).where(Offer.id == link_data['offer_id'])
                )
                offer = offer_result.scalar_one_or_none()
                if not offer:
                    raise_api_exception(
                        ErrorCode.RESOURCE_NOT_FOUND,
                        detail=f"Offer ID {link_data['offer_id']} 不存在"
                    )
            
            # 验证渠道是否存在（如果提供了 channel_id）
            if link_data.get('channel_id'):
                logger.debug(f"验证渠道是否存在: {link_data['channel_id']}")
                channel_result = await self.db.execute(
                    select(Publisher).where(Publisher.id == link_data['channel_id'])
                )
                channel = channel_result.scalar_one_or_none()
                if not channel:
                    raise_api_exception(
                        ErrorCode.RESOURCE_NOT_FOUND,
                        detail=f"渠道ID {link_data['channel_id']} 不存在"
                    )
            
            # 创建短链接
            logger.debug("创建短链接对象")
            short_link = ShortLink(
                original_url=link_data['original_url'],
                title=link_data.get('title'),
                description=link_data.get('description'),
                short_code=short_code or "temp",  # 临时代码，稍后更新
                created_by=current_user.id,
                offer_id=link_data.get('offer_id'),
                channel_id=link_data.get('channel_id'),
                is_active=link_data.get('is_active', True),
                expires_at=link_data.get('expires_at'),
                click_count=0
            )
            
            logger.debug("添加短链接到数据库")
            self.db.add(short_link)
            logger.debug("执行flush以获取ID")
            await self.db.flush()  # 先flush以获取ID
            logger.debug(f"获取到短链接ID: {short_link.id}")
            
            # 如果没有提供自定义代码，生成唯一代码
            if not link_data.get('short_code'):
                logger.debug("生成唯一短链接代码")
                # 获取所有已存在的代码
                result = await self.db.execute(select(ShortLink.short_code))
                existing_codes = {row[0] for row in result.all() if row[0] != "temp"}
                logger.debug(f"已存在的代码数量: {len(existing_codes)}")
                
                # 尝试从ID生成
                code_from_id = generate_short_code_from_id(short_link.id, min_length=4)
                logger.debug(f"从ID生成的代码: {code_from_id}")
                if code_from_id not in existing_codes:
                    short_link.short_code = code_from_id
                    logger.debug(f"使用从ID生成的代码: {code_from_id}")
                else:
                    # 如果ID生成的代码已存在，使用随机生成
                    unique_code = generate_unique_short_code(existing_codes, length=6)
                    logger.debug(f"随机生成的代码: {unique_code}")
                    if not unique_code:
                        raise_api_exception(
                            ErrorCode.OPERATION_FAILED,
                            detail="生成短链接代码失败，请稍后重试"
                        )
                    short_link.short_code = unique_code
                    logger.debug(f"使用随机生成的代码: {unique_code}")
            
            logger.debug("刷新短链接对象")
        await self.db.refresh(short_link)
        
        logger.info(f"短链接创建成功: {short_link.short_code} -> {short_link.original_url}")
        return short_link
    except Exception as e:
        logger.error(f"创建短链接失败: {str(e)}", exc_info=True)
        # 重新抛出异常
        raise
    
    async def update_short_link(
        self,
        link_id: int,
        link_data: Dict[str, Any],
        current_user: User
    ) -> ShortLink:
        """
        更新短链接
        
        Args:
            link_id: 短链接ID
            link_data: 更新的数据字典
            current_user: 当前用户
        
        Returns:
            ShortLink: 更新后的短链接对象
        """
        # 获取短链接
        short_link = await self.get_short_link_by_id(link_id, current_user, include_relations=False)
        
        # 权限检查：非管理员只能修改自己创建的短链接
        if current_user.role != UserRole.ADMIN:
            if short_link.created_by != current_user.id:
                raise_api_exception(
                    ErrorCode.ACCESS_DENIED,
                    detail="无权修改该短链接"
                )
        
        # 验证 Offer 是否存在（如果提供了 offer_id）
        if 'offer_id' in link_data and link_data['offer_id'] is not None:
            offer_result = await self.db.execute(
                select(Offer).where(Offer.id == link_data['offer_id'])
            )
            offer = offer_result.scalar_one_or_none()
            if not offer:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"Offer ID {link_data['offer_id']} 不存在"
                )
        
        # 验证渠道是否存在（如果提供了 channel_id）
        if 'channel_id' in link_data and link_data['channel_id'] is not None:
            channel_result = await self.db.execute(
                select(Publisher).where(Publisher.id == link_data['channel_id'])
            )
            channel = channel_result.scalar_one_or_none()
            if not channel:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"渠道ID {link_data['channel_id']} 不存在"
                )
        
        # 更新字段
        for key, value in link_data.items():
            setattr(short_link, key, value)
        
        await self.db.commit()
        await self.db.refresh(short_link)
        
        # 清除缓存，确保数据一致性
        await invalidate_short_link_cache(short_link.short_code)
        
        logger.info(f"短链接更新成功: {short_link.short_code}")
        return short_link
    
    async def delete_short_link(
        self,
        link_id: int,
        current_user: User
    ) -> None:
        """
        删除短链接
        
        Args:
            link_id: 短链接ID
            current_user: 当前用户
        """
        # 获取短链接
        short_link = await self.get_short_link_by_id(link_id, current_user, include_relations=False)
        
        # 权限检查：非管理员只能删除自己创建的短链接
        if current_user.role != UserRole.ADMIN:
            if short_link.created_by != current_user.id:
                raise_api_exception(
                    ErrorCode.ACCESS_DENIED,
                    detail="无权删除该短链接"
                )
        
        short_code = short_link.short_code
        
        # 删除短链接
        await self.db.delete(short_link)
        await self.db.commit()
        
        # 清除缓存和Redis计数器，确保数据一致性
        await invalidate_short_link_cache(short_code)
        # 清理Redis中的点击计数器，避免同步失败
        from app.core.short_link_click_counter import cleanup_click_counter
        await cleanup_click_counter(short_code)
        
        logger.info(f"短链接删除成功: {link_id}")

