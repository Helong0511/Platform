"""广告数据 Excel 导出处理

职责：按筛选条件查询 AdData，生成 xlsx 流式响应；支持管理员全量与客户自有数据。

权限：需登录；数据范围按角色过滤。

说明：Excel 批量导入/导出，支持广告数据等业务的表格批处理。"""
import logging
from calendar import monthrange
from datetime import date, datetime
from fastapi import Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.country_code import resolve_country_name
from app.services.ad_data.queries.filter_conditions import apply_ad_data_scope_filters
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.query_utils import check_use_assignment_table
from app.core.security import get_current_user
from app.core.excel_io import excel_streaming_response
from app.models.models import User, Client, Product, AdData, UserRole, ProductAssignment, CountryInfo
from app.services.ad_data.queries.dimension_filter import (
    build_ad_data_dimension_filter,
    is_cross_dimension,
    normalize_dimension,
)
from app.services.ad_data.queries.daily_summary_query import DailySummaryQuery

logger = logging.getLogger(__name__)

MAX_DAILY_SUMMARY_EXPORT_ROWS = 50_000


def resolve_daily_summary_export_grouping(
    dimension: str | None,
    split_by_country: bool,
) -> tuple[bool, bool]:
    """
    与 DailySummaryQuery.fetch 及每日统计各子页配置对齐的分组列。

    - 每日统计：country + split_by_country=false → 仅日期+产品
    - 国家数据：country + split_by_country=true → 日期+产品+国家
    - 广告单元：ad_unit → 日期+产品+广告单元
    - 详细报表：ad_unit_country → 日期+产品+广告单元+国家
    """
    dim = normalize_dimension(dimension)
    group_by_ad_unit = dim == "ad_unit" or is_cross_dimension(dim)
    group_by_country = split_by_country or is_cross_dimension(dim)
    return group_by_ad_unit, group_by_country


def build_daily_summary_export_row(
    row: dict,
    *,
    is_admin_user: bool,
    group_by_ad_unit: bool,
    group_by_country: bool,
) -> dict:
    """将 daily-summary 汇总行转为 Excel 列（列与每日统计页表格一致）。"""
    coverage_rate = row.get("coverage_rate", 0) or 0
    display_rate = row.get("display_rate", 0) or 0
    click_rate = row.get("click_rate", 0) or 0
    viewability_rate = row.get("viewability_rate", 0) or 0

    excel_row: dict = {
        "数据日期": row.get("date", ""),
        "产品名称": row.get("product_name", ""),
    }
    if is_admin_user:
        excel_row["所属用户"] = row.get("user_name", "")
    if group_by_ad_unit:
        excel_row["广告单元"] = row.get("ad_unit") or ""
    if group_by_country:
        excel_row["国家"] = row.get("country_name_zh") or ""

    excel_row.update(
        {
            "请求数": row.get("request_count", 0),
            "匹配数": row.get("match_count", 0),
            "覆盖率": f"{coverage_rate}%",
            "展示数": row.get("display_count", 0),
            "展示率": f"{display_rate}%",
            "点击数": row.get("click_count", 0),
            "点击率": f"{click_rate}%",
            "可见率": f"{viewability_rate}%",
            "CPC($)": round(row.get("cpc") or 0.0, 2),
            "PageViews": row.get("pageviews", 0) or 0,
            "eCPM(扣)($)": round(row.get("ecpm_after_deduct") or 0.0, 4),
            "收益(扣)($)": round(row.get("revenue_after_deduct") or 0.0, 4),
        }
    )
    if is_admin_user:
        excel_row["eCPM($)"] = round(row.get("ecpm_before_deduct") or 0.0, 4)
        excel_row["收益($)"] = round(row.get("revenue_before_deduct") or 0.0, 4)
    else:
        excel_row["eCPM($)"] = round(row.get("ecpm_after_deduct") or 0.0, 4)
        excel_row["收益($)"] = round(row.get("revenue_after_deduct") or 0.0, 4)

    return excel_row


