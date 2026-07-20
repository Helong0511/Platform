"""
广告数据（AdData）导入与聚合处理工具。

职责：解析上游 API/Excel 原始行、国家代码映射、比率计算、批量入库；
eCPM/收益按减扣前/后各汇总一条 Telegram，流量指标汇总一条（均按产品、国家排序，超长连续拆分）。

在系统中的位置：``app.core.ad_data_processor``，由定时拉取任务与管理端导入 API 调用。
"""
import logging
import asyncio
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set
import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models.models import AdData, User
from app.core.audit_log import log_user_action
from app.core.country_code import (
    build_ad_data_country_equality,
    find_country_code_by_any_format,
    format_country_display,
    preserve_unrecognized_country_code,
    resolve_country_display,
)
from app.core.ad_data_metadata import (
    DATA_SOURCE_UNKNOWN,
    REPORT_TYPE_LEGACY,
    normalize_report_type,
    normalize_upstream_account,
    resolve_report_type_for_row,
)
from app.core.utils import (
    apply_deduct_ratio,
    normalize_ad_unit,
    normalize_date_for_ad_data,
)
from app.core.telegram import send_telegram_notify_async
from app.core.config import settings

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)


def _metric_is_zero_int(value: Any) -> bool:
    return int(value or 0) == 0


def _metric_is_zero_float(value: Any) -> bool:
    return abs(float(value or 0.0)) < 1e-9


def _as_float(value: Any) -> float:
    """将 Decimal/None/数值统一为 float，避免 DECIMAL 列与 float 混算报错。"""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _metric_differs(existing_value: Any, new_value: Any, threshold: float = 0.01) -> bool:
    """比较 DECIMAL 列与 float 新值是否超出阈值。"""
    return abs(_as_float(existing_value) - _as_float(new_value)) > threshold


def is_empty_ad_metrics(
    *,
    request_count: int = 0,
    match_count: int = 0,
    display_count: int = 0,
    click_count: int = 0,
    revenue: float = 0.0,
    pageviews: int = 0,
    viewability_rate: float = 0.0,
    cpc: float = 0.0,
    ecpm: float = 0.0,
) -> bool:
    """所有可入库数值指标均为 0 时视为无有效数据；任一非零则保留。"""
    return (
        _metric_is_zero_int(request_count)
        and _metric_is_zero_int(match_count)
        and _metric_is_zero_int(display_count)
        and _metric_is_zero_int(click_count)
        and _metric_is_zero_int(pageviews)
        and _metric_is_zero_float(revenue)
        and _metric_is_zero_float(viewability_rate)
        and _metric_is_zero_float(cpc)
        and _metric_is_zero_float(ecpm)
    )


def _grouped_data_is_empty(grouped_data: Dict[str, Any]) -> bool:
    return is_empty_ad_metrics(
        request_count=grouped_data.get("request_count", 0),
        match_count=grouped_data.get("match_count", 0),
        display_count=grouped_data.get("display_count", 0),
        click_count=grouped_data.get("click_count", 0),
        revenue=grouped_data.get("revenue", 0.0),
        pageviews=grouped_data.get("pageviews", 0),
        viewability_rate=grouped_data.get("viewability_rate", 0.0),
        cpc=grouped_data.get("cpc", 0.0),
        ecpm=grouped_data.get("ecpm", 0.0),
    )


def _ad_data_identity_filters(
    *,
    product_id: int,
    storage_date: date,
    country_code,
    ad_unit: str,
    data_source: str,
    report_type: str,
    upstream_account: str,
):
    """构建 ad_data 唯一性查询条件（含来源、报表维度与上游账号）。"""
    return [
        AdData.date == storage_date,
        AdData.product_id == product_id,
        build_ad_data_country_equality(AdData.country_code, country_code),
        AdData.ad_unit == ad_unit,
        AdData.data_source == data_source,
        AdData.report_type == report_type,
        AdData.upstream_account == normalize_upstream_account(upstream_account),
    ]


def _report_type_lookup_condition(row_report_type: str):
    """导入查重：推断出的非 legacy 类型可同时匹配旧 legacy 行以便升级 report_type。"""
    if row_report_type == REPORT_TYPE_LEGACY:
        return AdData.report_type == REPORT_TYPE_LEGACY
    return or_(
        AdData.report_type == row_report_type,
        AdData.report_type == REPORT_TYPE_LEGACY,
    )


async def _find_existing_ad_data_for_import(
    db: AsyncSession,
    *,
    product_id: int,
    ad_date,
    country_code,
    ad_unit: str,
    data_source: str,
    row_report_type: str,
    upstream_account: str,
):
    """按唯一键查找已有行；legacy 行在推断入库时可被匹配并升级 report_type。"""
    storage_date = normalize_date_for_ad_data(ad_date)
    filters = [
        AdData.date == storage_date,
        AdData.product_id == product_id,
        build_ad_data_country_equality(AdData.country_code, country_code),
        AdData.ad_unit == ad_unit,
        AdData.data_source == data_source,
        AdData.upstream_account == normalize_upstream_account(upstream_account),
        _report_type_lookup_condition(row_report_type),
    ]
    result = await db.execute(select(AdData).where(*filters))
    return result.scalars().first()

# 应用时区配置（从统一配置读取）
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)


METRIC_DECREASE_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("ecpm_before", "⚠️ eCPM(减扣前)减少汇总", "eCPM(减扣前)"),
    ("ecpm_after", "⚠️ eCPM(减扣后)减少汇总", "eCPM(减扣后)"),
    ("revenue_before", "⚠️ 收益(减扣前)减少汇总", "收益(减扣前)"),
    ("revenue_after", "⚠️ 收益(减扣后)减少汇总", "收益(减扣后)"),
)

_METRIC_DECREASE_NOTICE = (
    "⚠️ 注意：API获取的数据正常情况下应该比上一次获得的数据大（累积增长）\n"
    "如果 eCPM / 收益减少，可能是数据源异常或数据被重置，请检查数据源。"
)


