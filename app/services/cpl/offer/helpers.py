"""
Offer 查询共用辅助函数。
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.models.models import (
    Client,
    OfferPublisherAssignment,
    Publisher,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)

PublisherConfigTuple = Tuple[int, Optional[int], Optional[float]]


async def get_client_id_for_user(db: AsyncSession, user: User) -> Optional[int]:
    """获取客户用户关联的 Client.id。"""
    if user.role != UserRole.CLIENT:
        return None
    result = await db.execute(select(Client.id).where(Client.user_id == user.id).limit(1))
    return result.scalar_one_or_none()


async def assert_client_can_access_offer(
    db: AsyncSession,
    offer_id: int,
    user: User,
) -> None:
    """客户用户须存在激活的 Offer-渠道分配。"""
    if user.role != UserRole.CLIENT:
        return

    client_id = await get_client_id_for_user(db, user)
    if not client_id:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Offer ID {offer_id} 不存在或无权访问",
        )

    check_result = await db.execute(
        select(OfferPublisherAssignment)
        .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
        .where(
            and_(
                OfferPublisherAssignment.offer_id == offer_id,
                Publisher.client_id == client_id,
                Publisher.is_active == True,
                OfferPublisherAssignment.is_active == True,
            )
        )
        .limit(1)
    )
    if not check_result.scalar_one_or_none():
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Offer ID {offer_id} 不存在或无权访问",
        )


def assignment_to_dict(assignment: OfferPublisherAssignment, publisher: Publisher) -> Dict[str, Any]:
    """渠道分配 ORM 转为 API 字典。"""
    return {
        "id": publisher.id,
        "publisher_name": publisher.publisher_name,
        "client_id": publisher.client_id,
        "downstream_cap": assignment.downstream_cap,
        "affiliate_payout": assignment.affiliate_payout,
    }


def parse_publisher_configs(publisher_configs) -> List[PublisherConfigTuple]:
    """
    解析并校验 publisher_configs，返回 (publisher_id, downstream_cap, affiliate_payout) 列表。

    Raises:
        HTTPException: 参数非法时通过 raise_api_exception 抛出
    """
    if publisher_configs is None:
        return []

    if len(publisher_configs) == 0:
        raise_api_exception(
            ErrorCode.INVALID_PARAMETER,
            detail="渠道配置不能为空，请至少添加一个渠道",
        )

    publisher_id_list = [
        config.get("publisher_id") if isinstance(config, dict) else config.publisher_id
        for config in publisher_configs
    ]
    valid_publisher_ids = [pid for pid in publisher_id_list if pid is not None]
    if len(valid_publisher_ids) != len(set(valid_publisher_ids)):
        raise_api_exception(
            ErrorCode.INVALID_PARAMETER,
            detail="渠道配置中存在重复的渠道ID",
        )

    parsed: List[PublisherConfigTuple] = []
    for config in publisher_configs:
        if isinstance(config, dict):
            pub_id = config.get("publisher_id")
            downstream_cap = config.get("downstream_cap")
            affiliate_payout = config.get("affiliate_payout")
        else:
            pub_id = config.publisher_id
            downstream_cap = config.downstream_cap
            affiliate_payout = config.affiliate_payout

        if pub_id is None:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="渠道配置中的publisher_id不能为空，请确保已选择渠道",
            )

        try:
            pub_id = int(pub_id)
        except (ValueError, TypeError):
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail=f"渠道配置中的publisher_id必须是整数，当前值: {pub_id} (类型: {type(pub_id).__name__})",
            )

        if pub_id <= 0:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail=f"渠道配置中的publisher_id必须大于0，当前值: {pub_id}",
            )

        if downstream_cap is not None:
            try:
                downstream_cap = int(downstream_cap)
            except (ValueError, TypeError):
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail=f"渠道ID {pub_id} 的下游Cap必须是整数，当前值: {downstream_cap} (类型: {type(downstream_cap).__name__})",
                )

        if affiliate_payout is not None:
            try:
                affiliate_payout = float(affiliate_payout)
            except (ValueError, TypeError):
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail=f"渠道ID {pub_id} 的下游PO必须是数字，当前值: {affiliate_payout} (类型: {type(affiliate_payout).__name__})",
                )

        if downstream_cap is not None and downstream_cap < 0:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail=f"渠道ID {pub_id} 的下游Cap不能为负数",
            )

        if affiliate_payout is not None and affiliate_payout < 0:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail=f"渠道ID {pub_id} 的下游PO不能为负数",
            )

        parsed.append((pub_id, downstream_cap, affiliate_payout))
    return parsed


async def load_publishers_by_ids(db: AsyncSession, pub_ids: List[int]) -> Dict[int, Publisher]:
    """批量加载渠道，缺失 ID 时抛出 RESOURCE_NOT_FOUND。"""
    if not pub_ids:
        return {}
    result = await db.execute(select(Publisher).where(Publisher.id.in_(pub_ids)))
    publishers_by_id = {p.id: p for p in result.scalars().all()}
    for pub_id in pub_ids:
        if pub_id not in publishers_by_id:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"渠道ID {pub_id} 不存在",
            )
    return publishers_by_id


def build_tracking_urls(offer_id: int, base_url: str) -> Tuple[str, str]:
    """生成下游 Tracklink 与 Postback URL。"""
    base = base_url.rstrip("/")
    downstream = f"{base}/api/v1/track/click/{offer_id}?publisher_id={{publisher_id}}"
    postback = f"{base}/api/v1/postback?click_id={{click_id}}&offer_id={offer_id}"
    return downstream, postback


def extract_short_code_from_url(url: str) -> Optional[str]:
    """从下游 Tracklink URL 中解析短码（/s/{short_code}）。"""
    if not url:
        return None

    try:
        path = urlparse(url).path
        if "/s/" in path:
            parts = path.split("/s/")
            if len(parts) > 1:
                short_code = parts[1].split("/")[0].split("?")[0]
                if short_code:
                    return short_code.strip()

        if path.startswith("/s/"):
            short_code = path[3:].split("/")[0].split("?")[0]
            if short_code:
                return short_code.strip()
        return None
    except Exception as e:
        logger.warning("提取短链接代码失败: url=%s, error=%s", url, str(e))
        return None