async def _export_daily_summary_excel(
    db: AsyncSession,
    current_user: User,
    target_client_id: str | None,
    start_date: date | None,
    end_date: date | None,
    product_id: str | None,
    country_code: str | None,
    ad_unit: str | None,
    dimension: str | None,
    split_by_country: bool,
    sort_by: str,
    sort_order: str,
) -> StreamingResponse:
    """每日统计页导出：与 daily-summary API 相同聚合粒度，非底层明细。"""
    group_by_ad_unit, group_by_country = resolve_daily_summary_export_grouping(
        dimension, split_by_country
    )

    product_id_str = product_id
    summary_query = DailySummaryQuery(db)

    _, total, _ = await summary_query.fetch(
        current_user=current_user,
        page=1,
        page_size=1,
        start_date=start_date,
        end_date=end_date,
        client_id=target_client_id,
        product_id=product_id_str,
        country_code=country_code,
        ad_unit=ad_unit,
        dimension=dimension,
        split_by_country=split_by_country,
        sort_by=sort_by or "date",
        sort_order=sort_order or "desc",
    )

    if total == 0:
        filter_info = []
        if start_date:
            filter_info.append(f"开始日期: {start_date}")
        if end_date:
            filter_info.append(f"结束日期: {end_date}")
        if product_id:
            filter_info.append(f"产品ID: {product_id}")
        if target_client_id:
            filter_info.append(f"客户ID: {target_client_id}")
        if country_code and country_code.strip() and country_code.strip() != "ZZ":
            filter_info.append(f"国家代码: {country_code}")
        filter_text = "、".join(filter_info) if filter_info else "当前筛选条件"
        raise_api_exception(
            error_code=ErrorCode.NOT_FOUND,
            message="无数据，不能导出",
            detail=f"当前筛选条件下没有可导出的数据（{filter_text}）。请调整筛选条件或确认是否有数据后重试",
        )

    export_page_size = min(total, MAX_DAILY_SUMMARY_EXPORT_ROWS)
    if total > MAX_DAILY_SUMMARY_EXPORT_ROWS:
        logger.warning(
            "每日统计导出行数 %s 超过上限 %s，仅导出前 %s 行",
            total,
            MAX_DAILY_SUMMARY_EXPORT_ROWS,
            MAX_DAILY_SUMMARY_EXPORT_ROWS,
        )

    rows, _, _ = await summary_query.fetch(
        current_user=current_user,
        page=1,
        page_size=export_page_size,
        start_date=start_date,
        end_date=end_date,
        client_id=target_client_id,
        product_id=product_id_str,
        country_code=country_code,
        ad_unit=ad_unit,
        dimension=dimension,
        split_by_country=split_by_country,
        sort_by=sort_by or "date",
        sort_order=sort_order or "desc",
    )

    is_admin_user = current_user.role == UserRole.ADMIN
    data = [
        build_daily_summary_export_row(
            row,
            is_admin_user=is_admin_user,
            group_by_ad_unit=group_by_ad_unit,
            group_by_country=group_by_country,
        )
        for row in rows
    ]

    return excel_streaming_response(data, "每日统计", "每日统计", max_col_width=None)