def _sort_decrease_items(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return sorted(
        items,
        key=lambda x: (
            str(x.get("product_name") or ""),
            str(x.get("country_display") or x.get("country_code") or ""),
            str(x.get("date_str") or ""),
        ),
    )


def _resolve_decrease_source_label(
    items: list[Dict[str, Any]],
    *,
    source_hint: str = "API",
) -> str:
    sources = {str(x.get("source") or "") for x in items if x.get("source")}
    return " / ".join(sorted(sources)) if sources else source_hint


def format_decrease_summary(
    items: list[Dict[str, Any]],
    *,
    title: str,
    record_description: str,
    notice: str,
    source_hint: str = "API",
) -> Optional[str]:
    """将减少条目汇总为一条 Telegram 文案，按产品、国家、日期排序。"""
    if not items:
        return None

    sorted_items = _sort_decrease_items(items)
    source_label = _resolve_decrease_source_label(sorted_items, source_hint=source_hint)
    current_time_str = datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = [
        title,
        "",
        f"数据来源: {source_label}",
        f"发送时间: {current_time_str}（时区: {settings.TIMEZONE}）",
        f"共 {len(sorted_items)} 条记录存在{record_description}",
        "",
        notice,
        "",
    ]

    current_product: Optional[str] = None
    for item in sorted_items:
        product_name = str(item.get("product_name") or "未知产品")
        if product_name != current_product:
            if current_product is not None:
                lines.append("")
            lines.append(f"【{product_name}】")
            current_product = product_name

        country_display = item.get("country_display") or item.get("country_code") or "-"
        date_str = item.get("date_str") or "-"
        lines.append(f"  国家: {country_display} | 日期: {date_str}")
        for field in item.get("fields") or []:
            lines.append(f"  • {field}")

    lines.append("")
    lines.append("✅ 已按上游新数据更新本地记录")
    return "\n".join(lines)


def _append_decrease_result(
    decrease_result: Optional[Dict[str, Any]],
    *,
    pending_traffic_decreases: list[Dict[str, Any]],
    pending_metric_decreases: list[Dict[str, Any]],
) -> None:
    if not decrease_result:
        return
    traffic_item = decrease_result.get("traffic_item")
    if traffic_item:
        pending_traffic_decreases.append(traffic_item)
    pending_metric_decreases.extend(decrease_result.get("metric_items") or [])


async def build_data_decrease_warning(
        existing_data: Any,
        new_request_count: int,
        new_match_count: int,
        new_display_count: int,
        new_click_count: int,
        new_revenue_before: float,
        new_revenue_after: float,
        date_str: str,
        product_name: str,
        country_code: Optional[str],
        source: str = "API",
        db: Optional[AsyncSession] = None,
        new_ecpm_before: float = 0.0,
        new_ecpm_after: float = 0.0,
) -> Optional[Dict[str, Any]]:
    """
    检查待更新数据是否比原有数据减少。

    返回字典（无减少时返回 None）：
    - metric_items: eCPM/收益减少条目，按类型汇总后发 Telegram
    - traffic_item: 流量类指标减少条目，供批次汇总（可无）
    """
    try:
        traffic_fields: list[str] = []
        metric_items: list[Dict[str, Any]] = []
        float_threshold = 0.01

        request_decrease = existing_data.request_count - new_request_count
        if request_decrease > 0:
            traffic_fields.append(
                f"请求数: 原有 {existing_data.request_count} → 新获取 {new_request_count} (减少 {request_decrease})")

        match_decrease = existing_data.match_count - new_match_count
        if match_decrease > 0:
            traffic_fields.append(
                f"匹配数: 原有 {existing_data.match_count} → 新获取 {new_match_count} (减少 {match_decrease})")

        display_decrease = existing_data.display_count - new_display_count
        if display_decrease > 0:
            traffic_fields.append(
                f"展示数: 原有 {existing_data.display_count} → 新获取 {new_display_count} (减少 {display_decrease})")

        click_decrease = existing_data.click_count - new_click_count
        if click_decrease > 0:
            traffic_fields.append(
                f"点击数: 原有 {existing_data.click_count} → 新获取 {new_click_count} (减少 {click_decrease})")

        ecpm_before_decrease = _as_float(existing_data.ecpm_before_deduct) - _as_float(new_ecpm_before)
        if ecpm_before_decrease > float_threshold:
            metric_items.append({
                "metric_type": "ecpm_before",
                "fields": [
                    f"原有 {_as_float(existing_data.ecpm_before_deduct):.2f} → "
                    f"新获取 {_as_float(new_ecpm_before):.2f} (减少 {ecpm_before_decrease:.2f})"
                ],
            })

        ecpm_after_decrease = _as_float(existing_data.ecpm_after_deduct) - _as_float(new_ecpm_after)
        if ecpm_after_decrease > float_threshold:
            metric_items.append({
                "metric_type": "ecpm_after",
                "fields": [
                    f"原有 {_as_float(existing_data.ecpm_after_deduct):.2f} → "
                    f"新获取 {_as_float(new_ecpm_after):.2f} (减少 {ecpm_after_decrease:.2f})"
                ],
            })

        revenue_before_decrease = _as_float(existing_data.revenue_before_deduct) - _as_float(new_revenue_before)
        if revenue_before_decrease > float_threshold:
            metric_items.append({
                "metric_type": "revenue_before",
                "fields": [
                    f"原有 {_as_float(existing_data.revenue_before_deduct):.2f} → "
                    f"新获取 {_as_float(new_revenue_before):.2f} (减少 {revenue_before_decrease:.2f})"
                ],
            })

        revenue_after_decrease = _as_float(existing_data.revenue_after_deduct) - _as_float(new_revenue_after)
        if revenue_after_decrease > float_threshold:
            metric_items.append({
                "metric_type": "revenue_after",
                "fields": [
                    f"原有 {_as_float(existing_data.revenue_after_deduct):.2f} → "
                    f"新获取 {_as_float(new_revenue_after):.2f} (减少 {revenue_after_decrease:.2f})"
                ],
            })

        if not traffic_fields and not metric_items:
            return None

        if db is not None:
            country_display = await resolve_country_display(db, country_code)
        else:
            country_display = format_country_display(country_code)

        result: Dict[str, Any] = {
            "metric_items": [],
            "traffic_item": None,
        }

        if traffic_fields:
            logger.warning(
                "流量指标减少: 来源=%s 日期=%s 产品=%s 国家=%s | %s",
                source,
                date_str,
                product_name,
                country_code or "-",
                "; ".join(traffic_fields),
            )
            result["traffic_item"] = {
                "date_str": date_str,
                "product_name": product_name,
                "country_code": country_code or "",
                "country_display": country_display,
                "source": source,
                "fields": traffic_fields,
            }

        for metric_item in metric_items:
            logger.warning(
                "指标减少: 类型=%s 来源=%s 日期=%s 产品=%s 国家=%s | %s",
                metric_item["metric_type"],
                source,
                date_str,
                product_name,
                country_code or "-",
                "; ".join(metric_item["fields"]),
            )
            result["metric_items"].append({
                **metric_item,
                "date_str": date_str,
                "product_name": product_name,
                "country_code": country_code or "",
                "country_display": country_display,
                "source": source,
            })

        return result
    except Exception as e:
        logger.warning(f"构建数据减少警告时出错: {e}")
        return None


def format_traffic_decrease_summary(
    traffic_items: list[Dict[str, Any]],
    *,
    source_hint: str = "API",
) -> Optional[str]:
    """将流量类指标减少条目汇总为一条 Telegram 文案，按产品、国家排序。"""
    return format_decrease_summary(
        traffic_items,
        title="⚠️ 流量指标减少汇总",
        record_description="请求数/匹配数/展示数/点击数减少",
        notice="⚠️ 正常情况下上游数据应为累积增长；流量回落请核对数据源。",
        source_hint=source_hint,
    )


def format_metric_decrease_summary(
    metric_items: list[Dict[str, Any]],
    *,
    metric_type: str,
    source_hint: str = "API",
) -> Optional[str]:
    """将某一类 eCPM/收益减少条目汇总为一条 Telegram 文案。"""
    category = next(
        (item for item in METRIC_DECREASE_CATEGORIES if item[0] == metric_type),
        None,
    )
    if not category:
        return None
    _, title, metric_label = category
    filtered_items = [
        item for item in metric_items if item.get("metric_type") == metric_type
    ]
    return format_decrease_summary(
        filtered_items,
        title=title,
        record_description=f"{metric_label}减少",
        notice=_METRIC_DECREASE_NOTICE,
        source_hint=source_hint,
    )


async def _send_decrease_summary_messages(
    summary: Optional[str],
    *,
    log_label: str,
    item_count: int,
) -> None:
    from app.core.telegram_utils import split_long_message

    if not summary:
        return
    try:
        for part in split_long_message(summary):
            await send_telegram_notify_async(settings.TELEGRAM_ADMIN, part)
        logger.warning("%s已发送（提交成功后）: %d 条", log_label, item_count)
    except Exception as notify_err:
        logger.warning("发送%s失败: %s", log_label, notify_err)


async def send_pending_data_decrease_warnings(
    *,
    traffic_decreases: Optional[list[Dict[str, Any]]] = None,
    metric_decreases: Optional[list[Dict[str, Any]]] = None,
) -> None:
    """事务提交成功后发送数据减少告警。

    - eCPM/收益：按减扣前/后各汇总一条（过长则连续拆分）
    - 请求/匹配/展示/点击：汇总为一条（过长则连续拆分）
    """
    metric_items = metric_decreases or []
    for metric_type, _, metric_label in METRIC_DECREASE_CATEGORIES:
        category_items = [
            item for item in metric_items if item.get("metric_type") == metric_type
        ]
        summary = format_metric_decrease_summary(
            metric_items,
            metric_type=metric_type,
        )
        await _send_decrease_summary_messages(
            summary,
            log_label=f"{metric_label}减少汇总",
            item_count=len(category_items),
        )

    traffic_items = traffic_decreases or []
    traffic_summary = format_traffic_decrease_summary(traffic_items)
    await _send_decrease_summary_messages(
        traffic_summary,
        log_label="流量指标减少汇总",
        item_count=len(traffic_items),
    )

async def process_api_ad_data(
        data: List[Dict[str, Any]],
        db: AsyncSession,
        admin_user: User,
        source: str = "API",
        field_mapping: Optional[Dict[str, str]] = None,
        *,
        data_source: str = DATA_SOURCE_UNKNOWN,
        report_type: str = REPORT_TYPE_LEGACY,
        upstream_account: str = "",
) -> Dict[str, int]:
    """
    标准化的API广告数据处理函数
    
    功能说明：
    1. 先按照日期、产品、国家对API返回的数据进行分组累加
    2. 累加后按照日期、产品、国家检查是否有重复数据
    3. 识别不出来国家代码的数据，保留原始国家代码写入（无国家输入时使用 ZZ）
    4. 根据产品的减扣比例自动计算减扣后的eCPM和收益
    5. 如果数据已存在，会检查是否需要更新
    
    参数:
        data: API返回的数据列表，每条数据应包含以下字段（字段名通过field_mapping映射）：
            - date: 日期字符串 (YYYY-MM-DD格式)
            - product_name: 产品名称（通过field_mapping映射到API字段名，如"url"）
            - request_count: 请求次数 (通过field_mapping映射，如映射到"requests"，可选，默认0)
            - match_count: 匹配请求 (通过field_mapping映射，如映射到"matche_que"，可选，默认0)
            - display_count: 广告展示次数 (通过field_mapping映射，如映射到"adimpressions"，可选，默认0)
            - click_count: 点击数 (通过field_mapping映射，如映射到"clicks"，可选，默认0)
            - revenue_before_deduct: 预计收入 (通过field_mapping映射，如映射到"estirevenue"，可选，默认0)
            - ecpm_before_deduct: eCPM值 (通过field_mapping映射，如映射到"ecpm"，可选，会自动计算)
            - country_code: 国家代码（支持多种格式，如果无法识别则累加处理）
        db: 数据库会话
        admin_user: 管理员用户对象（用于产品查找/创建）
        source: 数据来源标识（用于日志记录，默认"API"）
        field_mapping: 字段映射字典，键为标准字段名，值为API返回的字段名
        data_source: 入库字段，上游系统标识（zhisuo/gam/excel 等）
        report_type: 入库字段（保留参数兼容；实际按 ad_unit/country 行形态自动推断）
        upstream_account: 入库字段，上游账号（如 KE11）
    
    返回:
        Dict[str, int]: 处理结果统计
            - inserted_count: 成功插入的数据条数
            - updated_count: 成功更新的数据条数
            - skipped_count: 跳过重复的数据条数
            - zero_skipped_count: 跳过全零指标的数据条数
            - error_count: 处理出错的数据条数
    """

    resolved_data_source = str(data_source or DATA_SOURCE_UNKNOWN).strip() or DATA_SOURCE_UNKNOWN
    resolved_report_type = normalize_report_type(report_type)
    resolved_upstream_account = str(upstream_account or "").strip()

    # 字段映射函数
    def get_field(item: Dict[str, Any], field_name: str, default: Any = None) -> Any:
        """从数据项中获取字段值（严格按照传入的字段映射）"""
        if field_mapping and field_name in field_mapping:
            mapped_field = field_mapping[field_name]
        else:
            mapped_field = field_name
        return item.get(mapped_field, default)

    # 导入build_product_maps和find_or_create_product函数
    from app.api_v1.excel.import_handler import build_product_maps, find_or_create_product
    from app.core.product_assignment import find_ad_data_assignment_gaps

    # ========== 构建产品映射（与Excel导入逻辑一致） ==========
    product_map, product_name_map = await build_product_maps(db)
    logger.debug(f"已构建产品映射: {len(product_map)} 个产品")

    # 初始化统计计数器
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    zero_skipped_count = 0
    error_count = 0
    report_type_counts: dict[str, int] = defaultdict(int)
    import_date_min: Optional[date] = None
    import_date_max: Optional[date] = None
    # 本次成功 insert/update 的产品 ID（skip / error 不计入，用于分配空窗检查范围）
    written_product_ids: Set[int] = set()
    pending_traffic_decreases: list[Dict[str, Any]] = []
    pending_metric_decreases: list[Dict[str, Any]] = []

    # ========== 第一步：预处理所有数据，识别国家代码并分组 ==========
    # 存储能识别国家代码的数据：按 (date_str, product_name, country_code) 分组累加
    # key = (date_str, product_name, country_code), value = 累加的数据
    recognized_data: Dict[tuple, Dict[str, Any]] = {}

    # 存储无法识别国家代码的数据：key = (date_str, product_name), value = 累加的数据
    unrecognized_data: Dict[tuple, Dict[str, Any]] = {}
    
    # 存储无法识别的国家代码信息（用于发送Telegram通知，去重）
    # key = (date_str, product_name, country_input), value = 是否已发送通知
    unrecognized_country_notifications: Dict[tuple, bool] = {}

    # 遍历API返回的每条数据，进行预处理和分组
    for item in data:
        try:
            # 提取和验证基础字段
            item_date_str = get_field(item, "date", "")
            item_product_name = get_field(item, "product_name", "")

            # 验证日期
            if not item_date_str or not item_date_str.strip():
                logger.warning(f"日期为空，跳过该条数据")
                error_count += 1
                continue

            # 解析日期，支持多种格式：'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM:SS'
            item_date_str_clean = item_date_str.strip()
            item_date = None
            try:
                # 先尝试解析完整格式（日期+时间）
                try:
                    item_date = datetime.strptime(item_date_str_clean, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    # 如果失败，尝试只解析日期部分
                    try:
                        item_date = datetime.strptime(item_date_str_clean, '%Y-%m-%d')
                    except ValueError:
                        # 如果还是失败，尝试提取日期部分（处理可能的前后空格或格式问题）
                        date_part = item_date_str_clean.split()[0] if ' ' in item_date_str_clean else item_date_str_clean
                        item_date = datetime.strptime(date_part, '%Y-%m-%d')
                # 统一设置为当天的0点0分0秒
                item_date = item_date.replace(hour=0, minute=0, second=0, microsecond=0)
                # 分组 key 使用规范化日期，避免同一天不同字符串拆成两组触发唯一键冲突
                item_date_str = item_date.date().isoformat()
            except (ValueError, TypeError) as e:
                logger.warning(f"日期格式错误: {item_date_str}, 错误: {str(e)}, 跳过该条数据")
                error_count += 1
                continue

            data_day = item_date.date()
            if import_date_min is None or data_day < import_date_min:
                import_date_min = data_day
            if import_date_max is None or data_day > import_date_max:
                import_date_max = data_day

            # 验证产品名称
            if not item_product_name or not item_product_name.strip():
                logger.warning(f"产品名称为空，跳过该条数据")
                error_count += 1
                continue

            item_product_name = item_product_name.strip()
            item_ad_unit = normalize_ad_unit(get_field(item, "ad_unit", ""))

            # 解析数值字段
            try:
                # 请求数
                item_request_count = int(get_field(item, "request_count", 0) or 0)

                # 匹配数
                item_match_count = int(get_field(item, "match_count", 0) or 0)

                # 展示数
                item_display_count = int(get_field(item, "display_count", 0) or 0)

                # 点击数
                item_click_count = int(get_field(item, "click_count", 0) or 0)

                # 收益
                item_revenue = float(get_field(item, "revenue_before_deduct", 0) or 0)

                # CPC（如果字段映射存在则解析，否则使用默认值0.0）
                item_cpc = 0.0
                if field_mapping and "cpc" in field_mapping:
                    cpc_val = get_field(item, "cpc")
                    if cpc_val is not None and cpc_val != "":
                        try:
                            item_cpc = float(cpc_val)
                        except (ValueError, TypeError):
                            item_cpc = 0.0

                # 可见率（如果字段映射存在则解析，否则使用默认值0.0）
                item_viewability_rate = 0.0
                if field_mapping and "viewability_rate" in field_mapping:
                    viewability_rate_val = get_field(item, "viewability_rate")
                    if viewability_rate_val is not None and viewability_rate_val != "":
                        try:
                            item_viewability_rate = float(viewability_rate_val)
                        except (ValueError, TypeError):
                            item_viewability_rate = 0.0

                # PageViews（如果字段映射存在则解析，否则使用默认值0）
                item_pageviews = 0
                if field_mapping and "pageviews" in field_mapping:
                    pageviews_val = get_field(item, "pageviews")
                    if pageviews_val is not None and pageviews_val != "":
                        try:
                            item_pageviews = int(pageviews_val)
                        except (ValueError, TypeError):
                            item_pageviews = 0
            except (ValueError, TypeError) as e:
                logger.warning(f"数值字段格式错误: {str(e)}, 跳过该条数据")
                error_count += 1
                continue

            # eCPM（用于全零判断；无展示时由收益推算或为 0）
            item_ecpm_val = get_field(item, "ecpm_before_deduct")
            if item_ecpm_val is not None and item_ecpm_val != "":
                try:
                    item_ecpm = float(item_ecpm_val)
                except (ValueError, TypeError):
                    item_ecpm = (item_revenue / item_display_count * 1000) if item_display_count > 0 else 0.0
            else:
                item_ecpm = (item_revenue / item_display_count * 1000) if item_display_count > 0 else 0.0

            if is_empty_ad_metrics(
                request_count=item_request_count,
                match_count=item_match_count,
                display_count=item_display_count,
                click_count=item_click_count,
                revenue=item_revenue,
                pageviews=item_pageviews,
                viewability_rate=item_viewability_rate,
                cpc=item_cpc,
                ecpm=item_ecpm,
            ):
                zero_skipped_count += 1
                logger.debug(
                    "跳过全零指标行: date=%s product=%s",
                    item_date_str,
                    item_product_name,
                )
                continue

            # 计算eCPM（后续分组累加沿用已算好的 item_ecpm）

            # 尝试识别国家代码
            item_country_input = get_field(item, "country_code", None)
            item_country_code = None
            has_country_input = False  # 标记是否提供了国家代码输入

            if item_country_input and isinstance(item_country_input, str):
                item_country_input = item_country_input.strip()
                if item_country_input:
                    has_country_input = True  # 有提供国家代码输入
                    found_country_code = await find_country_code_by_any_format(db, item_country_input)
                    if found_country_code:
                        item_country_code = found_country_code

            # 根据是否能识别国家代码，分组数据
            if item_country_code:
                # 能识别国家代码（正常情况），按 (date_str, product_name, country_code, ad_unit) 分组累加
                key = (item_date_str, item_product_name, item_country_code, item_ad_unit)
                if key not in recognized_data:
                    recognized_data[key] = {
                        "date_str": item_date_str,
                        "date": item_date,
                        "product_name": item_product_name,
                        "country_code": item_country_code,
                        "ad_unit": item_ad_unit,
                        "request_count": 0,
                        "match_count": 0,
                        "display_count": 0,
                        "click_count": 0,
                        "cpc": 0.0,
                        "pageviews": 0,
                        "revenue": 0.0,
                        "ecpm": 0.0,
                        "items": []  # 存储原始数据项，用于后续计算eCPM
                    }
                # 累加数据
                # 请求数
                recognized_data[key]["request_count"] += item_request_count

                # 匹配数
                recognized_data[key]["match_count"] += item_match_count

                # 展示数
                recognized_data[key]["display_count"] += item_display_count

                # 点击数
                recognized_data[key]["click_count"] += item_click_count

                # CPC：如果有字段映射，保存到items中用于后续计算；如果没有字段映射，将在分组后根据公式计算
                # 不累加，保存单个值到items中

                # PageViews（如果字段映射存在则累加）
                if field_mapping and "pageviews" in field_mapping:
                    recognized_data[key]["pageviews"] += item_pageviews

                # 收益
                recognized_data[key]["revenue"] += item_revenue
                # 保存原始数据项，包括CPC（如果有字段映射）
                item_data = {
                    "revenue": item_revenue,
                    "display_count": item_display_count,
                    "ecpm": item_ecpm,
                    "click_count": item_click_count
                }
                # 如果有字段映射且有CPC值，保存到items中
                if field_mapping and "cpc" in field_mapping and item_cpc > 0:
                    item_data["cpc"] = item_cpc
                # 如果有字段映射且有可见率值，保存到items中
                if field_mapping and "viewability_rate" in field_mapping and item_viewability_rate > 0:
                    item_data["viewability_rate"] = item_viewability_rate
                recognized_data[key]["items"].append(item_data)
            else:
                # 有国家输入但无法识别：保留原始代码分组；无输入：country_code 入库为 NULL
                if has_country_input:
                    storage_code = preserve_unrecognized_country_code(item_country_input)
                    key = (item_date_str, item_product_name, item_ad_unit, storage_code)
                else:
                    key = (item_date_str, item_product_name, item_ad_unit)
                if key not in unrecognized_data:
                    unrecognized_data[key] = {
                        "date_str": item_date_str,
                        "date": item_date,
                        "product_name": item_product_name,
                        "ad_unit": item_ad_unit,
                        "request_count": 0,
                        "match_count": 0,
                        "display_count": 0,
                        "click_count": 0,
                        "viewability_rate": 0.0,
                        "cpc": 0.0,
                        "pageviews": 0,
                        "revenue": 0.0,
                        "ecpm": 0.0,
                        "items": []  # 存储原始数据项，用于后续计算
                    }
                # 累加数据
                # 请求数
                unrecognized_data[key]["request_count"] += item_request_count

                # 匹配数
                unrecognized_data[key]["match_count"] += item_match_count

                # 展示数
                unrecognized_data[key]["display_count"] += item_display_count

                # 点击数
                unrecognized_data[key]["click_count"] += item_click_count

                # CPC：如果有字段映射，保存到items中用于后续计算；如果没有字段映射，将在分组后根据公式计算
                # 不累加，保存单个值到items中

                # PageViews（如果字段映射存在则累加）
                if field_mapping and "pageviews" in field_mapping:
                    unrecognized_data[key]["pageviews"] += item_pageviews

                # 收益
                unrecognized_data[key]["revenue"] += item_revenue
                # 保存原始数据项，包括CPC（如果有字段映射）
                item_data = {
                    "revenue": item_revenue,
                    "display_count": item_display_count,
                    "ecpm": item_ecpm,
                    "click_count": item_click_count
                }
                # 如果有字段映射且有CPC值，保存到items中
                if field_mapping and "cpc" in field_mapping and item_cpc > 0:
                    item_data["cpc"] = item_cpc
                # 如果有字段映射且有可见率值，保存到items中
                if field_mapping and "viewability_rate" in field_mapping and item_viewability_rate > 0:
                    item_data["viewability_rate"] = item_viewability_rate
                unrecognized_data[key]["items"].append(item_data)

                # 只有当提供了国家代码输入但无法识别时，才发送Telegram通知
                # 如果没有提供国家代码输入，这是正常的（可能数据源就没有提供），不需要通知
                if has_country_input:
                    # 记录无法识别国家代码的警告
                    str_war = f"无法识别国家代码: [{item_country_input}], 日期={item_date_str}, 产品={item_product_name}"
                    logger.warning(str_war)
                    
                    # 发送Telegram通知（去重，避免重复发送相同的信息）
                    notification_key = (item_date_str, item_product_name, item_country_input)
                    if notification_key not in unrecognized_country_notifications:
                        unrecognized_country_notifications[notification_key] = True
                        try:
                            telegram_msg = f"⚠️ 无法识别国家代码警告\n\n"
                            telegram_msg += f"数据来源: {source}\n"
                            telegram_msg += f"日期: {item_date_str}\n"
                            telegram_msg += f"产品: {item_product_name}\n"
                            telegram_msg += f"国家代码输入: [{item_country_input}]\n\n"
                            telegram_msg += f"说明：提供了国家代码但无法识别，将保留原始值「{preserve_unrecognized_country_code(item_country_input)}」写入"
                            
                            # 发送通知（异步，不阻塞）
                            try:
                                await send_telegram_notify_async(settings.TELEGRAM_ADMIN, telegram_msg)
                                logger.info(f"无法识别国家代码警告已发送: 日期={item_date_str}, 产品={item_product_name}, 国家代码输入=[{item_country_input}]")
                            except Exception as notify_err:
                                logger.warning(f"发送无法识别国家代码警告失败: {notify_err}")
                        except Exception as e:
                            # 通知失败不应该影响数据处理流程
                            logger.warning(f"发送无法识别国家代码通知时出错: {e}")

        except Exception as e:
            logger.error(f"预处理数据时出错: {str(e)}", exc_info=True)
            error_count += 1
            continue

    # 记录预处理结果统计
    total_original_items = len(data)
    total_grouped_items = len(recognized_data) + len(unrecognized_data)
    if total_original_items > 0:
        logger.info(
            f"数据预处理完成: 原始数据 {total_original_items} 条, "
            f"合并后 {total_grouped_items} 条 "
            f"(能识别国家: {len(recognized_data)}, 无法识别国家: {len(unrecognized_data)}), "
            f"跳过全零 {zero_skipped_count} 条"
        )

    # ========== 第二步：处理能识别国家代码的数据（按日期、产品、国家检查重复，累加后处理） ==========
    for key, grouped_data in recognized_data.items():
        if _grouped_data_is_empty(grouped_data):
            continue
        pending_write: Optional[str] = None  # "insert" | "update"
        pending_product_id: Optional[int] = None
        pending_report_type: Optional[str] = None
        pending_decrease_result: Optional[Dict[str, Any]] = None
        async with db.begin_nested() as savepoint:
            try:
                date_str = grouped_data["date_str"]
                product_name = grouped_data["product_name"]
                country_code = grouped_data["country_code"]
                ad_unit = grouped_data.get("ad_unit", "")
                item_date = grouped_data["date"]

                # 查找或创建产品
                product_info = await find_or_create_product(
                    product_name=product_name,
                    target_client_id=None,
                    client_id=None,
                    mapping_complete=True,
                    product_map=product_map,
                    product_name_map=product_name_map,
                    db=db,
                    current_user=admin_user,
                )

                product_id = product_info["product_id"]
                ecpm_deduct_ratio = product_info.get("ecpm_deduct_ratio", 0.0)
                revenue_deduct_ratio = product_info.get("revenue_deduct_ratio", 0.0)

                # 计算累加后的eCPM（加权平均）
                total_revenue = grouped_data["revenue"]
                total_display = grouped_data["display_count"]
                total_clicks = grouped_data["click_count"]
                if total_display > 0:
                    calculated_ecpm = (total_revenue / total_display * 1000)
                else:
                    calculated_ecpm = 0.0

                final_ecpm = calculated_ecpm

                # 计算CPC：按照日期、产品、国家分组
                # 如果分组内只有单一条数据：有字段映射用映射字段，没有字段映射用公式算
                # 如果分组内有多条相同数据：累加后用算法计算
                items_list = grouped_data.get("items", [])
                items_count = len(items_list)
                
                calculated_cpc = 0.0
                if items_count == 1:
                    # 单一条数据
                    single_item = items_list[0]
                    if field_mapping and "cpc" in field_mapping and "cpc" in single_item:
                        # 有字段映射，直接用映射字段的CPC值
                        calculated_cpc = single_item.get("cpc", 0.0)
                    else:
                        # 没有字段映射，用公式计算：CPC = 收益 / 点击数
                        item_clicks = single_item.get("click_count", 0)
                        item_revenue = single_item.get("revenue", 0.0)
                        if item_clicks > 0:
                            calculated_cpc = item_revenue / item_clicks
                else:
                    # 多条相同数据，累加后用算法计算
                    if field_mapping and "cpc" in field_mapping:
                        # 有字段映射，检查items中是否有CPC值
                        has_cpc_values = False
                        total_cpc_weighted = 0.0
                        total_weight = 0
                        for item in items_list:
                            if "cpc" in item and item.get("cpc", 0) > 0:
                                has_cpc_values = True
                                item_clicks = item.get("click_count", 0)
                                if item_clicks > 0:
                                    total_cpc_weighted += item["cpc"] * item_clicks
                                    total_weight += item_clicks
                        if has_cpc_values and total_weight > 0:
                            # 有CPC值，使用加权平均（基于点击数）
                            calculated_cpc = total_cpc_weighted / total_weight
                        else:
                            # 有字段映射但没有CPC值，使用累加后的数据计算：CPC = 累加后的收益 / 累加后的点击数
                            if total_clicks > 0:
                                calculated_cpc = total_revenue / total_clicks
                    else:
                        # 没有字段映射，使用累加后的数据计算：CPC = 累加后的收益 / 累加后的点击数
                        if total_clicks > 0:
                            calculated_cpc = total_revenue / total_clicks
                # 更新分组数据中的CPC值
                grouped_data["cpc"] = calculated_cpc

                # 计算可见率：如果有字段映射且有可见率值，使用加权平均（基于点击数）；否则使用默认值0.0
                calculated_viewability_rate = 0.0
                if field_mapping and "viewability_rate" in field_mapping:
                    if items_count == 1:
                        # 单一条数据
                        single_item = items_list[0]
                        if "viewability_rate" in single_item:
                            calculated_viewability_rate = single_item.get("viewability_rate", 0.0)
                    else:
                        # 多条相同数据，使用加权平均（基于点击数）
                        has_viewability_values = False
                        total_viewability_weighted = 0.0
                        total_weight = 0
                        for item in items_list:
                            if "viewability_rate" in item and item.get("viewability_rate", 0) > 0:
                                has_viewability_values = True
                                item_clicks = item.get("click_count", 0)
                                if item_clicks > 0:
                                    total_viewability_weighted += item["viewability_rate"] * item_clicks
                                    total_weight += item_clicks
                        if has_viewability_values and total_weight > 0:
                            calculated_viewability_rate = total_viewability_weighted / total_weight
                # 更新分组数据中的可见率值
                grouped_data["viewability_rate"] = calculated_viewability_rate

                # 计算减扣后的值：无扣减保留原始精度，有扣减截断两位小数
                ecpm_after_deduct = apply_deduct_ratio(final_ecpm, ecpm_deduct_ratio)
                revenue_after_deduct = apply_deduct_ratio(total_revenue, revenue_deduct_ratio)

                # 检查数据是否重复（按日期、产品、国家、广告单元）
                row_report_type = resolve_report_type_for_row(
                    resolved_report_type,
                    ad_unit=ad_unit,
                    country_code=country_code,
                )
                existing_data = await _find_existing_ad_data_for_import(
                    db,
                    product_id=product_id,
                    ad_date=item_date,
                    country_code=country_code,
                    ad_unit=ad_unit,
                    data_source=resolved_data_source,
                    row_report_type=row_report_type,
                    upstream_account=resolved_upstream_account,
                )

                # 处理数据（新建或更新）
                if existing_data:
                    pending_decrease_result = await build_data_decrease_warning(
                        existing_data=existing_data,
                        new_request_count=grouped_data["request_count"],
                        new_match_count=grouped_data["match_count"],
                        new_display_count=grouped_data["display_count"],
                        new_click_count=grouped_data["click_count"],
                        new_revenue_before=total_revenue,
                        new_revenue_after=revenue_after_deduct,
                        new_ecpm_before=final_ecpm,
                        new_ecpm_after=ecpm_after_deduct,
                        date_str=date_str,
                        product_name=product_name,
                        country_code=country_code,
                        source=source,
                        db=db,
                    )

                    # 检查是否需要更新
                    need_update = False
                    update_fields = []

                    if existing_data.report_type != row_report_type:
                        need_update = True
                        update_fields.append(
                            f"报表类型: {existing_data.report_type} -> {row_report_type}"
                        )
                        existing_data.report_type = row_report_type

                    if existing_data.request_count != grouped_data["request_count"]:
                        need_update = True
                        update_fields.append(f"请求数: {existing_data.request_count} -> {grouped_data['request_count']}")
                        existing_data.request_count = grouped_data["request_count"]

                    if existing_data.match_count != grouped_data["match_count"]:
                        need_update = True
                        update_fields.append(f"匹配数: {existing_data.match_count} -> {grouped_data['match_count']}")
                        existing_data.match_count = grouped_data["match_count"]

                    if existing_data.display_count != grouped_data["display_count"]:
                        need_update = True
                        update_fields.append(f"展示数: {existing_data.display_count} -> {grouped_data['display_count']}")
                        existing_data.display_count = grouped_data["display_count"]

                    if existing_data.click_count != grouped_data["click_count"]:
                        need_update = True
                        update_fields.append(f"点击数: {existing_data.click_count} -> {grouped_data['click_count']}")
                        existing_data.click_count = grouped_data["click_count"]

                    # CPC（有字段映射则使用加权平均，否则使用公式计算：CPC = 收益 / 点击数）
                    grouped_cpc = grouped_data.get("cpc", 0.0)
                    if _metric_differs(existing_data.cpc, grouped_cpc):
                        need_update = True
                        update_fields.append(
                            f"CPC: {_as_float(existing_data.cpc):.2f} -> {_as_float(grouped_cpc):.2f}"
                        )
                        existing_data.cpc = grouped_cpc

                    # 可见率（如果有字段映射则更新）
                    grouped_viewability_rate = grouped_data.get("viewability_rate", 0.0)
                    if _metric_differs(existing_data.viewability_rate, grouped_viewability_rate):
                        need_update = True
                        update_fields.append(
                            f"可见率: {_as_float(existing_data.viewability_rate):.2f} -> {_as_float(grouped_viewability_rate):.2f}"
                        )
                        existing_data.viewability_rate = grouped_viewability_rate

                    # PageViews（如果字段映射存在则更新）
                    if field_mapping and "pageviews" in field_mapping:
                        grouped_pageviews = grouped_data.get("pageviews", 0)
                        if existing_data.pageviews != grouped_pageviews:
                            need_update = True
                            update_fields.append(f"PageViews: {existing_data.pageviews} -> {grouped_pageviews}")
                            existing_data.pageviews = grouped_pageviews

                    # 如果基础数据有变化，重新计算比率字段
                    if need_update:
                        existing_data.finalize_metrics()

                    if _metric_differs(existing_data.ecpm_before_deduct, final_ecpm):
                        need_update = True
                        update_fields.append(
                            f"eCPM(减扣前): {_as_float(existing_data.ecpm_before_deduct):.2f} -> {_as_float(final_ecpm):.2f}")
                        existing_data.ecpm_before_deduct = final_ecpm

                    if _metric_differs(existing_data.revenue_before_deduct, total_revenue):
                        need_update = True
                        update_fields.append(
                            f"收益(减扣前): {_as_float(existing_data.revenue_before_deduct):.2f} -> {_as_float(total_revenue):.2f}")
                        existing_data.revenue_before_deduct = total_revenue

                    if _metric_differs(existing_data.ecpm_after_deduct, ecpm_after_deduct):
                        need_update = True
                        update_fields.append(
                            f"eCPM(减扣后): {_as_float(existing_data.ecpm_after_deduct):.2f} -> {_as_float(ecpm_after_deduct):.2f}")
                        existing_data.ecpm_after_deduct = ecpm_after_deduct

                    if _metric_differs(existing_data.revenue_after_deduct, revenue_after_deduct):
                        need_update = True
                        update_fields.append(
                            f"收益(减扣后): {_as_float(existing_data.revenue_after_deduct):.2f} -> {_as_float(revenue_after_deduct):.2f}")
                        existing_data.revenue_after_deduct = revenue_after_deduct

                    if need_update:
                        pending_write = "update"
                        pending_product_id = product_id
                        pending_report_type = row_report_type
                        logger.info(
                            f"更新广告数据: 日期={date_str}, 产品={product_name}, 国家={country_code}, "
                            f"变化字段: {', '.join(update_fields)}"
                        )

                    else:
                        skipped_count += 1
                        pending_decrease_result = None
                        logger.info(f"数据完全相同，跳过: 日期={date_str}, 产品={product_name}, 国家={country_code}")
                else:
                    # 创建新记录
                    ad_data_date = normalize_date_for_ad_data(item_date)

                    new_ad_data = AdData(
                        date=ad_data_date,
                        product_id=product_id,
                        ad_unit=ad_unit,
                        country_code=country_code,
                        data_source=resolved_data_source,
                        upstream_account=resolved_upstream_account,
                        report_type=row_report_type,
                        request_count=grouped_data["request_count"],
                        match_count=grouped_data["match_count"],
                        display_count=grouped_data["display_count"],
                        click_count=grouped_data["click_count"],
                        viewability_rate=grouped_data.get("viewability_rate", 0.0),  # 可见率：有字段映射则使用加权平均，否则使用默认值0.0
                        cpc=grouped_data.get("cpc", 0.0),  # CPC：有字段映射则使用加权平均，否则使用公式计算（收益/点击数）
                        pageviews=grouped_data.get("pageviews", 0) if (field_mapping and "pageviews" in field_mapping) else 0,
                        ecpm_before_deduct=final_ecpm,
                        ecpm_after_deduct=ecpm_after_deduct,
                        revenue_before_deduct=total_revenue,
                        revenue_after_deduct=revenue_after_deduct
                    )
                    # 计算并设置比率字段
                    new_ad_data.finalize_metrics()

                    db.add(new_ad_data)
                    await db.flush()
                    await db.refresh(new_ad_data)
                    pending_write = "insert"
                    pending_product_id = product_id
                    pending_report_type = row_report_type

                    logger.info(
                        f"添加广告数据: 日期={date_str}, 产品={product_name}, 国家={country_code}, "
                        f"请求数={grouped_data['request_count']}, 匹配数={grouped_data['match_count']}, "
                        f"展示数={grouped_data['display_count']}, 点击数={grouped_data['click_count']}, "
                        f"eCPM={final_ecpm:.2f}->{ecpm_after_deduct:.2f}, "
                        f"收益={total_revenue:.2f}->{revenue_after_deduct:.2f}"
                    )


            except Exception as e:
                await savepoint.rollback()
                pending_write = None
                pending_product_id = None
                pending_report_type = None
                pending_decrease_result = None
                error_msg = str(e)
                if "IntegrityError" in str(type(e)) or "Duplicate entry" in error_msg or "uq_ad_data" in error_msg:
                    logger.warning(
                        f"数据重复冲突（唯一性约束）: 日期={date_str if 'date_str' in locals() else '未知'}, "
                        f"产品={product_name if 'product_name' in locals() else '未知'}, "
                        f"国家代码={country_code if 'country_code' in locals() else '未知'}, "
                        f"错误: {error_msg[:200]}"
                    )
                else:
                    logger.error(f"处理能识别国家代码的数据时出错: {error_msg}", exc_info=True)
                error_count += 1

        if pending_write == "insert" and pending_product_id is not None:
            inserted_count += 1
            written_product_ids.add(pending_product_id)
            if pending_report_type:
                report_type_counts[pending_report_type] += 1
        elif pending_write == "update" and pending_product_id is not None:
            updated_count += 1
            written_product_ids.add(pending_product_id)
            if pending_report_type:
                report_type_counts[pending_report_type] += 1
            if pending_decrease_result:
                _append_decrease_result(
                    pending_decrease_result,
                    pending_traffic_decreases=pending_traffic_decreases,
                    pending_metric_decreases=pending_metric_decreases,
                )

    # ========== 第三步：处理无国家输入（NULL）或无法识别（保留原始代码）的累加数据 ==========
    for key, grouped_data in unrecognized_data.items():
        if _grouped_data_is_empty(grouped_data):
            continue
        pending_write: Optional[str] = None
        pending_product_id: Optional[int] = None
        pending_report_type: Optional[str] = None
        pending_decrease_result: Optional[Dict[str, Any]] = None
        async with db.begin_nested() as savepoint:
            try:
                if len(key) == 4:
                    date_str, product_name, ad_unit, country_code = key
                else:
                    date_str, product_name, ad_unit = key
                    country_code = None

                # 查找或创建产品
                product_info = await find_or_create_product(
                    product_name=product_name,
                    target_client_id=None,
                    client_id=None,
                    mapping_complete=True,
                    product_map=product_map,
                    product_name_map=product_name_map,
                    db=db,
                    current_user=admin_user,
                )

                product_id = product_info["product_id"]
                ecpm_deduct_ratio = product_info.get("ecpm_deduct_ratio", 0.0)
                revenue_deduct_ratio = product_info.get("revenue_deduct_ratio", 0.0)

                # 计算累加后的eCPM（加权平均）
                total_revenue = grouped_data["revenue"]
                total_display = grouped_data["display_count"]
                total_clicks = grouped_data["click_count"]
                if total_display > 0:
                    calculated_ecpm = (total_revenue / total_display * 1000)
                else:
                    calculated_ecpm = 0.0

                final_ecpm = calculated_ecpm

                # 计算CPC：按照日期、产品、国家分组
                # 如果分组内只有单一条数据：有字段映射用映射字段，没有字段映射用公式算
                # 如果分组内有多条相同数据：累加后用算法计算
                items_list = grouped_data.get("items", [])
                items_count = len(items_list)
                
                calculated_cpc = 0.0
                if items_count == 1:
                    # 单一条数据
                    single_item = items_list[0]
                    if field_mapping and "cpc" in field_mapping and "cpc" in single_item:
                        # 有字段映射，直接用映射字段的CPC值
                        calculated_cpc = single_item.get("cpc", 0.0)
                    else:
                        # 没有字段映射，用公式计算：CPC = 收益 / 点击数
                        item_clicks = single_item.get("click_count", 0)
                        item_revenue = single_item.get("revenue", 0.0)
                        if item_clicks > 0:
                            calculated_cpc = item_revenue / item_clicks
                else:
                    # 多条相同数据，累加后用算法计算
                    if field_mapping and "cpc" in field_mapping:
                        # 有字段映射，检查items中是否有CPC值
                        has_cpc_values = False
                        total_cpc_weighted = 0.0
                        total_weight = 0
                        for item in items_list:
                            if "cpc" in item and item.get("cpc", 0) > 0:
                                has_cpc_values = True
                                item_clicks = item.get("click_count", 0)
                                if item_clicks > 0:
                                    total_cpc_weighted += item["cpc"] * item_clicks
                                    total_weight += item_clicks
                        if has_cpc_values and total_weight > 0:
                            # 有CPC值，使用加权平均（基于点击数）
                            calculated_cpc = total_cpc_weighted / total_weight
                        else:
                            # 有字段映射但没有CPC值，使用累加后的数据计算：CPC = 累加后的收益 / 累加后的点击数
                            if total_clicks > 0:
                                calculated_cpc = total_revenue / total_clicks
                    else:
                        # 没有字段映射，使用累加后的数据计算：CPC = 累加后的收益 / 累加后的点击数
                        if total_clicks > 0:
                            calculated_cpc = total_revenue / total_clicks
                # 更新分组数据中的CPC值
                grouped_data["cpc"] = calculated_cpc

                # 计算可见率：如果有字段映射且有可见率值，使用加权平均（基于点击数）；否则使用默认值0.0
                calculated_viewability_rate = 0.0
                if field_mapping and "viewability_rate" in field_mapping:
                    items_list = grouped_data.get("items", [])
                    items_count = len(items_list)
                    if items_count == 1:
                        # 单一条数据
                        single_item = items_list[0]
                        if "viewability_rate" in single_item:
                            calculated_viewability_rate = single_item.get("viewability_rate", 0.0)
                    else:
                        # 多条相同数据，使用加权平均（基于点击数）
                        has_viewability_values = False
                        total_viewability_weighted = 0.0
                        total_weight = 0
                        for item in items_list:
                            if "viewability_rate" in item and item.get("viewability_rate", 0) > 0:
                                has_viewability_values = True
                                item_clicks = item.get("click_count", 0)
                                if item_clicks > 0:
                                    total_viewability_weighted += item["viewability_rate"] * item_clicks
                                    total_weight += item_clicks
                        if has_viewability_values and total_weight > 0:
                            calculated_viewability_rate = total_viewability_weighted / total_weight
                # 更新分组数据中的可见率值
                grouped_data["viewability_rate"] = calculated_viewability_rate

                # 计算减扣后的值：无扣减保留原始精度，有扣减截断两位小数
                ecpm_after_deduct = apply_deduct_ratio(final_ecpm, ecpm_deduct_ratio)
                revenue_after_deduct = apply_deduct_ratio(total_revenue, revenue_deduct_ratio)

                # 检查数据是否重复（按日期、产品、国家代码、广告单元）
                item_date = grouped_data["date"]
                row_report_type = resolve_report_type_for_row(
                    resolved_report_type,
                    ad_unit=ad_unit,
                    country_code=country_code,
                )
                existing_data = await _find_existing_ad_data_for_import(
                    db,
                    product_id=product_id,
                    ad_date=item_date,
                    country_code=country_code,
                    ad_unit=ad_unit,
                    data_source=resolved_data_source,
                    row_report_type=row_report_type,
                    upstream_account=resolved_upstream_account,
                )

                # 处理数据（新建或更新）
                if existing_data:
                    pending_decrease_result = await build_data_decrease_warning(
                        existing_data=existing_data,
                        new_request_count=grouped_data["request_count"],
                        new_match_count=grouped_data["match_count"],
                        new_display_count=grouped_data["display_count"],
                        new_click_count=grouped_data["click_count"],
                        new_revenue_before=total_revenue,
                        new_revenue_after=revenue_after_deduct,
                        new_ecpm_before=final_ecpm,
                        new_ecpm_after=ecpm_after_deduct,
                        date_str=date_str,
                        product_name=product_name,
                        country_code=country_code,
                        source=f"{source}（无国家或无法识别，已累加）",
                        db=db,
                    )

                    # 检查是否需要更新
                    need_update = False
                    update_fields = []

                    if existing_data.report_type != row_report_type:
                        need_update = True
                        update_fields.append(
                            f"报表类型: {existing_data.report_type} -> {row_report_type}"
                        )
                        existing_data.report_type = row_report_type

                    if existing_data.country_code != country_code:
                        old_country = existing_data.country_code
                        existing_data.country_code = country_code
                        need_update = True
                        update_fields.append(
                            f"国家: {old_country or 'NULL'} -> {country_code or 'NULL'}"
                        )

                    if existing_data.request_count != grouped_data["request_count"]:
                        need_update = True
                        update_fields.append(
                            f"请求数: {existing_data.request_count} -> {grouped_data['request_count']}")
                        existing_data.request_count = grouped_data["request_count"]

                    if existing_data.match_count != grouped_data["match_count"]:
                        need_update = True
                        update_fields.append(f"匹配数: {existing_data.match_count} -> {grouped_data['match_count']}")
                        existing_data.match_count = grouped_data["match_count"]

                    if existing_data.display_count != grouped_data["display_count"]:
                        need_update = True
                        update_fields.append(
                            f"展示数: {existing_data.display_count} -> {grouped_data['display_count']}")
                        existing_data.display_count = grouped_data["display_count"]

                    if existing_data.click_count != grouped_data["click_count"]:
                        need_update = True
                        update_fields.append(f"点击数: {existing_data.click_count} -> {grouped_data['click_count']}")
                        existing_data.click_count = grouped_data["click_count"]

                    # CPC（有字段映射则使用加权平均，否则使用公式计算：CPC = 收益 / 点击数）
                    grouped_cpc = grouped_data.get("cpc", 0.0)
                    if _metric_differs(existing_data.cpc, grouped_cpc):
                        need_update = True
                        update_fields.append(
                            f"CPC: {_as_float(existing_data.cpc):.2f} -> {_as_float(grouped_cpc):.2f}"
                        )
                        existing_data.cpc = grouped_cpc

                    # PageViews（如果字段映射存在则更新）
                    if field_mapping and "pageviews" in field_mapping:
                        grouped_pageviews = grouped_data.get("pageviews", 0)
                        if existing_data.pageviews != grouped_pageviews:
                            need_update = True
                            update_fields.append(f"PageViews: {existing_data.pageviews} -> {grouped_pageviews}")
                            existing_data.pageviews = grouped_pageviews

                    # 如果基础数据有变化，重新计算比率字段
                    if need_update:
                        existing_data.finalize_metrics()

                    if _metric_differs(existing_data.ecpm_before_deduct, final_ecpm):
                        need_update = True
                        update_fields.append(
                            f"eCPM(减扣前): {_as_float(existing_data.ecpm_before_deduct):.2f} -> {_as_float(final_ecpm):.2f}")
                        existing_data.ecpm_before_deduct = final_ecpm

                    if _metric_differs(existing_data.revenue_before_deduct, total_revenue):
                        need_update = True
                        update_fields.append(
                            f"收益(减扣前): {_as_float(existing_data.revenue_before_deduct):.2f} -> {_as_float(total_revenue):.2f}")
                        existing_data.revenue_before_deduct = total_revenue

                    if _metric_differs(existing_data.ecpm_after_deduct, ecpm_after_deduct):
                        need_update = True
                        update_fields.append(
                            f"eCPM(减扣后): {_as_float(existing_data.ecpm_after_deduct):.2f} -> {_as_float(ecpm_after_deduct):.2f}")
                        existing_data.ecpm_after_deduct = ecpm_after_deduct

                    if _metric_differs(existing_data.revenue_after_deduct, revenue_after_deduct):
                        need_update = True
                        update_fields.append(
                            f"收益(减扣后): {_as_float(existing_data.revenue_after_deduct):.2f} -> {_as_float(revenue_after_deduct):.2f}")
                        existing_data.revenue_after_deduct = revenue_after_deduct

                    if need_update:
                        pending_write = "update"
                        pending_product_id = product_id
                        pending_report_type = row_report_type
                        logger.info(
                            f"更新广告数据（无国家或无法识别，已累加）: 日期={date_str}, 产品={product_name}, "
                            f"国家={country_code or 'NULL'}, 变化字段: {', '.join(update_fields)}"
                        )

                    else:
                        skipped_count += 1
                        pending_decrease_result = None
                        logger.info(
                            f"数据完全相同，跳过: 日期={date_str}, 产品={product_name}, "
                            f"国家={country_code or 'NULL'}"
                        )
                else:
                    # 创建新记录
                    ad_data_date = normalize_date_for_ad_data(item_date)

                    new_ad_data = AdData(
                        date=ad_data_date,
                        product_id=product_id,
                        ad_unit=ad_unit,
                        country_code=country_code,
                        data_source=resolved_data_source,
                        upstream_account=resolved_upstream_account,
                        report_type=row_report_type,
                        request_count=grouped_data["request_count"],
                        match_count=grouped_data["match_count"],
                        display_count=grouped_data["display_count"],
                        click_count=grouped_data["click_count"],
                        viewability_rate=grouped_data.get("viewability_rate", 0.0),  # 可见率：有字段映射则使用加权平均，否则使用默认值0.0
                        cpc=grouped_data.get("cpc", 0.0),  # CPC：有字段映射则使用加权平均，否则使用公式计算（收益/点击数）
                        pageviews=grouped_data.get("pageviews", 0) if (field_mapping and "pageviews" in field_mapping) else 0,
                        ecpm_before_deduct=final_ecpm,
                        ecpm_after_deduct=ecpm_after_deduct,
                        revenue_before_deduct=total_revenue,
                        revenue_after_deduct=revenue_after_deduct
                    )
                    # 计算并设置比率字段
                    new_ad_data.finalize_metrics()

                    db.add(new_ad_data)
                    await db.flush()
                    await db.refresh(new_ad_data)
                    pending_write = "insert"
                    pending_product_id = product_id
                    pending_report_type = row_report_type

                    logger.info(
                        f"添加广告数据（国家代码未识别，已保留原始值）: 日期={date_str}, 产品={product_name}, 国家={country_code}, "
                        f"请求数={grouped_data['request_count']}, 匹配数={grouped_data['match_count']}, "
                        f"展示数={grouped_data['display_count']}, 点击数={grouped_data['click_count']}, "
                        f"eCPM={final_ecpm:.2f}->{ecpm_after_deduct:.2f}, "
                        f"收益={total_revenue:.2f}->{revenue_after_deduct:.2f}"
                    )

            except Exception as e:
                await savepoint.rollback()
                pending_write = None
                pending_product_id = None
                pending_report_type = None
                pending_decrease_result = None
                error_msg = str(e)
                if "IntegrityError" in str(type(e)) or "Duplicate entry" in error_msg or "uq_ad_data" in error_msg:
                    logger.warning(
                        f"数据重复冲突（唯一性约束）: 日期={date_str if 'date_str' in locals() else '未知'}, "
                        f"产品={product_name if 'product_name' in locals() else '未知'}, "
                        f"国家代码={country_code if 'country_code' in locals() else '未知'}, 错误: {error_msg[:200]}"
                    )
                else:
                    logger.error(f"处理无法识别国家代码的数据时出错: {error_msg}", exc_info=True)
                error_count += 1

        if pending_write == "insert" and pending_product_id is not None:
            inserted_count += 1
            written_product_ids.add(pending_product_id)
            if pending_report_type:
                report_type_counts[pending_report_type] += 1
        elif pending_write == "update" and pending_product_id is not None:
            updated_count += 1
            written_product_ids.add(pending_product_id)
            if pending_report_type:
                report_type_counts[pending_report_type] += 1
            if pending_decrease_result:
                _append_decrease_result(
                    pending_decrease_result,
                    pending_traffic_decreases=pending_traffic_decreases,
                    pending_metric_decreases=pending_metric_decreases,
                )

    if inserted_count > 0 or updated_count > 0:
        try:
            await log_user_action(
                db=db,
                action_type="IMPORT",
                username="SYSTEM",
                resource_type="AD_DATA",
                resource_name=source,
                ip_address=source,
                success=True,
                details={
                    "inserted_count": inserted_count,
                    "updated_count": updated_count,
                    "skipped_count": skipped_count,
                    "zero_skipped_count": zero_skipped_count,
                    "error_count": error_count,
                    "source": f"{source}自动导入",
                },
            )
        except Exception as log_error:
            logger.warning(f"记录广告数据导入汇总审计失败: {log_error}")

    assignment_gaps: list[dict[str, Any]] = []
    assignment_orphan_total = 0
    if import_date_min and import_date_max and (inserted_count > 0 or updated_count > 0):
        assignment_gaps, assignment_orphan_total = await find_ad_data_assignment_gaps(
            db,
            start_date=import_date_min,
            end_date=import_date_max,
            product_ids=sorted(written_product_ids) if written_product_ids else None,
        )

    return {
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "zero_skipped_count": zero_skipped_count,
        "error_count": error_count,
        "report_type_counts": dict(report_type_counts),
        "assignment_gaps": assignment_gaps,
        "assignment_orphan_total": assignment_orphan_total,
        "metric_decreases": pending_metric_decreases,
        "traffic_decreases": pending_traffic_decreases,
    }
