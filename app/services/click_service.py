"""
短链接访问记录服务层
封装点击记录查询的业务逻辑
"""
import json
import logging
from datetime import timedelta
from time import perf_counter
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, load_only

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.utils import parse_date_to_app_timezone, get_app_now_naive
from app.core.url.url_params_util import normalize_url_params
from app.models.models import Click, Offer, Publisher, Advertiser, ShortLink

logger = logging.getLogger(__name__)


class ClickService:
    """短链接访问记录服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _parse_json_text_field(raw: Any) -> Any:
        """将 ORM Text 中的 JSON 字段解析为对象；解析失败则原样返回。"""
        if raw is None or raw == "":
            return None
        if isinstance(raw, (dict, list)):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    @staticmethod
    def _serialize_click(click: Click, include_heavy_fields: bool = False) -> Dict[str, Any]:
        """序列化点击记录，列表场景默认不返回大字段以提升性能。"""
        click_data = {
            "id": click.id,
            "click_id": click.click_id,
            "click_time": click.click_time.isoformat() if click.click_time else None,
            "ip": click.ip,
            "device": click.device,
            "country": click.country,
            "referer": click.referer,
            "conversion_id": click.conversion_id,
            "created_at": click.created_at.isoformat() if click.created_at else None,
            "offer_id": click.offer_id,
            "offer_name": click.offer.offer_name if click.offer else None,
            "publisher_id": click.publisher_id,
            "publisher_name": click.publisher.publisher_name if click.publisher else None,
            "advertiser_id": click.advertiser_id,
            "advertiser_name": click.advertiser.advertiser_name if click.advertiser else None,
            "short_link_id": click.short_link_id,
            "short_code": click.short_link.short_code if click.short_link else None,
            "os": click.os,
            "os_version": click.os_version,
            "browser": click.browser,
            "browser_version": click.browser_version,
            "accept_language": click.accept_language,
            "accept_encoding": click.accept_encoding,
            "is_bot": click.is_bot,
            "device_type": click.device_type,
            "device_brand": click.device_brand,
            "device_model": click.device_model,
        }

        if include_heavy_fields:
            parsed_url_params = ClickService._parse_json_text_field(click.url_params)
            click_data.update({
                "user_agent": click.user_agent,
                "short_link_title": click.short_link.title if click.short_link else None,
                "short_link_url": click.short_link.original_url if click.short_link else None,
                "url_params": parsed_url_params,
                "url_params_normalized": (
                    normalize_url_params(parsed_url_params)
                    if isinstance(parsed_url_params, dict)
                    else {}
                ),
                "all_headers": ClickService._parse_json_text_field(click.all_headers),
                "original_request_url": click.original_request_url,
                "final_redirect_url": click.final_redirect_url,
            })

        return click_data

    async def get_clicks(
            self,
            page: int = 1,
            page_size: int = 20,
            click_id: Optional[str] = None,
            conversion_id: Optional[str] = None,
            offer_id: Optional[int] = None,
            publisher_id: Optional[int] = None,
            advertiser_id: Optional[int] = None,
            short_link_id: Optional[int] = None,
            ip: Optional[str] = None,
            country: Optional[str] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        获取短链接访问记录列表

        Args:
            page: 页码
            page_size: 每页数量
            click_id: Click ID过滤
            conversion_id: 转化ID过滤
            offer_id: Offer ID过滤
            publisher_id: 渠道ID过滤
            advertiser_id: 广告主ID过滤
            short_link_id: 短链接ID过滤
            ip: IP地址过滤
            country: 国家过滤
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）

        Returns:
            Tuple[List[Dict], int]: (点击记录列表, 总数)
        """
        started_at = perf_counter()

        # 解析日期（使用应用时区，与数据库时间一致）
        start_datetime = None
        end_datetime = None

        # 如果没有提供日期范围，默认查询最近7天
        # 但如果提供了conversion_id或click_id，不设置默认日期范围，查询所有时间
        if not start_date and not end_date:
            if not click_id and not conversion_id:
                now = get_app_now_naive()
                end_datetime = now
                start_datetime = now - timedelta(days=7)
                logger.debug(f"未提供日期范围，默认查询最近7天: {start_datetime} 至 {end_datetime}")
        else:
            if start_date:
                start_datetime = parse_date_to_app_timezone(start_date, is_end_date=False)
            if end_date:
                end_datetime = parse_date_to_app_timezone(end_date, is_end_date=True)

        # 如果提供了日期范围，检查是否超过90天（防止查询过大数据量）
        if start_datetime and end_datetime:
            date_range_days = (end_datetime - start_datetime).days
            if date_range_days > 90:
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail=f"查询日期范围不能超过90天，当前范围：{date_range_days}天。请缩小查询范围或使用筛选条件。"
                )
            if date_range_days < 0:
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="开始日期不能晚于结束日期"
                )

        # 构建查询 - 使用 joinedload 预加载关联数据，避免 N+1 查询
        query = select(Click).options(
            load_only(
                Click.id,
                Click.click_id,
                Click.click_time,
                Click.ip,
                Click.device,
                Click.country,
                Click.referer,
                Click.conversion_id,
                Click.created_at,
                Click.offer_id,
                Click.publisher_id,
                Click.advertiser_id,
                Click.short_link_id,
                Click.os,
                Click.os_version,
                Click.browser,
                Click.browser_version,
                Click.accept_language,
                Click.accept_encoding,
                Click.is_bot,
                Click.device_type,
                Click.device_brand,
                Click.device_model,
            ),
            joinedload(Click.offer).load_only(Offer.id, Offer.offer_name),
            joinedload(Click.publisher).load_only(Publisher.id, Publisher.publisher_name),
            joinedload(Click.advertiser).load_only(Advertiser.id, Advertiser.advertiser_name),
            joinedload(Click.short_link).load_only(ShortLink.id, ShortLink.short_code)
        )

        conditions = []

        if click_id:
            conditions.append(Click.click_id == click_id)

        if conversion_id:
            conditions.append(Click.conversion_id == conversion_id)

        if offer_id:
            conditions.append(Click.offer_id == offer_id)

        if publisher_id:
            conditions.append(Click.publisher_id == publisher_id)

        if advertiser_id:
            conditions.append(Click.advertiser_id == advertiser_id)

        if short_link_id:
            conditions.append(Click.short_link_id == short_link_id)

        if ip:
            # 优化：使用精确匹配或前缀匹配，避免全表扫描
            # 如果IP包含通配符，使用LIKE；否则使用精确匹配（更快）
            ip_trimmed = ip.strip()
            if '%' in ip_trimmed or '_' in ip_trimmed:
                # 用户明确使用通配符，使用LIKE
                conditions.append(Click.ip.like(ip_trimmed))
            elif '.' in ip_trimmed:
                # IPv4地址，支持精确匹配或前缀匹配（如 192.168.）
                if ip_trimmed.endswith('.'):
                    # 前缀匹配，如 "192.168." -> "192.168.%"
                    conditions.append(Click.ip.like(f"{ip_trimmed}%"))
                else:
                    # 精确匹配，性能最好
                    conditions.append(Click.ip == ip_trimmed)
            else:
                # 其他情况，使用精确匹配
                conditions.append(Click.ip == ip_trimmed)

        if country:
            conditions.append(Click.country == country)

        if start_datetime:
            conditions.append(Click.click_time >= start_datetime)
        if end_datetime:
            conditions.append(Click.click_time <= end_datetime)

        if conditions:
            query = query.where(and_(*conditions))

        # 计算总数
        count_query = select(func.count(Click.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))

        count_started_at = perf_counter()
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        count_elapsed_ms = int((perf_counter() - count_started_at) * 1000)

        # 分页和排序
        query = query.order_by(Click.click_time.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        list_started_at = perf_counter()
        result = await self.db.execute(query)
        clicks = result.unique().scalars().all()
        list_elapsed_ms = int((perf_counter() - list_started_at) * 1000)

        serialize_started_at = perf_counter()
        click_list = [self._serialize_click(click, include_heavy_fields=False) for click in clicks]
        serialize_elapsed_ms = int((perf_counter() - serialize_started_at) * 1000)

        total_elapsed_ms = int((perf_counter() - started_at) * 1000)
        log_msg = (
            "短链接访问记录列表耗时: total=%sms, count=%sms, query=%sms, serialize=%sms, "
            "rows=%s, total_count=%s, page=%s, page_size=%s"
        )
        log_args = (
            total_elapsed_ms,
            count_elapsed_ms,
            list_elapsed_ms,
            serialize_elapsed_ms,
            len(click_list),
            total,
            page,
            page_size,
        )
        if total_elapsed_ms >= 1500:
            logger.warning(log_msg, *log_args)
        else:
            logger.info(log_msg, *log_args)

        return click_list, total

    async def get_click_detail(self, click_record_id: int) -> Dict[str, Any]:
        """获取单条点击记录详情（包含大字段）。"""
        query = (
            select(Click)
            .options(
                joinedload(Click.offer).load_only(Offer.id, Offer.offer_name),
                joinedload(Click.publisher).load_only(Publisher.id, Publisher.publisher_name),
                joinedload(Click.advertiser).load_only(Advertiser.id, Advertiser.advertiser_name),
                joinedload(Click.short_link).load_only(
                    ShortLink.id,
                    ShortLink.short_code,
                    ShortLink.title,
                    ShortLink.original_url,
                ),
            )
            .where(Click.id == click_record_id)
        )

        result = await self.db.execute(query)
        click = result.unique().scalar_one_or_none()

        if not click:
            raise_api_exception(ErrorCode.NOT_FOUND, detail="点击记录不存在")

        return self._serialize_click(click, include_heavy_fields=True)
