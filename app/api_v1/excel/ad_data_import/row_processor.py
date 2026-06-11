"""单行广告数据导入处理"""
import logging
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api_v1.excel.ad_data_import.helpers import clean_numeric_value
from app.api_v1.excel.ad_data_import.product_resolver import find_or_create_product
from app.api_v1.excel.utils import (
    is_valid_numeric_value, normalize_date_key, parse_date_value, safe_get_value,
)
from app.core.ad_data_processor import check_and_notify_data_decrease
from app.core.constants import ECPM_MULTIPLIER
from app.core.country_code import find_country_code_by_any_format, preserve_unrecognized_country_code
from app.core.utils import (
    get_date_range, normalize_ad_unit, normalize_date_for_ad_data, truncate_to_2_decimal,
)
from app.models.models import User, AdData

logger = logging.getLogger(__name__)


async def process_row_data(
        row: pd.Series,
        row_num: int,
        product_map: dict[str, dict[str, Any]],
        product_name_map: dict[str, list[dict[str, Any]]],
        mapping_complete: bool,
        client_id: int | None,
        db: AsyncSession,
        current_user: User,
        result: dict[str, Any],
        existing_records: dict[tuple[Any, int], AdData] | None = None
) -> None:
    """
    处理单行数据
    
    参数:
        row: DataFrame行
        row_num: Excel行号
        product_map: 产品映射
        product_name_map: 产品名称映射
        mapping_complete: 映射是否完整
        client_id: 客户ID（查询参数）
        db: 数据库会话
        current_user: 当前用户
        result: 结果字典（用于更新统计）
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        # 解析日期（Excel导入的日期默认是系统时区，不需要转换）
        date_value = row["date"]
        data_date = parse_date_value(date_value)

        # 获取产品名称
        product_name = str(row["product_name"]).strip()
        # ---------- 条件分支 ----------
        if not product_name:
            raise ValueError("产品名称不能为空")

        # 获取Excel中的client_id（如果存在）
        excel_client_id = None
        # ---------- 条件分支 ----------
        if "client_id" in row.index and pd.notna(row.get("client_id")):
            excel_client_id = int(row["client_id"])
        # ---------- 条件分支 ----------
        elif "客户ID" in row.index and pd.notna(row.get("客户ID")):
            excel_client_id = int(row["客户ID"])

        # 查找或创建产品
        product_info = await find_or_create_product(
            product_name=product_name,
            target_client_id=excel_client_id,
            client_id=client_id,
            mapping_complete=mapping_complete,
            product_map=product_map,
            product_name_map=product_name_map,
            db=db,
            current_user=current_user
        )

        # 确定扣减比例
        # ---------- 条件分支 ----------
        if product_info.get("product_name") != product_name:
            logger.info(
                f"产品名称不匹配（Excel: {product_name}, "
                f"数据库: {product_info.get('product_name')}），使用默认扣减比例（0）"
            )
            ecpm_deduct_ratio = 0.0
            revenue_deduct_ratio = 0.0
        else:
            ecpm_deduct_ratio = product_info["ecpm_deduct_ratio"]
            revenue_deduct_ratio = product_info["revenue_deduct_ratio"]

        # 广告单元（可选）
        ad_unit = ''
        # ---------- 条件分支 ----------
        if "ad_unit" in row.index and pd.notna(row.get("ad_unit")):
            ad_unit = normalize_ad_unit(row["ad_unit"])
        # ---------- 条件分支 ----------
        elif "广告单元" in row.index and pd.notna(row.get("广告单元")):
            ad_unit = normalize_ad_unit(row["广告单元"])

        # 国家代码（可选，默认全部区域）
        country_code = "ZZ"
        country_input = None
        # ---------- 条件分支 ----------
        if "country_code" in row.index and pd.notna(row.get("country_code")):
            country_input = str(row["country_code"]).strip()
        # ---------- 条件分支 ----------
        elif "国家代码" in row.index and pd.notna(row.get("国家代码")):
            country_input = str(row["国家代码"]).strip()
        # ---------- 条件分支 ----------
        if country_input:
            found_country_code = await find_country_code_by_any_format(db, country_input)
            # ---------- 条件分支 ----------
            if found_country_code:
                country_code = found_country_code
            else:
                country_code = preserve_unrecognized_country_code(country_input)
                logger.warning(
                    f"无法识别国家代码格式: {country_input}, "
                    f"日期={row.get('date', '未知')}, 产品={product_name}, "
                    f"保留原始值 '{country_code}'"
                )

        # ---------- 条件分支 ----------
        if country_code == "ZZ":
            country_condition = or_(
                AdData.country_code == "ZZ",
                AdData.country_code.is_(None)
            )
        else:
            country_condition = AdData.country_code == country_code

        # 解析数值字段
        # ---------- 异常处理 ----------
        try:
            request_count = int(row["request_count"])
            match_count = int(row["match_count"])
            display_count = int(row["display_count"])
            click_count = int(row["click_count"])
            revenue_before = clean_numeric_value(row["revenue_before_deduct"])

            # 优先使用Excel表中的映射关系数据，如果不存在或为空/NaN，才按照计算公式计算
            # 覆盖率（匹配率）= 匹配数/请求数 * 100
            coverage_rate_val = row.get("coverage_rate")
            # ---------- 条件分支 ----------
            if coverage_rate_val is not None and pd.notna(coverage_rate_val) and str(coverage_rate_val).strip() != "":
                coverage_rate = clean_numeric_value(coverage_rate_val)
            else:
                coverage_rate = (match_count / request_count * 100) if request_count > 0 else 0.0

            # 展示率 = 展示数/匹配数 * 100
            display_rate_val = row.get("display_rate")
            # ---------- 条件分支 ----------
            if display_rate_val is not None and pd.notna(display_rate_val) and str(display_rate_val).strip() != "":
                display_rate = clean_numeric_value(display_rate_val)
            else:
                display_rate = (display_count / match_count * 100) if match_count > 0 else 0.0

            # 点击率 = 点击数/展示数 * 100
            click_rate_val = row.get("click_rate")
            # ---------- 条件分支 ----------
            if click_rate_val is not None and pd.notna(click_rate_val) and str(click_rate_val).strip() != "":
                click_rate = clean_numeric_value(click_rate_val)
            else:
                click_rate = (click_count / display_count * 100) if display_count > 0 else 0.0

            # 可见率（可选字段，如果Excel中有则使用，否则使用默认值0.0）
            viewability_rate_val = safe_get_value(row, "viewability_rate")
            # ---------- 条件分支 ----------
            if is_valid_numeric_value(viewability_rate_val):
                viewability_rate = clean_numeric_value(viewability_rate_val)
            else:
                viewability_rate = 0.0

            # eCPM = 收益/展示数 * 1000
            ecpm_before_val = safe_get_value(row, "ecpm_before_deduct")
            # ---------- 条件分支 ----------
            if is_valid_numeric_value(ecpm_before_val):
                ecpm_before = clean_numeric_value(ecpm_before_val)
            else:
                ecpm_before = (revenue_before / display_count * ECPM_MULTIPLIER) if display_count > 0 else 0.0

            # CPC（可选字段，如果Excel中有则使用，否则使用默认值0.0）
            cpc_val = safe_get_value(row, "cpc")
            # ---------- 条件分支 ----------
            if is_valid_numeric_value(cpc_val):
                cpc = clean_numeric_value(cpc_val)
            else:
                cpc = 0.0

            # PageViews（可选字段，如果Excel中有则使用，否则使用默认值0）
            pageviews_val = safe_get_value(row, "pageviews")
            # ---------- 条件分支 ----------
            if is_valid_numeric_value(pageviews_val):
                pageviews = int(pageviews_val)
            else:
                pageviews = 0

        except (ValueError, TypeError) as e:
            raise ValueError(f"数值字段格式错误: {str(e)}")

        # 验证数值非负
        # ---------- 条件分支 ----------
        if request_count < 0 or match_count < 0 or display_count < 0 or click_count < 0:
            raise ValueError("请求数、匹配数、展示数和点击数不能为负数")
        # ---------- 条件分支 ----------
        if ecpm_before < 0 or revenue_before < 0:
            raise ValueError("eCPM和收益不能为负数")

        # 计算减扣后的值（截断到两位小数，不使用四舍五入）
        ecpm_after = truncate_to_2_decimal(ecpm_before * (1 - ecpm_deduct_ratio))
        revenue_after = truncate_to_2_decimal(revenue_before * (1 - revenue_deduct_ratio))

        logger.debug(
            f"产品: {product_name}, 客户ID: {product_info['client_id']}, "
            f"eCPM扣减比例: {ecpm_deduct_ratio}, 收益扣减比例: {revenue_deduct_ratio}, "
            f"eCPM: {ecpm_before} -> {ecpm_after}, 收益: {revenue_before} -> {revenue_after}"
        )

        # 检查是否已存在相同日期和产品的记录（使用预查询的结果或单独查询）
        existing_data = None
        # ---------- 条件分支 ----------
        if existing_records is not None:
            # 使用预查询的结果（优化性能）
            # 确保日期格式一致（使用date对象，不包含时间）
            date_key = normalize_date_key(data_date)
            key = (date_key, product_info["product_id"], country_code, ad_unit)
            existing_data = existing_records.get(key)
        else:
            # 如果没有预查询结果，则单独查询（向后兼容）
            date_start, date_end = get_date_range(data_date)

            existing_query = select(AdData).where(
                AdData.date >= date_start,
                AdData.date <= date_end,
                AdData.product_id == product_info["product_id"],
                AdData.ad_unit == ad_unit,
                country_condition
            )
            existing_result = await db.execute(existing_query)
            existing_data = existing_result.scalars().first()

        # ---------- 条件分支 ----------
        if existing_data:
            # 更新现有记录
            logger.info(
                f"⚠️ 数据库中存在重复记录: 日期={data_date}, "
                f"产品ID={product_info['product_id']}，将更新现有记录"
            )
            # 检查数据是否减少（在更新之前）
            # 格式化日期字符串（data_date 可能是 date 或 datetime 类型）
            # ---------- 条件分支 ----------
            if isinstance(data_date, datetime):
                date_str = data_date.date().isoformat()
            # ---------- 条件分支 ----------
            elif hasattr(data_date, 'isoformat'):
                date_str = data_date.isoformat()
            else:
                date_str = str(data_date)

            await check_and_notify_data_decrease(
                existing_data=existing_data,
                new_request_count=request_count,
                new_match_count=match_count,
                new_display_count=display_count,
                new_click_count=click_count,
                new_revenue_before=revenue_before,
                new_revenue_after=revenue_after,
                date_str=date_str,
                product_name=product_name,
                country_code=country_code,
                source=f"Excel导入（用户: {current_user.username}）"
            )

            existing_data.country_code = country_code
            existing_data.ad_unit = ad_unit
            existing_data.request_count = request_count
            existing_data.match_count = match_count
            existing_data.display_count = display_count
            existing_data.click_count = click_count
            existing_data.viewability_rate = viewability_rate
            existing_data.cpc = cpc
            existing_data.pageviews = pageviews
            existing_data.ecpm_before_deduct = ecpm_before
            existing_data.ecpm_after_deduct = ecpm_after
            existing_data.revenue_before_deduct = revenue_before
            existing_data.revenue_after_deduct = revenue_after
            # 如果Excel中提供了比率字段，使用Excel的值；否则使用计算值
            # 注意：coverage_rate, display_rate, click_rate 已经在前面使用 clean_numeric_value() 转换过了
            existing_data.coverage_rate = coverage_rate
            existing_data.display_rate = display_rate
            existing_data.click_rate = click_rate
            existing_data.viewability_rate = viewability_rate
            # 如果基础数据有变化，重新计算比率字段（确保一致性）
            existing_data.calculate_rates()
            result["updated_rows"] += 1
            logger.debug(f"✅ 已更新记录: 日期={data_date}, 产品={product_name}")
        else:
            # 创建新记录
            # 注意：如果data_date是date类型，需要转换为datetime（使用当天的00:00:00）
            # Excel导入的日期默认是系统时区，不需要进行时区转换
            # 确保与数据库中的DateTime类型一致
            ad_data_date = normalize_date_for_ad_data(data_date)

            ad_data = AdData(
                date=ad_data_date,
                product_id=product_info["product_id"],
                ad_unit=ad_unit,
                country_code=country_code,
                request_count=request_count,
                match_count=match_count,
                display_count=display_count,
                click_count=click_count,
                viewability_rate=viewability_rate,
                cpc=cpc,
                pageviews=pageviews,
                ecpm_before_deduct=ecpm_before,
                ecpm_after_deduct=ecpm_after,
                revenue_before_deduct=revenue_before,
                revenue_after_deduct=revenue_after
            )
            # 如果Excel中提供了比率字段，使用Excel的值；否则使用计算值
            # 注意：coverage_rate, display_rate, click_rate 已经在前面使用 clean_numeric_value() 转换过了
            ad_data.coverage_rate = coverage_rate
            ad_data.display_rate = display_rate
            ad_data.click_rate = click_rate
            ad_data.viewability_rate = viewability_rate
            # 调用计算方法确保比率字段正确（如果基础数据有变化，会重新计算）
            ad_data.calculate_rates()
            db.add(ad_data)
            result["new_rows"] += 1
            logger.debug(f"✅ 已创建新记录: 日期={data_date}, 产品={product_name}")

            # 将新创建的记录添加到existing_records缓存中，以便后续行能检测到同一批数据中的重复
            # 这样可以避免同一批数据中的重复记录被插入（虽然数据库唯一性约束也会防止，但提前检测更好）
            # ---------- 条件分支 ----------
            if existing_records is not None:
                # 确保日期格式一致（使用date对象，不包含时间）
                date_key = normalize_date_key(data_date)
                key = (date_key, product_info["product_id"], country_code, ad_unit)
                existing_records[key] = ad_data

        result["success_rows"] += 1

    except Exception as e:
        result["failed_rows"] += 1
        result["errors"].append({
            "row": row_num,
            "error": str(e)
        })

