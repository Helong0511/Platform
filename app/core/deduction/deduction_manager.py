"""
转化扣减管理逻辑
用于计算扣减和处理优先级
"""
import logging
import random
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_, func
from datetime import datetime, timedelta

from app.models.models import (
    ConversionDeductionConfig, 
    ConversionDeductionLog,
    PostbackConversion,
    Advertiser,
    Offer,
    Publisher,
    Click
)

logger = logging.getLogger(__name__)


async def find_deduction_config(
    db: AsyncSession,
    advertiser_id: Optional[int] = None,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None
) -> Optional[ConversionDeductionConfig]:
    """
    查找扣减配置（按优先级：Offer > Advertiser > Publisher）
    
    Args:
        db: 数据库会话
        advertiser_id: 广告主ID
        offer_id: Offer ID
        publisher_id: 渠道ID
        
    Returns:
        找到的扣减配置，如果没找到返回None
    """
    try:
        # 优先级1: Offer级别配置
        if offer_id:
            offer_config_result = await db.execute(
                select(ConversionDeductionConfig).where(
                    and_(
                        ConversionDeductionConfig.offer_id == offer_id,
                        ConversionDeductionConfig.is_active == True
                    )
                ).order_by(ConversionDeductionConfig.priority.desc())
            )
            offer_config = offer_config_result.scalars().first()
            if offer_config:
                logger.debug(f"找到Offer级别扣减配置: offer_id={offer_id}, config_id={offer_config.id}")
                return offer_config
        
        # 优先级2: 广告主级别配置
        if advertiser_id:
            advertiser_config_result = await db.execute(
                select(ConversionDeductionConfig).where(
                    and_(
                        ConversionDeductionConfig.advertiser_id == advertiser_id,
                        ConversionDeductionConfig.is_active == True
                    )
                ).order_by(ConversionDeductionConfig.priority.desc())
            )
            advertiser_config = advertiser_config_result.scalars().first()
            if advertiser_config:
                logger.debug(f"找到广告主级别扣减配置: advertiser_id={advertiser_id}, config_id={advertiser_config.id}")
                return advertiser_config
        
        # 优先级3: 渠道级别配置
        if publisher_id:
            publisher_config_result = await db.execute(
                select(ConversionDeductionConfig).where(
                    and_(
                        ConversionDeductionConfig.publisher_id == publisher_id,
                        ConversionDeductionConfig.is_active == True
                    )
                ).order_by(ConversionDeductionConfig.priority.desc())
            )
            publisher_config = publisher_config_result.scalars().first()
            if publisher_config:
                logger.debug(f"找到渠道级别扣减配置: publisher_id={publisher_id}, config_id={publisher_config.id}")
                return publisher_config
        
        return None
        
    except Exception as e:
        logger.error(f"查找扣减配置失败: {str(e)}", exc_info=True)
        return None


async def get_recent_conversion_stats(
    db: AsyncSession,
    advertiser_id: Optional[int] = None,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None,
    hours: int = 24
) -> Dict[str, Any]:
    """
    获取最近的转化统计信息（用于判断是否应该扣减）
    
    Args:
        db: 数据库会话
        advertiser_id: 广告主ID
        offer_id: Offer ID
        publisher_id: 渠道ID
        hours: 统计时间范围（小时）
        
    Returns:
        统计信息字典
    """
    try:
        # 计算时间范围
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        # 构建查询条件（统计扣减日志表，因为被扣量的转化不保存到主表）
        conditions = [
            ConversionDeductionLog.created_at >= start_time,
            ConversionDeductionLog.created_at <= end_time
        ]
        
        if advertiser_id:
            conditions.append(ConversionDeductionLog.advertiser_id == advertiser_id)
        
        if offer_id:
            conditions.append(ConversionDeductionLog.offer_id == offer_id)
        
        if publisher_id:
            conditions.append(ConversionDeductionLog.publisher_id == publisher_id)
        
        # 统计总数（所有转化，包括被扣量的和未扣量的）
        # 注意：所有转化都会记录到扣减日志表，即使未扣减也会记录
        total_result = await db.execute(
            select(func.count(ConversionDeductionLog.id)).where(and_(*conditions))
        )
        total = total_result.scalar() or 0
        
        # 统计已扣减数量（被扣量的转化，deducted_volume > 0）
        deducted_result = await db.execute(
            select(func.count(ConversionDeductionLog.id)).where(
                and_(*conditions, ConversionDeductionLog.deducted_volume > 0)
            )
        )
        deducted = deducted_result.scalar() or 0
        
        # 已处理数量就是total（因为每条转化都会记录日志）
        processed = total
        
        return {
            'total': total,
            'deducted': deducted,
            'processed': processed
        }
        
    except Exception as e:
        logger.error(f"获取转化统计失败: {str(e)}", exc_info=True)
        return {
            'total': 0,
            'deducted': 0,
            'processed': 0
        }


