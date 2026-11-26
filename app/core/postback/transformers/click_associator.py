"""
Click ID 关联器

通过 Click ID 关联 Click 记录，获取 Offer、Publisher 等信息
"""
import asyncio
import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.tracking.click_token import resolve_click_from_token
from app.core.url.url_params_util import (
    merge_association_url_params,
    normalize_url_params,
    parse_stored_url_params,
)
from app.models.models import Click, Offer, Publisher, Advertiser

logger = logging.getLogger(__name__)


class ClickAssociator:
    """Click ID 关联器"""

    @staticmethod
    def _with_normalized_url_params(association: Dict[str, Any]) -> Dict[str, Any]:
        """将关联结果中的 url_params 统一为扁平 dict（兼容 JSON 字符串存储）。"""
        up = association.get("url_params")
        if isinstance(up, dict):
            association = {**association, "url_params": normalize_url_params(up)}
        elif isinstance(up, str) and up.strip():
            association = {
                **association,
                "url_params": parse_stored_url_params(up),
            }
        return association

    @staticmethod
    def _merge_token_and_db_association(
        db_assoc: Dict[str, Any],
        token_assoc: Dict[str, Any],
    ) -> Dict[str, Any]:
        """合并数据库点击行与令牌解析结果，url_params 做键级合并。"""
        # 数据库点击快照与签名 Token 的身份字段必须一致；Token 不得静默覆盖 DB。
        identity_fields = (
            "click_id",
            "offer_id",
            "publisher_id",
            "advertiser_id",
            "short_link_id",
            "client_id",
        )
        conflicts = [
            key
            for key in identity_fields
            if db_assoc.get(key) is not None
            and token_assoc.get(key) is not None
            and str(db_assoc.get(key)) != str(token_assoc.get(key))
        ]
        if conflicts:
            logger.error(
                "Click Token 与数据库身份快照冲突，拒绝归因：fields=%s",
                ",".join(conflicts),
            )
            raise ValueError("Click attribution identity conflict")

        merged = dict(db_assoc)
        for key, value in token_assoc.items():
            if value is None or key == "url_params" or key in identity_fields:
                continue
            merged[key] = value
        # 数据库有点击时快照优先；旧行缺少快照时仅接受签名 Token 的非空客户 ID。
        merged["client_id"] = (
            db_assoc.get("client_id")
            if db_assoc.get("client_id") is not None
            else token_assoc.get("client_id")
        )
        merged["url_params"] = merge_association_url_params(
            db_assoc.get("url_params"),
            token_assoc.get("url_params"),
        )
        return merged

    @staticmethod
    async def associate(
        click_id: Optional[str],
        db: AsyncSession,
    ) -> Optional[Dict[str, Any]]:
        """
        关联 Click：优先解析追踪令牌（新格式），失败则查 clicks 表（旧格式/落库延迟）。
        """
        if not click_id:
            logger.debug("Click ID 为空，无法关联")
            return None

        token_assoc = resolve_click_from_token(click_id)
        if token_assoc:
            # 令牌内 url_params 常为空或已被裁剪；fbclid/dp/email/phone 等多在 clicks 表。
            # 只要 DB 有对应行，始终合并 url_params 与 ip/ua 等落库字段。
            db_assoc = await ClickAssociator.associate_from_db(click_id, db)
            if db_assoc:
                merged = ClickAssociator._merge_token_and_db_association(
                    db_assoc, token_assoc
                )
                merged = await ClickAssociator._enrich_association(merged, db)
                return ClickAssociator._with_normalized_url_params(merged)
            return ClickAssociator._with_normalized_url_params(
                await ClickAssociator._enrich_association(token_assoc, db)
            )

        return await ClickAssociator.associate_from_db(click_id, db)

    @staticmethod
    async def _enrich_association(
        association: Dict[str, Any],
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        令牌解析仅有 ID 时，按需加载 Offer/Publisher/Advertiser ORM（供通知等逻辑使用）。
        转发等流程仅需 publisher_id，不依赖本步骤。
        """
        if not association.get("_from_token"):
            return association

        offer_id = association.get("offer_id")
        publisher_id = association.get("publisher_id")
        advertiser_id = association.get("advertiser_id")

        try:
            if publisher_id and association.get("publisher") is None:
                r = await db.execute(
                    select(Publisher).where(Publisher.id == publisher_id).limit(1)
                )
                association["publisher"] = r.scalars().first()
                # 禁止用 Publisher 当前 client_id 回填历史点击归属；历史 Token/Click 缺快照时保持 None。
            if offer_id and association.get("offer") is None:
                r = await db.execute(
                    select(Offer).where(Offer.id == offer_id).limit(1)
                )
                association["offer"] = r.scalars().first()
            if advertiser_id and association.get("advertiser") is None:
                r = await db.execute(
                    select(Advertiser).where(Advertiser.id == advertiser_id).limit(1)
                )
                association["advertiser"] = r.scalars().first()
        except Exception as e:
            # Enrichment 查询失败属于数据库故障，不等于关联对象不存在。
            # 不得返回半截 Token 身份继续进入 Cap/扣量/转发流程。
            logger.error(
                "令牌关联 ORM enrichment 数据库查询失败，终止归因：error_type=%s",
                type(e).__name__,
            )
            try:
                await db.rollback()
            except Exception as rollback_error:
                logger.critical(
                    "令牌关联 ORM enrichment 失败后的事务回滚也失败：error_type=%s",
                    type(rollback_error).__name__,
                )
            raise

        return association

    @staticmethod
    async def associate_from_db(
        click_id: Optional[str],
        db: AsyncSession,
    ) -> Optional[Dict[str, Any]]:
        """
        通过 clicks 表关联（兼容旧版随机 click_id 及异步落库延迟）。仅对明确的未命中重试；数据库异常回滚后向上传播，避免伪装成 not-found。
        """
        if not click_id:
            logger.debug("Click ID 为空，无法关联")
            return None

        logger.info("开始关联 Click ID（数据库）：present=%s", bool(click_id))
        
        # 使用指数退避策略重试查询，处理批量处理延迟问题（最多约 2.4s）
        max_attempts = 5
        base_delay = 0.3
        
        click = None
        for attempt in range(max_attempts):
            # 查询 Click 记录（带关联的 Offer、Publisher、Advertiser）
            try:
                result = await db.execute(
                    select(Click)
                    .options(
                        joinedload(Click.offer),
                        joinedload(Click.publisher),
                        joinedload(Click.advertiser)
                    )
                    .where(Click.click_id == str(click_id))
                    .limit(1)
                )
                
                click = result.scalars().first()
                
                if click:
                    logger.info("第 %s 次尝试：找到 Click 记录：id=%s", attempt + 1, click.id)
                    break
                else:
                    logger.warning("第 %s 次尝试：未找到 Click 记录", attempt + 1)
                    if attempt < max_attempts - 1:
                        # 指数退避：delay = base_delay * (2 ^ attempt)
                        delay = base_delay * (2 ** attempt)
                        logger.debug(f"等待 {delay:.2f} 秒后重试...")
                        await asyncio.sleep(delay)
            except Exception as e:
                # 查询异常不等于 Click 不存在。SQLAlchemy 事务失败后 Session 可能进入
                # failed state，不能在同一 Session 上继续重试，更不能把 DB 故障降级成 None。
                logger.error(
                    "查询 Click 记录失败，终止归因并交由接收层返回可重试错误：error_type=%s",
                    type(e).__name__,
                )
                try:
                    await db.rollback()
                except Exception as rollback_error:
                    logger.critical(
                        "Click 查询失败后的事务回滚也失败：error_type=%s",
                        type(rollback_error).__name__,
                    )
                raise
        
        if not click:
            logger.error("多次尝试后仍未找到 Click 记录")
            return None
        
        url_params = parse_stored_url_params(click.url_params, for_use=False)
        if url_params:
            logger.debug("成功解析 url_params：字段数=%s", len(url_params))
        elif click.url_params:
            logger.warning("解析 url_params 失败：原始参数已省略")
        
        # 提取关联信息
        association = {
            'click_id': click.click_id,
            'offer_id': click.offer_id,
            'publisher_id': click.publisher_id,
            'advertiser_id': click.advertiser_id,
            'short_link_id': click.short_link_id,
            'click_time': click.click_time,
            'ip': click.ip,
            'user_agent': click.user_agent,
            'country': click.country,
            'device': click.device,
            'os': click.os,
            'offer': click.offer,
            'publisher': click.publisher,
            # 客户归属以点击时的渠道配置为准，不能信任回调请求体中的 client_id。
            'client_id': click.client_id,
            'advertiser': click.advertiser,
            'url_params': url_params,
        }
        
        logger.info(
            f"Click ID 关联成功：click_id={click_id}, "
            f"offer_id={click.offer_id}, publisher_id={click.publisher_id}"
        )

        return ClickAssociator._with_normalized_url_params(association)
