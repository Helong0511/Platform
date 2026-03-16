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
            # 检查是否已存在 ClickStats 记录
            from sqlalchemy import select
            click_id = click_association['click_id']
            result = await db.execute(
                select(ClickStats).where(ClickStats.click_id == click_id)
            )
            existing_stats = result.scalars().first()
            
            if existing_stats:
                # 已存在记录，跳过
                logger.info(
                    f"Click 统计已存在，跳过：click_id={click_id}, "
                    f"conversion_id={conversion_id}"
                )
                return True
            
            # 创建新的 ClickStats 记录
            click_stats = ClickStats(
                click_id=click_id,
                offer_id=click_association['offer_id'],
                publisher_id=click_association['publisher_id'],
                advertiser_id=click_association['advertiser_id'],
                click_time=click_association['click_time'],
                created_at=get_app_now_naive()
            )
            
            db.add(click_stats)
            await db.flush()
            
            logger.info(
                f"Click 统计已更新：click_id={click_id}, "
                f"conversion_id={conversion_id}"
            )
            
            return True
            
        except Exception as e:
            # 检查是否是唯一索引冲突
            error_msg = str(e)
            if "Duplicate entry" in error_msg and "click_stats.ix_click_stats_click_id" in error_msg:
                # 唯一索引冲突，这是预期的容错情况
                click_id = click_association.get('click_id', 'unknown')
                logger.warning(
                    f"Click 统计已存在（唯一索引冲突）：click_id={click_id}, "
                    f"conversion_id={conversion_id}"
                )
                
                # 发送 Telegram 通知
                try:
                    from app.core.config import settings
                    from app.core.telegram import send_telegram_message_async
                    import asyncio
                    
                    telegram_msg = f"⚠️ Click 统计重复警告\n\n"
                    telegram_msg += f"点击 ID: {click_id}\n"
                    telegram_msg += f"转化 ID: {conversion_id}\n"
                    telegram_msg += f"错误信息: 唯一索引冲突，记录已存在\n"
                    telegram_msg += f"时间: {get_app_now_naive().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    
                    # 异步发送通知
                    asyncio.create_task(
                        send_telegram_message_async(
                            settings.TELEGRAM_ADMIN, 
                            telegram_msg
                        )
                    )
                    logger.info(f"已发送 Click 统计重复警告通知: click_id={click_id}")
                except Exception as notify_err:
                    logger.warning(f"发送 Click 统计重复警告通知失败: {notify_err}")
                
                await db.rollback()
                return True  # 虽然有冲突，但这是预期情况，返回成功
            else:
                # 其他错误
                logger.error(f"更新 Click 统计失败：{e}", exc_info=True)
                await db.rollback()
                return False
