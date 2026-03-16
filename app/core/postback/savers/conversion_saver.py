"""
转化记录保存器

负责保存转化记录到数据库
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PostbackConversion, ClickStats
from app.core.utils import get_app_now_naive

logger = logging.getLogger(__name__)


class ConversionSaver:
    """转化记录保存器"""
    
    @staticmethod
    async def save(
        normalized_data: Dict[str, Any],
        click_association: Optional[Dict[str, Any]],
        final_payout: float,
        conversion_status: str,
        db: AsyncSession
    ) -> PostbackConversion:
        """
        保存转化记录
        
        Args:
            normalized_data: 标准化后的数据
            click_association: Click 关联信息
            final_payout: 最终金额
            conversion_status: 转化状态
            db: 数据库会话
        
        Returns:
            PostbackConversion: 保存的转化记录
        """
        # 创建转化记录
        import json
        raw_data_json = json.dumps(normalized_data['raw_data']) if normalized_data.get('raw_data') else None
        
        conversion = PostbackConversion(
            platform=normalized_data['platform'],
            conversion_id=normalized_data['conversion_id'],
            event_name=normalized_data['event_name'],
            event_value=normalized_data['event_value'],
            original_payout=normalized_data['payout'],
            payout=final_payout,
            devad_id=normalized_data['devad_id'],
            os=normalized_data['os'],
            carrier=normalized_data['carrier'],
            ip=normalized_data['ip'] or (click_association.get('ip') if click_association else None),
            gid=normalized_data['gid'],
            product_id=normalized_data['product_id'] or (click_association.get('product_id') if click_association else None),
            client_id=normalized_data['client_id'] or (click_association.get('client_id') if click_association else None),
            conversion_status=conversion_status,
            raw_data=raw_data_json,
            created_at=get_app_now_naive()
        )
        
        db.add(conversion)
        await db.flush()  # 获取 ID
        await db.refresh(conversion)
        
        logger.info(
            f"转化记录已保存：id={conversion.id}, "
            f"platform={conversion.platform}, conversion_id={conversion.conversion_id}"
        )
        
        return conversion
    
    @staticmethod
    async def update_click_stats(
        click_association: Optional[Dict[str, Any]],
        conversion_id: int,
        db: AsyncSession
    ) -> bool:
        """
        更新 Click 统计
        
        Args:
            click_association: Click 关联信息
            conversion_id: 转化 ID
            db: 数据库会话
        
        Returns:
            bool: 是否成功更新
        """
        if not click_association:
            return False
        
        try:
            # 更新 ClickStats 表
            click_stats = ClickStats(
                click_id=click_association['click_id'],
                offer_id=click_association['offer_id'],
                publisher_id=click_association['publisher_id'],
                advertiser_id=click_association['advertiser_id'],
                click_time=click_association['click_time'],
                conversion_id=conversion_id,
                created_at=get_app_now_naive()
            )
            
            db.add(click_stats)
            await db.commit()
            
            logger.info(
                f"Click 统计已更新：click_id={click_association['click_id']}, "
                f"conversion_id={conversion_id}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"更新 Click 统计失败：{e}", exc_info=True)
            await db.rollback()
            return False
