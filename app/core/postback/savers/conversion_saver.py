"""
转化记录保存器

负责保存转化记录到数据库
"""
import logging
import json
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import PostbackConversion, Click
from app.core.utils import get_app_now_naive

logger = logging.getLogger(__name__)


class ConversionSaver:
    """转化记录保存器"""
    
    @staticmethod
    async def save(
        normalized_data: Dict[str, Any],
        click_association: Optional[Dict[str, Any]],
        final_payout: Decimal | float | int | str,
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
        # 归因快照写入 raw_data._attribution（无 DB 列迁移时的轻量方案）
        raw_in = normalized_data.get('raw_data')
        snapshot = None
        if click_association:
            snapshot = {
                k: click_association[k]
                for k in ('offer_id', 'publisher_id', 'advertiser_id', 'click_id')
                if click_association.get(k) is not None
            } or None

        if isinstance(raw_in, dict):
            raw_payload = dict(raw_in)
            if snapshot:
                raw_payload['_attribution'] = snapshot
            raw_data_json = json.dumps(raw_payload)
        elif raw_in is not None:
            raw_data_json = json.dumps(raw_in)
        elif snapshot:
            raw_data_json = json.dumps({'_attribution': snapshot})
        else:
            raw_data_json = None
        
        click_time = None
        if click_association:
            click_time = click_association.get('click_time')

        snap_offer = click_association.get('offer_id') if click_association else None
        snap_pub = click_association.get('publisher_id') if click_association else None
        snap_adv = click_association.get('advertiser_id') if click_association else None

        conversion = PostbackConversion(
            platform=normalized_data['platform'],
            conversion_id=normalized_data['conversion_id'],
            click_id=normalized_data.get('click_id') or (click_association.get('click_id') if click_association else None),
            click_time=click_time,
            offer_id=snap_offer,
            publisher_id=snap_pub,
            advertiser_id=snap_adv,
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
    async def update_click_conversion(
        click_association: Optional[Dict[str, Any]],
        conversion_id: int,
        db: AsyncSession
    ) -> bool:
        """
        更新 Click 表的 conversion_id
        
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
            # 查询并更新 Click 记录
            click_id = click_association['click_id']
            
            # 查询 Click 记录
            result = await db.execute(
                select(Click).where(Click.click_id == click_id)
            )
            click = result.scalars().first()
            
            if not click:
                logger.warning(
                    f"未找到 Click 记录，无法更新 conversion_id：click_id={click_id}, "
                    f"conversion_id={conversion_id}"
                )
                return False
            
            # 更新 conversion_id
            click.conversion_id = conversion_id
            await db.flush()
            
            logger.info(
                f"Click 表 conversion_id 已更新：click_id={click_id}, "
                f"conversion_id={conversion_id}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"更新 Click 表 conversion_id 失败：{e}", exc_info=True)
            raise