async def export_ad_data_handler(
        start_date: date | None = None,
        end_date: date | None = None,
        product_id: str | None = None,
        client_id: str | None = None,
        country_code: str | None = None,
        ad_unit: str | None = None,
        dimension: str | None = None,
        data_source: str | None = None,
        upstream_account: str | None = None,
        report_type: str | None = None,
        daily_summary: bool = False,
        split_by_country: bool = False,
        sort_by: str = "date",
        sort_order: str = "desc",
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> StreamingResponse:
    """
    导出广告数据到Excel文件
    - 客户只能导出自己的广告数据
    - 支持按日期范围、产品ID和国家代码过滤
    - 返回Excel文件流
    
    功能：导出数据（export_ad_data_handler）。
    实现：异步端点，通过 Service 层访问数据库/缓存。
    鉴权：由 Depends(get_current_user) 或 require_admin 控制访问范围。
    响应：统一 ResponseBaseSchema / PaginatedResponseBaseSchema 包装。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 获取客户信息 - 使用selectinload预加载（如果需要）
    # ---------- 条件分支 ----------
    if current_user.role != UserRole.ADMIN:
        # 优化：直接查询客户，避免额外查询
        client_query = select(Client).where(Client.user_id == current_user.id)
        client_result = await db.execute(client_query)
        client = client_result.scalars().first()
        # ---------- 条件分支 ----------
        if not client:
            logger.warning(f"客户用户 {current_user.username} 没有关联的客户账户")
            raise_api_exception(
                error_code=ErrorCode.FORBIDDEN,
                message="没有关联的客户账户，无法导出数据",
                detail="客户用户必须关联客户账户才能导出数据。请联系管理员为您创建客户账户"
            )
        target_client_id = client.id

        # 额外检查：客户是否有任何广告数据（在应用筛选条件之前先检查是否有数据）
        # 先检查是否使用产品分配历史表
        use_assignment_table_for_count = await check_use_assignment_table(db)

        data_count_query = select(func.count(AdData.id)).join(
            Product, AdData.product_id == Product.id
        )
        # ---------- 条件分支 ----------
        if use_assignment_table_for_count:
            # 使用产品分配历史表（优化：避免在 AdData.date 上使用 func.date()）
            # 使用与 ad_data.py 完全相同的方式，将日期范围条件放在 JOIN 条件中
            # 注意：不在JOIN条件中直接过滤client_id，而是先JOIN，然后在WHERE子句中过滤
            data_count_query = data_count_query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    # MySQL 会自动将 DATE 转换为 DATETIME，所以可以直接比较
                    AdData.date >= ProductAssignment.start_date,
                    or_(
                        ProductAssignment.end_date.is_(None),
                        # 使用 DATE_ADD 确保包含整天的数据（end_date 23:59:59.999999）
                        AdData.date < func.date_add(ProductAssignment.end_date, text("INTERVAL 1 DAY"))
                    )
                )
            )
            # JOIN Client表，然后通过WHERE子句过滤客户ID（与 ad_data.py 保持一致）
            data_count_query = data_count_query.join(Client, ProductAssignment.client_id == Client.id)
            # 在WHERE子句中过滤客户ID（如果指定了客户ID）
            # ---------- 条件分支 ----------
            if target_client_id is not None:
                data_count_query = data_count_query.where(Client.id == target_client_id)
        else:
            # 旧的查询方式
            # ---------- 条件分支 ----------
            if target_client_id is not None:
                data_count_query = data_count_query.where(Product.client_id == target_client_id)

        # 应用产品状态过滤（只统计激活状态的产品）
        data_count_query = data_count_query.where(Product.is_active == True)

        # 应用日期范围过滤（如果指定了日期范围）
        # ---------- 条件分支 ----------
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            data_count_query = data_count_query.where(AdData.date >= start_datetime)
        # ---------- 条件分支 ----------
        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())
            data_count_query = data_count_query.where(AdData.date <= end_datetime)

        data_count_result = await db.execute(data_count_query)
        total_data_count = data_count_result.scalar() or 0

        # ---------- 条件分支 ----------
        if total_data_count == 0:
            logger.info(f"客户用户 {current_user.username} (客户ID: {target_client_id}) 没有任何广告数据")
            raise_api_exception(
                error_code=ErrorCode.NOT_FOUND,
                message="无数据，不能导出",
                detail="您的账户下没有任何广告数据，无法导出。请先导入数据后再试"
            )
    else:
        # 管理员可以指定客户ID，也可以不指定（导出所有客户的数据）
        target_client_id = client_id

    if daily_summary:
        return await _export_daily_summary_excel(
            db=db,
            current_user=current_user,
            target_client_id=target_client_id,
            start_date=start_date,
            end_date=end_date,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
            dimension=dimension,
            split_by_country=split_by_country,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    # 检查是否使用产品分配历史表
    use_assignment_table = await check_use_assignment_table(db)

    # 构建查询（同时查询国家信息）
    query = select(AdData, CountryInfo)
    query = query.join(Product, AdData.product_id == Product.id)

    # ---------- 条件分支 ----------
    if use_assignment_table:
        # 使用产品分配历史表：根据日期范围匹配正确的客户归属（优化：避免在 AdData.date 上使用 func.date()）
        # 注意：导出时需要考虑日期范围，确保只导出该客户在该时间段内的数据
        # 使用与 ad_data.py 完全相同的方式，将日期范围条件放在 JOIN 条件中
        # 注意：不在JOIN条件中直接过滤client_id，而是先JOIN，然后在WHERE子句中过滤
        query = query.join(
            ProductAssignment,
            and_(
                ProductAssignment.product_id == Product.id,
                # MySQL 会自动将 DATE 转换为 DATETIME，所以可以直接比较
                AdData.date >= ProductAssignment.start_date,
                or_(
                    ProductAssignment.end_date.is_(None),
                    # 使用 DATE_ADD 确保包含整天的数据（end_date 23:59:59.999999）
                    AdData.date < func.date_add(ProductAssignment.end_date, text("INTERVAL 1 DAY"))
                )
            )
        )
        # JOIN Client表，然后通过WHERE子句过滤客户ID（与 ad_data.py 保持一致）
        query = query.join(Client, ProductAssignment.client_id == Client.id)
    else:
        query = query.join(Client, Product.client_id == Client.id)

    # 左关联国家信息（在所有其他JOIN之后）
    # 修复排序规则冲突：使用 COLLATE 统一排序规则
    query = query.outerjoin(
        CountryInfo,
        AdData.country_code.collate('utf8mb4_unicode_ci') ==
        CountryInfo.alpha_2_code.collate('utf8mb4_unicode_ci')
    )

    # 应用产品状态过滤（只显示激活状态的产品，与 ad_data.py 保持一致）
    query = query.where(Product.is_active == True)

    query = query.where(
        build_ad_data_dimension_filter(
            AdData.country_code, AdData.ad_unit, dimension,
            report_type_column=AdData.report_type,
        )
    )

    scope_client_id = (
        target_client_id
        if current_user.role == UserRole.ADMIN
        else str(target_client_id)
    )
    query = await apply_ad_data_scope_filters(
        db,
        query,
        current_user=current_user,
        client_id=scope_client_id,
        product_id=product_id,
        country_code=country_code,
        ad_unit=ad_unit,
        dimension=dimension,
        data_source=data_source,
        upstream_account=upstream_account,
        report_type=report_type,
    )

    # 应用日期过滤（直接使用条件，避免函数可能的问题）
    # ---------- 条件分支 ----------
    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time())
        query = query.where(AdData.date >= start_datetime)
    # ---------- 条件分支 ----------
    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time())
        query = query.where(AdData.date <= end_datetime)
    # 如果没有指定日期范围，默认查询当前月的数据（与 ad_data.py 保持一致）
    # ---------- 条件分支 ----------
    elif not start_date and not end_date:
        today = date.today()
        # 当前月的第一天
        month_start = date(today.year, today.month, 1)
        # 当前月的最后一天
        _, last_day = monthrange(today.year, today.month)
        month_end = date(today.year, today.month, last_day)

        month_start_datetime = datetime.combine(month_start, datetime.min.time())
        month_end_datetime = datetime.combine(month_end, datetime.max.time())
        query = query.where(AdData.date >= month_start_datetime)
        query = query.where(AdData.date <= month_end_datetime)

    # 执行查询
    result = await db.execute(query.order_by(AdData.date.desc()))
    ad_data_results = result.all()  # 返回 (AdData, CountryInfo) 元组列表

    # 如果没有数据，抛出错误提示用户
    # ---------- 条件分支 ----------
    if not ad_data_results or len(ad_data_results) == 0:
        # 构建更详细的错误信息
        filter_info = []
        # ---------- 条件分支 ----------
        if start_date:
            filter_info.append(f"开始日期: {start_date}")
        # ---------- 条件分支 ----------
        if end_date:
            filter_info.append(f"结束日期: {end_date}")
        # ---------- 条件分支 ----------
        if product_id:
            filter_info.append(f"产品ID: {product_id}")
        # ---------- 条件分支 ----------
        if client_id:
            filter_info.append(f"客户ID: {client_id}")
        # ---------- 条件分支 ----------
        if country_code and country_code.strip() and country_code.strip() != 'ZZ':
            filter_info.append(f"国家代码: {country_code}")

        filter_text = "、".join(filter_info) if filter_info else "当前筛选条件"

        raise_api_exception(
            error_code=ErrorCode.NOT_FOUND,
            message="无数据，不能导出",
            detail=f"当前筛选条件下没有可导出的数据（{filter_text}）。请调整筛选条件或确认是否有数据后重试"
        )

    is_admin = current_user.role == UserRole.ADMIN

    product_ids = list({ad_data.product_id for ad_data, _ in ad_data_results})
    products_query = select(Product).where(Product.id.in_(product_ids))
    products_result = await db.execute(products_query)
    products = products_result.scalars().all()
    product_map = {p.id: p.name for p in products}

    product_to_user_map = {}
    # ---------- 条件分支 ----------
    if is_admin:
        client_ids = list({p.client_id for p in products})
        clients_query = select(Client, User).join(
            User, Client.user_id == User.id
        ).where(Client.id.in_(client_ids))
        clients_result = await db.execute(clients_query)
        client_user_map = {}
        # ---------- 循环处理 ----------
        for client, user in clients_result.all():
            client_user_map[client.id] = user.full_name or user.username

        # ---------- 循环处理 ----------
        for product in products:
            product_to_user_map[product.id] = client_user_map.get(
                product.client_id, "未知用户"
            )

    data = []
    # ---------- 循环处理 ----------
    for item, country_info in ad_data_results:
        coverage_rate = item.coverage_rate if item.coverage_rate is not None else round(
            (item.match_count / item.request_count * 100) if item.request_count > 0 else 0.0,
            2
        )
        display_rate = item.display_rate if item.display_rate is not None else round(
            (item.display_count / item.match_count * 100) if item.match_count > 0 else 0.0,
            2
        )
        click_rate = item.click_rate if item.click_rate is not None else round(
            (item.click_count / item.display_count * 100) if item.display_count > 0 else 0.0,
            2
        )

        date_value = item.date
        # ---------- 条件分支 ----------
        if isinstance(date_value, datetime):
            date_value = date_value.date()
        # ---------- 条件分支 ----------
        elif hasattr(date_value, 'date'):
            date_value = date_value.date()

        country_code = item.country_code or ""
        country_name = resolve_country_name(country_info, country_code) or ""

        # ---------- 条件分支 ----------
        if is_admin:
            row_data = {
                "数据日期": date_value,
                "所属用户": product_to_user_map.get(item.product_id, "未知用户"),
                "产品名称": product_map.get(item.product_id, "未知产品"),
                "来源": item.data_source or "legacy",
                "账号": item.upstream_account or "",
                "报表类型": item.report_type or "legacy",
                "广告单元": item.ad_unit or "",
                "国家代码": country_code,
                "国家": country_name,
                "请求数": item.request_count,
                "匹配数": item.match_count,
                "覆盖率": f"{coverage_rate}%",
                "展示数": item.display_count,
                "展示率": f"{display_rate}%",
                "点击数": item.click_count,
                "点击率": f"{click_rate}%",
                "CPC($)": round(item.cpc or 0.0, 2),
                "PageViews": item.pageviews or 0,
                "eCPM(扣)($)": round(item.ecpm_after_deduct, 4),
                "eCPM($)": round(item.ecpm_before_deduct, 4),
                "收益(扣)($)": round(item.revenue_after_deduct, 4),
                "收益($)": round(item.revenue_before_deduct, 4)
            }
        else:
            row_data = {
                "数据日期": date_value,
                "产品名称": product_map.get(item.product_id, "未知产品"),
                "广告单元": item.ad_unit or "",
                "国家代码": country_code,
                "国家": country_name,
                "请求数": item.request_count,
                "匹配数": item.match_count,
                "覆盖率": f"{coverage_rate}%",
                "展示数": item.display_count,
                "展示率": f"{display_rate}%",
                "点击数": item.click_count,
                "点击率": f"{click_rate}%",
                "CPC($)": round(item.cpc or 0.0, 2),
                "PageViews": item.pageviews or 0,
                "eCPM($)": round(item.ecpm_after_deduct, 4),
                "收益($)": round(item.revenue_after_deduct, 4)
            }

        data.append(row_data)

    # ---------- 构建响应 ----------
    return excel_streaming_response(
        data, "广告数据", "广告数据", max_col_width=None
    )
