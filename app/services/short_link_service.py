"""
短链接服务层。

功能说明：
- 短链接 CRUD、分页搜索与权限隔离（非管理员仅见自建链接）
- 创建两阶段生成 short_code：临时代码 flush 取 ID 后按 ID 或随机生成唯一码
- 更新/删除后失效 Redis 短链缓存及点击计数器

搜索策略：
- 疑似 short_code 时优先精确/前缀匹配；否则全文索引 title/description

在系统中的位置：
- 被管理端短链接 API 调用；与 ``app.core.short_link_cache`` 联动

注意事项：
1. original_url 保存前应校验协议与占位符合法性
2. 绑定 offer_id/channel_id 影响重定向归因，变更后须考虑缓存一致性
"""
import re
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, text
from sqlalchemy.orm import joinedload
from sqlalchemy import exc

from app.models.models import ShortLink, User, UserRole, Offer, Publisher
from app.services.base_service import BaseService
from fastapi import HTTPException
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.short_link.generator import (
    generate_short_code_from_id,
    generate_unique_short_code
)
from app.core.short_link_cache import invalidate_short_link_cache
from app.core.short_link_click_counter import cleanup_click_counter
import logging

logger = logging.getLogger(__name__)


class ShortLinkService(BaseService[ShortLink]):
    """
    短链接服务。

    与 Offer/Publisher 关联校验、joinedload 预加载创建者与渠道；
    写路径注意 short_code 唯一性与并发下的临时代码策略。
    """

    def __init__(self, db: AsyncSession):
        """注入数据库会话并绑定 ShortLink 模型。"""
        super().__init__(db, ShortLink)

    async def get_short_link_by_id(
            self,
            link_id: int,
            current_user: User,
            include_relations: bool = True
    ) -> ShortLink:
        """
        按 ID 获取短链接详情。

        非管理员仅能访问 created_by == current_user.id 的记录。

        Args:
            link_id: 短链接主键
            current_user: 当前用户
            include_relations: 是否 joinedload creator、channel

        Returns:
            ShortLink 实体
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
        分页查询短链接列表。

        管理员可见全部；普通用户自动加 created_by 过滤。
        search 会根据关键词形态选择 short_code 精确/前缀或 title/description 全文/前缀策略。

        Args:
            current_user: 当前用户
            page: 页码
            page_size: 每页条数
            search: 标题/URL/代码/描述关键词
            is_active: 启用状态
            created_by: 创建者 ID（管理员筛选用）
            offer_id: 关联 Offer ID

        Returns:
            (短链接列表, 总条数)
        """
        query = select(ShortLink)

        # 数据隔离：非管理员只能看自己的链接
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
            search_trimmed = search.strip()

            if len(search_trimmed) > 100:
                search_trimmed = search_trimmed[:100]
                logger.warning(f"搜索关键词过长，已截断到100字符: {search}")

            # 分支 A：形如短码 → 走 short_code 索引友好路径
            is_likely_short_code = bool(re.match(r'^[a-zA-Z0-9_-]+$', search_trimmed))

            search_conditions = []

            if is_likely_short_code:
                search_conditions.append(ShortLink.short_code == search_trimmed)
                if len(search_trimmed) >= 2:
                    search_conditions.append(ShortLink.short_code.like(f"{search_trimmed}%"))
            else:
                # 分支 B：自然语言关键词 → 全文索引，失败则 title/description 前缀
                try:
                    fulltext_title = text(
                        "MATCH(title) AGAINST(:search_term IN NATURAL LANGUAGE MODE)"
                    ).bindparams(search_term=search_trimmed)
                    search_conditions.append(fulltext_title)

                    fulltext_desc = text(
                        "MATCH(description) AGAINST(:search_term IN NATURAL LANGUAGE MODE)"
                    ).bindparams(search_term=search_trimmed)
                    search_conditions.append(fulltext_desc)
                except Exception:
                    search_conditions.append(ShortLink.title.like(f"{search_trimmed}%"))
                    search_conditions.append(ShortLink.description.like(f"{search_trimmed}%"))

            # 分支 C：original_url 子串（长度门槛降低全表扫描风险）
            if len(search_trimmed) >= 4:
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
        创建短链接。

        short_code 未指定时：insert 临时代码 → flush 得 ID → 按 ID 生成或随机唯一码 → commit。
        关联 offer_id/channel_id 时校验外键存在。

        Args:
            link_data: 须含 original_url；可选 short_code、offer_id、channel_id 等
            current_user: 创建者

        Returns:
            持久化后的 ShortLink
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

            # --- 外键校验：Offer / 渠道 ---
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

            # --- 两阶段 short_code：临时代码占位，flush 后生成最终唯一码 ---
            temp_code = f"temp_{uuid.uuid4().hex[:8]}" if not short_code else short_code
            short_link = ShortLink(
                original_url=link_data['original_url'],
                title=link_data.get('title'),
                description=link_data.get('description'),
                short_code=temp_code,  # 唯一的临时代码，稍后更新
                created_by=current_user.id,
                offer_id=link_data.get('offer_id'),
                channel_id=link_data.get('channel_id'),
                is_active=link_data.get('is_active', True),
                expires_at=link_data.get('expires_at'),
                click_count=0
            )

            logger.debug(f"添加短链接到数据库，临时代码: {temp_code}")
            self.db.add(short_link)
            logger.debug("执行flush以获取ID")
            await self.db.flush()  # 先flush以获取ID
            logger.debug(f"获取到短链接ID: {short_link.id}")

            # 如果没有提供自定义代码，生成唯一代码
            if not link_data.get('short_code'):
                result = await self.db.execute(select(ShortLink.short_code))
                existing_codes = {row[0] for row in result.all() if not row[0].startswith('temp_')}

                code_from_id = generate_short_code_from_id(short_link.id, min_length=4)
                if code_from_id not in existing_codes:
                    short_link.short_code = code_from_id
                else:
                    # ID 派生码冲突时退化为随机唯一码
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

            # 提交事务，确保数据保存到数据库
            logger.debug("提交事务")
            await self.db.commit()

            logger.info(f"短链接创建成功: {short_link.short_code} -> {short_link.original_url}")
            return short_link
        except exc.IntegrityError as e:
            # 处理重复短码的错误
            if "Duplicate entry" in str(e) and "short_code" in str(e):
                logger.error(f"短链接代码重复: {str(e)}")
                raise_api_exception(
                    ErrorCode.RESOURCE_ALREADY_EXISTS,
                    detail="短链接代码已存在，请使用其他代码"
                )
            logger.error(f"创建短链接失败: {str(e)}", exc_info=True)
            # 抛出标准化的服务器错误异常
            raise_api_exception(
                ErrorCode.INTERNAL_ERROR,
                detail="创建短链接时发生数据库错误，请稍后重试"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"创建短链接失败: {str(e)}", exc_info=True)
            # 抛出标准化的服务器错误异常
            raise_api_exception(
                ErrorCode.INTERNAL_ERROR,
                detail="创建短链接时发生错误，请稍后重试"
            )

    async def update_short_link(
            self,
            link_id: int,
            link_data: Dict[str, Any],
            current_user: User
    ) -> ShortLink:
        """
        更新短链接字段。

        提交后 invalidate_short_link_cache，避免跳转仍读到旧 URL。

        Args:
            link_id: 短链接主键
            link_data: 待更新字段
            current_user: 当前用户

        Returns:
            更新后的 ShortLink
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
        删除短链接。

        删除后清理 Redis 短链缓存与点击计数器，防止幽灵计数同步。

        Args:
            link_id: 短链接主键
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
        await cleanup_click_counter(short_code)

        logger.info(f"短链接删除成功: {link_id}")
