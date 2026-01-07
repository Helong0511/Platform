"""
转化扣减配置管理服务层
封装扣减配置的业务逻辑

重构说明:
- 提取公共验证逻辑
- 优化数据库查询
- 改进错误处理和日志记录
- 添加配置缓存失效机制
"""
from typing import Optional, List, Dict, Any, Tuple, Literal
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from sqlalchemy.orm import joinedload

from app.models.models import (
    ConversionDeductionConfig,
    ConversionDeductionLog,
    Advertiser,
    Offer,
    Publisher,
    User
)
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.cache import invalidate_cache
import logging

logger = logging.getLogger(__name__)

# 配置层级类型
ConfigLevel = Literal['advertiser', 'offer', 'publisher']


class ConversionDeductionService(BaseService[ConversionDeductionConfig]):
    """
    转化扣减配置服务
    
    提供扣减配置的CRUD操作、日志查询和统计功能
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db, ConversionDeductionConfig)
    
    async def _validate_target_exists(
        self,
        level: ConfigLevel,
        target_id: int
    ) -> None:
        """
        验证配置目标是否存在
        
        Args:
            level: 配置层级
            target_id: 目标ID
            
        Raises:
            APIException: 如果目标不存在
        """
        if level == 'advertiser':
            result = await self.db.execute(
                select(Advertiser).where(Advertiser.id == target_id)
            )
            if not result.scalars().first():
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"广告主ID {target_id} 不存在"
                )
        elif level == 'offer':
            result = await self.db.execute(
                select(Offer).where(Offer.id == target_id)
            )
            if not result.scalars().first():
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"Offer ID {target_id} 不存在"
                )
        elif level == 'publisher':
            result = await self.db.execute(
                select(Publisher).where(Publisher.id == target_id)
            )
            if not result.scalars().first():
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"渠道ID {target_id} 不存在"
                )
        else:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail=f"无效的配置层级: {level}"
            )
    
    async def _check_existing_config(
        self,
        level: ConfigLevel,
        target_id: int
    ) -> None:
        """
        检查是否已存在激活的配置
        
        Args:
            level: 配置层级
            target_id: 目标ID
            
        Raises:
            APIException: 如果已存在激活的配置
        """
        conditions = [ConversionDeductionConfig.is_active == True]
        
        if level == 'advertiser':
            conditions.append(ConversionDeductionConfig.advertiser_id == target_id)
        elif level == 'offer':
            conditions.append(ConversionDeductionConfig.offer_id == target_id)
        elif level == 'publisher':
            conditions.append(ConversionDeductionConfig.publisher_id == target_id)
        
        result = await self.db.execute(
            select(ConversionDeductionConfig).where(and_(*conditions))
        )
        
        if result.scalars().first():
            level_name = {'advertiser': '广告主', 'offer': 'Offer', 'publisher': '渠道'}[level]
            raise_api_exception(
                ErrorCode.RESOURCE_ALREADY_EXISTS,
                detail=f"{level_name}ID {target_id} 已存在激活的扣减配置"
            )
    
    def _build_config_fields(
        self,
        level: ConfigLevel,
        target_id: int,
        config_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        构建配置字段
        
        Args:
            level: 配置层级
            target_id: 目标ID
            config_data: 配置数据
            
        Returns:
            配置字段字典
        """
        fields = {
            'enable_volume_deduction': config_data.get('enable_volume_deduction', False),
            'volume_deduction_ratio': config_data.get('volume_deduction_ratio', 0.0),
            'deduction_strategy': config_data.get('deduction_strategy', 'random'),
            'enable_amount_deduction': config_data.get('enable_amount_deduction', False),
            'amount_deduction_ratio': config_data.get('amount_deduction_ratio', 0.0),
            'priority': config_data.get('priority', 0),
            'is_active': config_data.get('is_active', True)
        }
        
        # 根据层级设置对应的ID字段
        if level == 'advertiser':
            fields['advertiser_id'] = target_id
            fields['offer_id'] = None
            fields['publisher_id'] = None
        elif level == 'offer':
            fields['advertiser_id'] = None
            fields['offer_id'] = target_id
            fields['publisher_id'] = None
        elif level == 'publisher':
            fields['advertiser_id'] = None
            fields['offer_id'] = None
            fields['publisher_id'] = target_id
        
        return fields
    
    async def _invalidate_config_cache(
        self,
        level: Optional[ConfigLevel] = None,
        target_id: Optional[int] = None
    ) -> None:
        """
        清除配置缓存
        
        Args:
            level: 配置层级（可选）
            target_id: 目标ID（可选）
        """
        if level and target_id:
            # 清除特定配置的缓存
            pattern = f"cpl:deduction_config:{level}:{target_id}"
            await invalidate_cache(pattern)
        else:
            # 清除所有配置缓存
            await invalidate_cache("cpl:deduction_config:*")

    async def create_deduction_config(
        self,
        config_data: Dict[str, Any],
        current_user: User
    ) -> ConversionDeductionConfig:
        """
        创建扣减配置

        Args:
            config_data: 扣减配置数据
            current_user: 当前用户

        Returns:
            ConversionDeductionConfig: 创建的扣减配置对象
        """
        # 验证至少启用一种扣减方式
        if not config_data.get('enable_volume_deduction') and not config_data.get('enable_amount_deduction'):
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="请至少启用一种扣减方式（扣量或扣金额）"
            )

        level: ConfigLevel = config_data.get('level')
        target_id = config_data.get('target_id')

        if not level or not target_id:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="配置层级和目标ID不能为空"
            )

        # 验证目标是否存在
        await self._validate_target_exists(level, target_id)
        
        # 检查是否已存在激活的配置
        await self._check_existing_config(level, target_id)

        # 构建配置字段
        fields = self._build_config_fields(level, target_id, config_data)
        
        # 创建配置
        config = ConversionDeductionConfig(**fields)

        try:
            self.db.add(config)
            await self.db.commit()
            await self.db.refresh(config)

            # 清除配置缓存
            await self._invalidate_config_cache(level, target_id)

            # 加载关联信息
            config = await self._load_config_with_relations(config.id)

            logger.info(f"扣减配置创建成功: config_id={config.id}, level={level}, target_id={target_id}")
            return config
        except Exception as e:
            await self.db.rollback()
            logger.error(f"创建扣减配置失败: level={level}, target_id={target_id}, error={str(e)}", exc_info=True)
            if isinstance(e, type(raise_api_exception)):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"创建扣减配置失败: {str(e)}"
            )
    
    async def _load_config_with_relations(
        self,
        config_id: int
    ) -> ConversionDeductionConfig:
        """
        加载配置及其关联信息
        
        Args:
            config_id: 配置ID
            
        Returns:
            配置对象
        """
        query = select(ConversionDeductionConfig).where(
            ConversionDeductionConfig.id == config_id
        ).options(
            joinedload(ConversionDeductionConfig.advertiser),
            joinedload(ConversionDeductionConfig.offer),
            joinedload(ConversionDeductionConfig.publisher)
        )
        result = await self.db.execute(query)
        # 使用joinedload时，为了安全起见使用unique()去重
        config = result.unique().scalars().first()
        if not config:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"扣减配置ID {config_id} 不存在"
            )
        return config

    async def get_deduction_configs(
        self,
        page: int = 1,
        page_size: int = 20,
        level: Optional[str] = None,
        is_active: Optional[bool] = None,
        keyword: Optional[str] = None
    ) -> Tuple[List[ConversionDeductionConfig], int]:
        """
        获取扣减配置列表

        Args:
            page: 页码
            page_size: 每页数量
            level: 配置层级过滤
            is_active: 状态过滤
            keyword: 搜索关键词

        Returns:
            Tuple[List[ConversionDeductionConfig], int]: (扣减配置列表, 总数)
        """
        # 构建查询
        query = select(ConversionDeductionConfig)

        # 应用过滤条件
        conditions = []
        if level:
            if level == 'advertiser':
                conditions.append(ConversionDeductionConfig.advertiser_id.isnot(None))
            elif level == 'offer':
                conditions.append(ConversionDeductionConfig.offer_id.isnot(None))
            elif level == 'publisher':
                conditions.append(ConversionDeductionConfig.publisher_id.isnot(None))

        if is_active is not None:
            conditions.append(ConversionDeductionConfig.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))

        # 获取总数（关键词搜索在内存中过滤，所以先获取所有数据）
        count_query = select(func.count()).select_from(ConversionDeductionConfig)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(
            ConversionDeductionConfig.priority.desc(),
            ConversionDeductionConfig.created_at.desc()
        )
        query = query.offset((page - 1) * page_size).limit(page_size)

        # 加载关联信息
        query = query.options(
            joinedload(ConversionDeductionConfig.advertiser),
            joinedload(ConversionDeductionConfig.offer),
            joinedload(ConversionDeductionConfig.publisher)
        )

        result = await self.db.execute(query)
        configs = result.unique().scalars().all()

        # 关键词搜索（在内存中过滤，因为需要关联查询）
        if keyword:
            keyword_lower = keyword.lower()
            filtered_configs = []
            for config in configs:
                target_name = None
                if config.advertiser:
                    target_name = config.advertiser.advertiser_name
                elif config.offer:
                    target_name = config.offer.offer_name
                elif config.publisher:
                    target_name = config.publisher.publisher_name

                if target_name and keyword_lower in target_name.lower():
                    filtered_configs.append(config)
            configs = filtered_configs
            total = len(filtered_configs)

        return configs, total

    async def get_deduction_config_by_id(self, config_id: int) -> Optional[ConversionDeductionConfig]:
        """
        根据ID获取扣减配置详情

        Args:
            config_id: 配置ID

        Returns:
            Optional[ConversionDeductionConfig]: 扣减配置对象，如果不存在则返回None
        """
        query = select(ConversionDeductionConfig).where(
            ConversionDeductionConfig.id == config_id
        ).options(
            joinedload(ConversionDeductionConfig.advertiser),
            joinedload(ConversionDeductionConfig.offer),
            joinedload(ConversionDeductionConfig.publisher)
        )
        result = await self.db.execute(query)
        # 使用joinedload时，为了安全起见使用unique()去重
        return result.unique().scalars().first()

    async def update_deduction_config(
        self,
        config_id: int,
        update_data: Dict[str, Any],
        current_user: User
    ) -> ConversionDeductionConfig:
        """
        更新扣减配置

        Args:
            config_id: 配置ID
            update_data: 更新数据
            current_user: 当前用户

        Returns:
            ConversionDeductionConfig: 更新后的扣减配置对象
        """
        config = await self.get_deduction_config_by_id(config_id)
        if not config:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"扣减配置ID {config_id} 不存在"
            )

        # 确定配置层级和目标ID（用于清除缓存）
        level: Optional[ConfigLevel] = None
        target_id: Optional[int] = None
        if config.advertiser_id:
            level = 'advertiser'
            target_id = config.advertiser_id
        elif config.offer_id:
            level = 'offer'
            target_id = config.offer_id
        elif config.publisher_id:
            level = 'publisher'
            target_id = config.publisher_id

        # 更新字段（排除level和target_id，这些不能直接更新）
        for field, value in update_data.items():
            if field in ['level', 'target_id']:
                continue
            if hasattr(config, field):
                setattr(config, field, value)

        try:
            await self.db.commit()
            await self.db.refresh(config)

            # 清除配置缓存
            if level and target_id:
                await self._invalidate_config_cache(level, target_id)

            # 加载关联信息
            config = await self._load_config_with_relations(config_id)

            logger.info(f"扣减配置更新成功: config_id={config_id}")
            return config
        except Exception as e:
            await self.db.rollback()
            logger.error(f"更新扣减配置失败: config_id={config_id}, error={str(e)}", exc_info=True)
            if isinstance(e, type(raise_api_exception)):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新扣减配置失败: {str(e)}"
            )

    async def update_deduction_config_status(
        self,
        config_id: int,
        is_active: bool,
        current_user: User
    ) -> ConversionDeductionConfig:
        """
        更新扣减配置状态

        Args:
            config_id: 配置ID
            is_active: 是否激活
            current_user: 当前用户

        Returns:
            ConversionDeductionConfig: 更新后的扣减配置对象
        """
        config = await self.get_deduction_config_by_id(config_id)
        if not config:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"扣减配置ID {config_id} 不存在"
            )

        # 确定配置层级和目标ID（用于清除缓存）
        level: Optional[ConfigLevel] = None
        target_id: Optional[int] = None
        if config.advertiser_id:
            level = 'advertiser'
            target_id = config.advertiser_id
        elif config.offer_id:
            level = 'offer'
            target_id = config.offer_id
        elif config.publisher_id:
            level = 'publisher'
            target_id = config.publisher_id

        config.is_active = is_active

        try:
            await self.db.commit()
            await self.db.refresh(config)

            # 清除配置缓存
            if level and target_id:
                await self._invalidate_config_cache(level, target_id)

            logger.info(f"扣减配置状态更新成功: config_id={config_id}, is_active={is_active}")
            return config
        except Exception as e:
            await self.db.rollback()
            logger.error(f"更新扣减配置状态失败: config_id={config_id}, error={str(e)}", exc_info=True)
            if isinstance(e, type(raise_api_exception)):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新扣减配置状态失败: {str(e)}"
            )

    async def delete_deduction_config(
        self,
        config_id: int,
        current_user: User
    ) -> None:
        """
        删除扣减配置

        Args:
            config_id: 配置ID
            current_user: 当前用户
        """
        config = await self.get_deduction_config_by_id(config_id)
        if not config:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"扣减配置ID {config_id} 不存在"
            )

        # 确定配置层级和目标ID（用于清除缓存）
        level: Optional[ConfigLevel] = None
        target_id: Optional[int] = None
        if config.advertiser_id:
            level = 'advertiser'
            target_id = config.advertiser_id
        elif config.offer_id:
            level = 'offer'
            target_id = config.offer_id
        elif config.publisher_id:
            level = 'publisher'
            target_id = config.publisher_id

        try:
            await self.db.delete(config)
            await self.db.commit()

            # 清除配置缓存
            if level and target_id:
                await self._invalidate_config_cache(level, target_id)

            logger.info(f"扣减配置删除成功: config_id={config_id}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"删除扣减配置失败: config_id={config_id}, error={str(e)}", exc_info=True)
            if isinstance(e, type(raise_api_exception)):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"删除扣减配置失败: {str(e)}"
            )

    async def batch_update_status(
        self,
        config_ids: List[int],
        is_active: bool,
        current_user: User
    ) -> int:
        """
        批量更新扣减配置状态

        Args:
            config_ids: 配置ID列表
            is_active: 是否激活
            current_user: 当前用户

        Returns:
            int: 成功更新的数量
        """
        if not config_ids:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="配置ID列表不能为空"
            )

        # 验证所有配置是否存在
        result = await self.db.execute(
            select(ConversionDeductionConfig).where(
                ConversionDeductionConfig.id.in_(config_ids)
            )
        )
        configs = result.scalars().all()

        if len(configs) != len(config_ids):
            found_ids = {config.id for config in configs}
            missing_ids = set(config_ids) - found_ids
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"以下配置ID不存在: {', '.join(map(str, missing_ids))}"
            )

        # 批量更新状态
        from sqlalchemy import update
        stmt = update(ConversionDeductionConfig).where(
            ConversionDeductionConfig.id.in_(config_ids)
        ).values(is_active=is_active)
        
        try:
            await self.db.execute(stmt)
            await self.db.commit()

            # 清除所有相关配置的缓存
            for config in configs:
                level: Optional[ConfigLevel] = None
                target_id: Optional[int] = None
                if config.advertiser_id:
                    level = 'advertiser'
                    target_id = config.advertiser_id
                elif config.offer_id:
                    level = 'offer'
                    target_id = config.offer_id
                elif config.publisher_id:
                    level = 'publisher'
                    target_id = config.publisher_id
                
                if level and target_id:
                    await self._invalidate_config_cache(level, target_id)

            logger.info(f"批量更新扣减配置状态成功: config_ids={config_ids}, is_active={is_active}, count={len(configs)}")
            return len(configs)
        except Exception as e:
            await self.db.rollback()
            logger.error(f"批量更新扣减配置状态失败: config_ids={config_ids}, error={str(e)}", exc_info=True)
            if isinstance(e, type(raise_api_exception)):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"批量更新扣减配置状态失败: {str(e)}"
            )

    async def batch_delete(
        self,
        config_ids: List[int],
        current_user: User
    ) -> int:
        """
        批量删除扣减配置

        Args:
            config_ids: 配置ID列表
            current_user: 当前用户

        Returns:
            int: 成功删除的数量
        """
        if not config_ids:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="配置ID列表不能为空"
            )

        # 获取所有配置（用于记录日志和清除缓存）
        result = await self.db.execute(
            select(ConversionDeductionConfig).where(
                ConversionDeductionConfig.id.in_(config_ids)
            )
        )
        configs = result.scalars().all()

        if len(configs) != len(config_ids):
            found_ids = {config.id for config in configs}
            missing_ids = set(config_ids) - found_ids
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"以下配置ID不存在: {', '.join(map(str, missing_ids))}"
            )

        # 记录删除日志
        from app.core.audit_log import log_delete
        for config in configs:
            await log_delete(
                db=self.db,
                user=current_user,
                resource_type="CONVERSION_DEDUCTION_CONFIG",
                resource_id=config.id,
                resource_name=f"扣减配置-{config.id}",
                request=None
            )

        # 批量删除配置
        from sqlalchemy import delete
        stmt = delete(ConversionDeductionConfig).where(
            ConversionDeductionConfig.id.in_(config_ids)
        )
        
        try:
            await self.db.execute(stmt)
            await self.db.commit()

            # 清除所有相关配置的缓存
            for config in configs:
                level: Optional[ConfigLevel] = None
                target_id: Optional[int] = None
                if config.advertiser_id:
                    level = 'advertiser'
                    target_id = config.advertiser_id
                elif config.offer_id:
                    level = 'offer'
                    target_id = config.offer_id
                elif config.publisher_id:
                    level = 'publisher'
                    target_id = config.publisher_id
                
                if level and target_id:
                    await self._invalidate_config_cache(level, target_id)

            logger.info(f"批量删除扣减配置成功: config_ids={config_ids}, count={len(configs)}")
            return len(configs)
        except Exception as e:
            await self.db.rollback()
            logger.error(f"批量删除扣减配置失败: config_ids={config_ids}, error={str(e)}", exc_info=True)
            if isinstance(e, type(raise_api_exception)):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"批量删除扣减配置失败: {str(e)}"
            )

    async def get_deduction_stats(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_by: Optional[str] = None,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        获取扣减统计

        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            group_by: 分组方式
            advertiser_id: 广告主ID过滤
            offer_id: Offer ID过滤
            publisher_id: 渠道ID过滤

        Returns:
            Dict: 扣减统计数据
        """
        # 解析日期
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_dt = datetime.now() - timedelta(days=30)

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        else:
            end_dt = datetime.now()

        # 构建查询条件
        conditions = [
            ConversionDeductionLog.created_at >= start_dt,
            ConversionDeductionLog.created_at < end_dt
        ]

        if advertiser_id:
            conditions.append(ConversionDeductionLog.advertiser_id == advertiser_id)
        if offer_id:
            conditions.append(ConversionDeductionLog.offer_id == offer_id)
        if publisher_id:
            conditions.append(ConversionDeductionLog.publisher_id == publisher_id)

        # 统计总体数据
        stats_query = select(
            func.sum(ConversionDeductionLog.original_volume).label('original_volume'),
            func.sum(ConversionDeductionLog.deducted_volume).label('deducted_volume'),
            func.sum(ConversionDeductionLog.final_volume).label('final_volume'),
            func.sum(ConversionDeductionLog.original_amount).label('original_amount'),
            func.sum(ConversionDeductionLog.deducted_amount).label('deducted_amount'),
            func.sum(ConversionDeductionLog.final_amount).label('final_amount')
        ).where(and_(*conditions))

        stats_result = await self.db.execute(stats_query)
        stats_row = stats_result.first()

        original_volume = stats_row.original_volume or 0
        deducted_volume = stats_row.deducted_volume or 0
        final_volume = stats_row.final_volume or 0
        original_amount = float(stats_row.original_amount or 0)
        deducted_amount = float(stats_row.deducted_amount or 0)
        final_amount = float(stats_row.final_amount or 0)

        # 计算比例
        volume_deduction_ratio = deducted_volume / original_volume if original_volume > 0 else 0.0
        amount_deduction_ratio = deducted_amount / original_amount if original_amount > 0 else 0.0

        # 分组统计（根据group_by参数实现分组）
        items = []
        if group_by and group_by != 'time':
            # 根据分组方式构建分组查询
            group_fields = []
            if group_by == 'advertiser':
                group_fields = [ConversionDeductionLog.advertiser_id]
            elif group_by == 'offer':
                group_fields = [ConversionDeductionLog.offer_id]
            elif group_by == 'publisher':
                group_fields = [ConversionDeductionLog.publisher_id]
            
            if group_fields:
                # 加载关联信息用于显示名称
                group_query = select(
                    *group_fields,
                    func.sum(ConversionDeductionLog.original_volume).label('original_volume'),
                    func.sum(ConversionDeductionLog.deducted_volume).label('deducted_volume'),
                    func.sum(ConversionDeductionLog.final_volume).label('final_volume'),
                    func.sum(ConversionDeductionLog.original_amount).label('original_amount'),
                    func.sum(ConversionDeductionLog.deducted_amount).label('deducted_amount'),
                    func.sum(ConversionDeductionLog.final_amount).label('final_amount')
                ).where(and_(*conditions)).group_by(*group_fields)
                
                group_result = await self.db.execute(group_query)
                for row in group_result:
                    item_data = {
                        'original_volume': int(row.original_volume or 0),
                        'deducted_volume': int(row.deducted_volume or 0),
                        'final_volume': int(row.final_volume or 0),
                        'original_amount': float(row.original_amount or 0),
                        'deducted_amount': float(row.deducted_amount or 0),
                        'final_amount': float(row.final_amount or 0),
                        'volume_deduction_ratio': (row.deducted_volume or 0) / (row.original_volume or 1) if row.original_volume else 0.0,
                        'amount_deduction_ratio': (row.deducted_amount or 0) / (row.original_amount or 1) if row.original_amount else 0.0
                    }
                    
                    # 添加名称字段
                    if group_by == 'advertiser' and row.advertiser_id:
                        # 需要查询广告主名称（简化处理，可以优化为JOIN）
                        item_data['advertiser_id'] = row.advertiser_id
                    elif group_by == 'offer' and row.offer_id:
                        item_data['offer_id'] = row.offer_id
                    elif group_by == 'publisher' and row.publisher_id:
                        item_data['publisher_id'] = row.publisher_id
                    
                    items.append(item_data)

        return {
            "original_volume": int(original_volume),
            "deducted_volume": int(deducted_volume),
            "final_volume": int(final_volume),
            "volume_deduction_ratio": volume_deduction_ratio,
            "original_amount": original_amount,
            "deducted_amount": deducted_amount,
            "final_amount": final_amount,
            "amount_deduction_ratio": amount_deduction_ratio,
            "items": items
        }

    async def get_deduction_logs(
        self,
        page: int = 1,
        page_size: int = 20,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        conversion_id: Optional[int] = None,
        click_id: Optional[str] = None
    ) -> Tuple[List[ConversionDeductionLog], int]:
        """
        获取扣减日志

        Args:
            page: 页码
            page_size: 每页数量
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            advertiser_id: 广告主ID过滤
            offer_id: Offer ID过滤
            publisher_id: 渠道ID过滤
            conversion_id: 转化ID过滤
            click_id: 点击ID过滤

        Returns:
            Tuple[List[ConversionDeductionLog], int]: (扣减日志列表, 总数)
        """
        # 解析日期
        conditions = []
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            conditions.append(ConversionDeductionLog.created_at >= start_dt)
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            conditions.append(ConversionDeductionLog.created_at < end_dt)

        if advertiser_id:
            conditions.append(ConversionDeductionLog.advertiser_id == advertiser_id)
        if offer_id:
            conditions.append(ConversionDeductionLog.offer_id == offer_id)
        if publisher_id:
            conditions.append(ConversionDeductionLog.publisher_id == publisher_id)
        if conversion_id:
            conditions.append(ConversionDeductionLog.conversion_id == conversion_id)
        if click_id:
            conditions.append(ConversionDeductionLog.click_id == click_id)

        # 获取总数
        count_query = select(func.count()).select_from(ConversionDeductionLog)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页查询
        query = select(ConversionDeductionLog)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(ConversionDeductionLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        # 加载关联信息
        query = query.options(
            joinedload(ConversionDeductionLog.advertiser),
            joinedload(ConversionDeductionLog.offer),
            joinedload(ConversionDeductionLog.publisher)
        )

        result = await self.db.execute(query)
        logs = result.unique().scalars().all()

        return logs, total

