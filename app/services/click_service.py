"""
短链接访问记录（点击日志）服务层。

功能说明：
- 点击记录分页查询与详情（列表省略 url_params/all_headers 等大字段）
- 默认最近 7 天范围；按 click_id/conversion_id 精确查时不限时间窗口
- 支持手动补报 Facebook Purchase 事件（像素配置短链→斗篷→全局多级回退）

在系统中的位置：
- 被管理端点击日志 API 调用；补报委托 ``send_third_party_report``

注意事项：
1. 列表使用 load_only + joinedload；慢查询（≥1.5s）打 warning 便于索引优化
2. 补报前须校验转化是否已存在，避免重复 CAPI 事件
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

from app.core.config import settings
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.third_party_report import send_third_party_report
from app.core.utils import parse_date_to_app_timezone, get_app_now_naive
from app.core.url.url_params_util import (
    normalize_url_params,
    parse_stored_url_params,
    resolve_dp_from_url_params,
    scalar_query_value,
)
from app.models.models import Click, Offer, Publisher, Advertiser, ShortLink, PostbackConversion
from app.services.cloak_pixel_mapping import get_cloak_pixel_config

logger = logging.getLogger(__name__)


class ClickService:
    """
    点击日志服务。

    查询侧强调日期范围护栏与 IP 匹配策略；补报侧按
    短链自定义像素 → 斗篷配置 → 全局配置 解析 Facebook 凭证。
    """

    def __init__(self, db: AsyncSession):
        """注入异步数据库会话。"""
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
        """
        将 Click ORM 转为 API 字典。

        列表默认省略 user_agent/url_params/all_headers 等大字段；
        详情页传 include_heavy_fields=True 返回完整诊断信息。
        """
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

    @staticmethod
    def _build_facebook_report_payload(
            click: Click,
            conversion: PostbackConversion,
            url_params: Dict[str, Any],
            facebook_pixel_id: str,
            facebook_access_token: str,
            facebook_api_version: str
    ) -> Dict[str, Any]:
        """
        组装 Facebook CAPI 补报 payload。

        从 url_params 解析 adsid（fbclid/click_id/cid 优先级）及联系字段；
        转化金额须 > 0 才允许 Purchase 事件。

        Raises:
            VALIDATION_ERROR: 缺少 adsid 或金额无效
        """
        fbclid = scalar_query_value(url_params.get("fbclid"))
        click_id_in_url = scalar_query_value(url_params.get("click_id"))
        cid_in_url = scalar_query_value(url_params.get("cid"))
        email = scalar_query_value(url_params.get("email"))
        phone = scalar_query_value(url_params.get("phone"))
        adsid = fbclid or click_id_in_url or cid_in_url or (click.click_id or "").strip()
        if not adsid:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="该记录缺少可用于上报的 adsid（fbclid/click_id）"
            )

        amount = conversion.payout
        if amount is None or amount <= 0:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="该转化金额无效（<=0），无法补报 Purchase"
            )

        return {
            "adsid": adsid,
            "event": "Purchase",
            "email": email or "",
            "ip": (click.ip or "").strip(),
            "phone": phone or "",
            "ua": (click.user_agent or "").strip(),
            "source": "click_log_manual_retry",
            "conversion_id": str(conversion.id)[:200],
            "currency": "USD",
            "amount": float(amount),
            "click_time": click.click_time,
            "facebook_pixel_id": facebook_pixel_id,
            "facebook_access_token": facebook_access_token,
            "facebook_api_version": facebook_api_version,
        }

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
        分页查询短链接点击记录。

        未传日期且非精确 click_id/conversion_id 查询时，默认最近 7 天；
        显式日期范围不得超过 90 天。

        Args:
            page/page_size: 分页
            click_id/conversion_id: 精确 ID 过滤（存在时跳过默认 7 天）
            offer_id/publisher_id/advertiser_id/short_link_id: 业务维度过滤
            ip: 支持精确、前缀或 LIKE 通配
            country: 国家码
            start_date/end_date: YYYY-MM-DD，应用时区解析

        Returns:
            (序列化后的点击字典列表, 总条数)
        """
        started_at = perf_counter()

        # --- 时间范围：默认 7 天 / 解析入参 / 90 天上限 ---
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

        # --- 查询体：load_only 减列 + joinedload 防 N+1 ---
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
            ip_trimmed = ip.strip()
            # 通配符 → LIKE；IPv4 尾点 → 前缀；否则精确匹配
            if '%' in ip_trimmed or '_' in ip_trimmed:
                conditions.append(Click.ip.like(ip_trimmed))
            elif '.' in ip_trimmed:
                if ip_trimmed.endswith('.'):
                    conditions.append(Click.ip.like(f"{ip_trimmed}%"))
                else:
                    conditions.append(Click.ip == ip_trimmed)
            else:
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
        """
        获取单条点击详情（含 user_agent、url_params、headers 等大字段）。

        Args:
            click_record_id: clicks 表主键 id（非 click_id 字符串）

        Returns:
            完整序列化字典

        Raises:
            NOT_FOUND: 记录不存在
        """
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

    async def resend_facebook_report(self, click_record_id: int) -> Dict[str, Any]:
        """
        对已转化点击手动补报 Facebook Purchase 事件。

        须存在 conversion_id 及有效 PostbackConversion；像素凭证按
        短链级 → 斗篷(dp+short_code) → settings 全局 三级解析。

        Args:
            click_record_id: clicks 表主键

        Returns:
            补报摘要（pixel 来源、conversion_id、dp 等）

        Raises:
            NOT_FOUND / VALIDATION_ERROR: 记录或转化缺失、未转化、参数不足
        """
        click_query = (
            select(Click)
            .options(joinedload(Click.short_link))
            .where(Click.id == click_record_id)
        )
        click_result = await self.db.execute(click_query)
        click = click_result.unique().scalar_one_or_none()
        if not click:
            raise_api_exception(ErrorCode.NOT_FOUND, detail="点击记录不存在")
        if not click.conversion_id:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="该点击记录尚未转化，无法进行补报"
            )

        conv_result = await self.db.execute(
            select(PostbackConversion).where(PostbackConversion.id == click.conversion_id)
        )
        conversion = conv_result.scalars().first()
        if not conversion:
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                detail=f"未找到关联转化记录：{click.conversion_id}"
            )

        url_params = parse_stored_url_params(click.url_params)
        dp = resolve_dp_from_url_params(url_params)
        short_code = click.short_link.short_code if click.short_link else None

        facebook_pixel_id = settings.FACEBOOK_PIXEL_ID
        facebook_access_token = settings.FACEBOOK_ACCESS_TOKEN
        facebook_api_version = settings.FACEBOOK_API_VERSION
        config_source = "全局配置"

        # 像素凭证优先级：短链自定义 > 斗篷配置 > 全局 settings
        if click.short_link and click.short_link.facebook_pixel_id and click.short_link.facebook_access_token:
            facebook_pixel_id = click.short_link.facebook_pixel_id
            facebook_access_token = click.short_link.facebook_access_token
            facebook_api_version = click.short_link.facebook_api_version or settings.FACEBOOK_API_VERSION
            config_source = f"短链接配置(short_link_id={click.short_link_id})"
        elif dp and short_code:
            try:
                cloak_cfg = await get_cloak_pixel_config(
                    db=self.db,
                    dp=dp,
                    short_code=short_code,
                    use_cache=True
                )
                if cloak_cfg:
                    facebook_pixel_id = cloak_cfg.get("facebook_pixel_id") or facebook_pixel_id
                    facebook_access_token = cloak_cfg.get("facebook_access_token") or facebook_access_token
                    facebook_api_version = cloak_cfg.get("facebook_api_version") or facebook_api_version
                    config_source = f"斗篷配置(dp={dp})"
            except Exception as exc:
                logger.warning("获取斗篷像素配置失败，继续使用默认配置: %s", exc)

        payload = self._build_facebook_report_payload(
            click=click,
            conversion=conversion,
            url_params=url_params,
            facebook_pixel_id=facebook_pixel_id,
            facebook_access_token=facebook_access_token,
            facebook_api_version=facebook_api_version,
        )
        await send_third_party_report(**payload)

        logger.info(
            "点击记录手动补报成功: click_record_id=%s click_id=%s conversion_id=%s source=%s",
            click_record_id,
            click.click_id,
            click.conversion_id,
            config_source,
        )

        return {
            "click_record_id": click_record_id,
            "click_id": click.click_id,
            "conversion_id": click.conversion_id,
            "dp": dp,
            "pixel_config_source": config_source,
            "facebook_pixel_id": facebook_pixel_id,
        }
