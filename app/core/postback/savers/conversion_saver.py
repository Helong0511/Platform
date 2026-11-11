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

from app.models.models import PostbackConversion, Click, Product
from app.core.utils import get_app_now_naive

logger = logging.getLogger(__name__)


class ConversionSaver:
    """转化记录保存器"""

    @staticmethod
    async def resolve_trusted_attribution(
        normalized_data: Dict[str, Any],
        click_association: Optional[Dict[str, Any]],
        db: AsyncSession,
    ) -> tuple[Optional[int], Optional[int]]:
        """仅从服务器侧点击/渠道关系确定客户，并验证产品属于该客户。"""
        trusted_client_id = (
            click_association.get('client_id') if click_association else None
        )
        if trusted_client_id is None and click_association:
            trusted_publisher = click_association.get('publisher')
            trusted_client_id = getattr(trusted_publisher, 'client_id', None)

        supplied_client_id = normalized_data.get('client_id')
        if supplied_client_id is not None:
            try:
                client_id_mismatch = (
                    trusted_client_id is None
                    or int(supplied_client_id) != int(trusted_client_id)
                )
            except (TypeError, ValueError):
                client_id_mismatch = True
            if client_id_mismatch:
                logger.warning(
                    "忽略回调中不可信或与点击归属不一致的 client_id：supplied=%s trusted=%s",
                    supplied_client_id,
                    trusted_client_id,
                )

        product_id_candidate = (
            click_association.get('product_id') if click_association else None
        ) or normalized_data.get('product_id')
        trusted_product_id = None
        if trusted_client_id is not None and product_id_candidate is not None:
            product_result = await db.execute(
                select(Product.id)
                .where(
                    Product.id == product_id_candidate,
                    Product.client_id == trusted_client_id,
                )
                .limit(1)
            )
            trusted_product_id = product_result.scalar_one_or_none()
            if trusted_product_id is None:
                logger.warning(
                    "忽略不属于当前点击客户的 product_id：product_id=%s client_id=%s",
                    product_id_candidate,
                    trusted_client_id,
                )
        elif product_id_candidate is not None:
            logger.warning(
                "缺少可信点击客户归属，忽略回调中的 product_id：product_id=%s",
                product_id_candidate,
            )

        return trusted_client_id, trusted_product_id

    @staticmethod
    async def save(
        normalized_data: Dict[str, Any],
        click_association: Optional[Dict[str, Any]],
        final_payout: Decimal | float | int | str,
        conversion_status: str,
        db: AsyncSession,
        trusted_client_id: Optional[int] = None,
        trusted_product_id: Optional[int] = None,
        trusted_attribution_resolved: bool = False,
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
        # 归因快照在可信租户/产品归属核验后生成，避免把请求体字段当成可信归属。
        raw_in = normalized_data.get('raw_data')
        raw_payload = dict(raw_in) if isinstance(raw_in, dict) else None
        snapshot = None

        click_time = None
        if click_association:
            click_time = click_association.get('click_time')

        snap_offer = click_association.get('offer_id') if click_association else None
        snap_pub = click_association.get('publisher_id') if click_association else None
        snap_adv = click_association.get('advertiser_id') if click_association else None

        if not trusted_attribution_resolved:
            trusted_client_id, trusted_product_id = (
                await ConversionSaver.resolve_trusted_attribution(
                    normalized_data=normalized_data,
                    click_association=click_association,
                    db=db,
                )
            )

        if click_association:
            snapshot = {
                key: click_association[key]
                for key in ('offer_id', 'publisher_id', 'advertiser_id', 'click_id')
                if click_association.get(key) is not None
            }
            if trusted_client_id is not None:
                snapshot['client_id'] = trusted_client_id
            if trusted_product_id is not None:
                snapshot['product_id'] = trusted_product_id
            snapshot = snapshot or None

        if raw_payload is not None:
            if snapshot:
                raw_payload['_attribution'] = snapshot
            raw_data_json = json.dumps(raw_payload)
        elif raw_in is not None:
            raw_data_json = json.dumps(raw_in)
        elif snapshot:
            raw_data_json = json.dumps({'_attribution': snapshot})
        else:
            raw_data_json = None

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
            product_id=trusted_product_id,
            client_id=trusted_client_id,
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
            logger.error("更新 Click 表 conversion_id 失败：%s", type(e).__name__)
            raise