def should_deduct_volume(
    config: ConversionDeductionConfig,
    stats: Dict[str, Any]
) -> bool:
    """
    判断是否应该扣减转化数量
    
    Args:
        config: 扣减配置
        stats: 转化统计信息
        
    Returns:
        是否应该扣减
    """
    if not config.enable_volume_deduction or config.volume_deduction_ratio <= 0:
        return False
    
    total = stats.get('total', 0)
    deducted = stats.get('deducted', 0)
    processed = stats.get('processed', 0)
    
    if total == 0:
        return False
    
    # 计算应该扣减的数量
    should_deduct_count = int(total * config.volume_deduction_ratio)
    
    # 如果已经扣减够了，不再扣减
    if deducted >= should_deduct_count:
        return False
    
    # 根据策略决定是否扣减这条
    remaining_to_deduct = should_deduct_count - deducted
    remaining_conversions = total - processed
    
    if remaining_conversions == 0:
        return False
    
    if config.deduction_strategy == 'random':
        # 随机扣减，但确保总体比例正确
        probability = remaining_to_deduct / remaining_conversions
        return random.random() < probability
    
    elif config.deduction_strategy == 'proportional':
        # 按比例扣减（每N个扣1个）
        if config.volume_deduction_ratio > 0:
            interval = int(1 / config.volume_deduction_ratio)
            return (processed + 1) % interval == 0
        return False
    
    elif config.deduction_strategy == 'round_robin':
        # 轮询扣减
        if config.volume_deduction_ratio > 0:
            interval = int(1 / config.volume_deduction_ratio)
            return processed % interval == 0
        return False
    
    return False


def calculate_amount_deduction(
    original_amount: float,
    config: ConversionDeductionConfig
) -> Tuple[float, float]:
    """
    计算扣减后的金额
    
    Args:
        original_amount: 原始金额
        config: 扣减配置
        
    Returns:
        (扣减后金额, 扣减金额)
    """
    if not config.enable_amount_deduction or config.amount_deduction_ratio <= 0:
        return original_amount, 0.0
    
    deduction_amount = original_amount * config.amount_deduction_ratio
    final_amount = original_amount - deduction_amount
    
    return final_amount, deduction_amount


async def apply_deduction(
    db: AsyncSession,
    conversion_data: Dict[str, Any],
    config: ConversionDeductionConfig,
    click_id: Optional[str] = None,
    advertiser_id: Optional[int] = None,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    应用扣减（可能同时扣量和扣金额）
    
    Args:
        db: 数据库会话
        conversion_data: 转化数据字典
        config: 扣减配置
        click_id: 点击ID
        advertiser_id: 广告主ID
        offer_id: Offer ID
        publisher_id: 渠道ID
        
    Returns:
        扣减结果字典
    """
    result = {
        'should_deduct_volume': False,
        'should_deduct_amount': False,
        'original_volume': 1,
        'original_amount': conversion_data.get('original_payout', 0.0) or 0.0,
        'final_volume': 1,
        'final_amount': conversion_data.get('original_payout', 0.0) or 0.0,
        'deducted_volume': 0,
        'deducted_amount': 0.0,
        'deduction_type': None
    }
    
    # 获取转化统计
    stats = await get_recent_conversion_stats(
        db=db,
        advertiser_id=advertiser_id,
        offer_id=offer_id,
        publisher_id=publisher_id,
        hours=24
    )
    
    # 判断是否扣量
    if config.enable_volume_deduction:
        result['should_deduct_volume'] = should_deduct_volume(config, stats)
        if result['should_deduct_volume']:
            result['final_volume'] = 0
            result['deducted_volume'] = 1
            result['deduction_type'] = 'volume'
    
    # 计算扣金额
    if config.enable_amount_deduction:
        result['should_deduct_amount'] = True
        result['final_amount'], result['deducted_amount'] = calculate_amount_deduction(
            result['original_amount'], config
        )
        if result['deduction_type']:
            result['deduction_type'] = 'both'
        else:
            result['deduction_type'] = 'amount'
    
    return result


async def log_deduction(
    db: AsyncSession,
    deduction_result: Dict[str, Any],
    conversion_id: Optional[int] = None,
    click_id: Optional[str] = None,
    advertiser_id: Optional[int] = None,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None,
    config: Optional[ConversionDeductionConfig] = None,
    deduction_reason: Optional[str] = None
) -> ConversionDeductionLog:
    """
    记录扣减日志
    
    Args:
        db: 数据库会话
        deduction_result: 扣减结果
        conversion_id: 转化记录ID
        click_id: 点击ID
        advertiser_id: 广告主ID
        offer_id: Offer ID
        publisher_id: 渠道ID
        config: 扣减配置
        deduction_reason: 扣减原因
        
    Returns:
        扣减日志记录
    """
    log = ConversionDeductionLog(
        conversion_id=conversion_id,
        click_id=click_id,
        advertiser_id=advertiser_id,
        offer_id=offer_id,
        publisher_id=publisher_id,
        original_volume=deduction_result['original_volume'],
        original_amount=deduction_result['original_amount'],
        deducted_volume=deduction_result['deducted_volume'],
        deducted_amount=deduction_result['deducted_amount'],
        final_volume=deduction_result['final_volume'],
        final_amount=deduction_result['final_amount'],
        deduction_config_id=config.id if config else None,
        volume_deduction_ratio=config.volume_deduction_ratio if config and config.enable_volume_deduction else None,
        amount_deduction_ratio=config.amount_deduction_ratio if config and config.enable_amount_deduction else None,
        deduction_strategy=config.deduction_strategy if config else None,
        deduction_reason=deduction_reason
    )
    
    db.add(log)
    await db.flush()  # 不提交，让调用者决定何时提交
    
    return log

