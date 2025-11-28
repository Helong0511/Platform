"""
Excel导出处理模块
处理广告数据的Excel导出逻辑
"""
from fastapi import Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, text
from sqlalchemy.sql import literal_column
from datetime import date, datetime
from calendar import monthrange
from io import BytesIO
from urllib.parse import quote
import logging

import pandas as pd

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import User, Client, Product, AdData, UserRole, ProductAssignment, CountryInfo
from app.core.query_utils import product_assignment_join_condition, date_range_condition, check_use_assignment_table

logger = logging.getLogger(__name__)


async def export_ad_data_handler(
        start_date: date | None = None,
        end_date: date | None = None,
        product_id: int | None = None,
        client_id: int | None = None,
        country_code: str | None = None,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> StreamingResponse:
    """
    导出广告数据到Excel文件
    - 客户只能导出自己的广告数据
    - 支持按日期范围、产品ID和国家代码过滤
    - 返回Excel文件流
    """
    # 获取客户信息 - 使用selectinload预加载（如果需要）
    if current_user.role != UserRole.ADMIN:
        # 优化：直接查询客户，避免额外查询
        from sqlalchemy.orm import selectinload
        client_query = select(Client).where(Client.user_id == current_user.id)
        client_result = await db.execute(client_query)
        client = client_result.scalars().first()
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
            if target_client_id is not None:
                data_count_query = data_count_query.where(Client.id == target_client_id)
        else:
            # 旧的查询方式
            if target_client_id is not None:
                data_count_query = data_count_query.where(Product.client_id == target_client_id)
        
        # 应用产品状态过滤（只统计激活状态的产品）
        data_count_query = data_count_query.where(Product.is_active == True)
        
        # 应用日期范围过滤（如果指定了日期范围）
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            data_count_query = data_count_query.where(AdData.date >= start_datetime)
        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())
            data_count_query = data_count_query.where(AdData.date <= end_datetime)
        
        data_count_result = await db.execute(data_count_query)
        total_data_count = data_count_result.scalar() or 0

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

    # 检查是否使用产品分配历史表
    use_assignment_table = await check_use_assignment_table(db)
    
    # 构建查询（同时查询国家信息）
    query = select(AdData, CountryInfo)
    query = query.join(Product, AdData.product_id == Product.id)
    
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
        # 在WHERE子句中过滤客户ID（如果指定了客户ID）
        if target_client_id is not None:
            query = query.where(Client.id == target_client_id)
    else:
        # 旧的查询方式：直接通过Product.client_id关联
        # 如果指定了客户ID，直接过滤；如果没有指定，需要JOIN Client表来支持后续的权限过滤
        if target_client_id is not None:
            query = query.where(Product.client_id == target_client_id)
        else:
            # 如果没有指定客户ID，JOIN Client表以便后续可能的权限过滤
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
    
    # 应用日期过滤（直接使用条件，避免函数可能的问题）
    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time())
        query = query.where(AdData.date >= start_datetime)
    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time())
        query = query.where(AdData.date <= end_datetime)
    # 如果没有指定日期范围，默认查询当前月的数据（与 ad_data.py 保持一致）
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

    # 应用产品过滤
    if product_id:
        if use_assignment_table:
            # 使用产品分配历史表时，需要验证产品在指定日期范围内是否属于该客户
            # 这里简化处理：如果查询能返回数据，说明产品在该时间段属于该客户
            pass  # 验证逻辑已经在JOIN条件中处理
        else:
            # 旧的验证方式：验证产品是否属于该客户
            product_query = select(Product).where(
                and_(
                    Product.id == product_id,
                    Product.client_id == target_client_id
                )
            )
            product_result = await db.execute(product_query)
            product = product_result.scalars().first()
            if not product:
                raise_api_exception(
                    error_code=ErrorCode.NOT_FOUND,
                    message=f"产品ID {product_id} 不存在或不属于该客户",
                    detail="请选择有效的产品"
                )
        query = query.where(AdData.product_id == product_id)

    # 国家代码过滤
    if country_code and country_code.strip():
        country_code_clean = country_code.strip()
        # 验证国家代码长度（ISO 3166-1 二字母代码最多2个字符）
        if country_code_clean != 'ZZ' and len(country_code_clean) <= 2:
            query = query.where(AdData.country_code == country_code_clean)
        elif len(country_code_clean) > 2:
            # 国家代码长度超过2个字符，记录警告但不报错
            logger.warning(f"导出时国家代码长度超过2个字符: {country_code_clean}，将忽略此过滤条件")

    # 执行查询
    result = await db.execute(query.order_by(AdData.date.desc()))
    ad_data_results = result.all()  # 返回 (AdData, CountryInfo) 元组列表

    # 如果没有数据，抛出错误提示用户
    if not ad_data_results or len(ad_data_results) == 0:
        # 构建更详细的错误信息
        filter_info = []
        if start_date:
            filter_info.append(f"开始日期: {start_date}")
        if end_date:
            filter_info.append(f"结束日期: {end_date}")
        if product_id:
            filter_info.append(f"产品ID: {product_id}")
        if client_id:
            filter_info.append(f"客户ID: {client_id}")
        if country_code and country_code.strip() and country_code.strip() != 'ZZ':
            filter_info.append(f"国家代码: {country_code}")

        filter_text = "、".join(filter_info) if filter_info else "当前筛选条件"

        raise_api_exception(
            error_code=ErrorCode.NOT_FOUND,
            message="无数据，不能导出",
            detail=f"当前筛选条件下没有可导出的数据（{filter_text}）。请调整筛选条件或确认是否有数据后重试"
        )

    # 创建Excel文件
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # 根据用户角色定义列名
        is_admin = current_user.role == UserRole.ADMIN

        # 获取所有相关产品信息
        product_ids = list({ad_data.product_id for ad_data, _ in ad_data_results})
        products_query = select(Product).where(Product.id.in_(product_ids))
        products_result = await db.execute(products_query)
        products = products_result.scalars().all()
        product_map = {p.id: p.name for p in products}

        # 创建产品ID到客户用户名的映射（仅管理员需要）
        product_to_user_map = {}
        if is_admin:
            # 获取所有相关客户和用户信息
            client_ids = list({p.client_id for p in products})
            clients_query = select(Client, User).join(
                User, Client.user_id == User.id
            ).where(Client.id.in_(client_ids))
            clients_result = await db.execute(clients_query)
            client_user_map = {}
            for client, user in clients_result.all():
                client_user_map[client.id] = user.full_name or user.username

            for product in products:
                product_to_user_map[product.id] = client_user_map.get(
                    product.client_id, "未知用户"
                )

        # 创建数据列表
        data = []
        for item, country_info in ad_data_results:
            # 使用数据库字段中的比率（如果为空则计算）
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

            # 处理日期格式
            date_value = item.date
            if isinstance(date_value, datetime):
                date_value = date_value.date()
            elif hasattr(date_value, 'date'):
                date_value = date_value.date()

            # 获取国家信息
            country_code = item.country_code or ""
            # 如果通过JOIN找到了国家信息，使用它；否则根据country_code回退
            if country_info:
                country_name = country_info.country_name_zh
            elif country_code == "AA":
                country_name = "未知区域"
            elif country_code == "ZZ":
                country_name = "全部区域"
            else:
                country_name = ""

            # 按照指定顺序构建数据行
            if is_admin:
                # 管理员：显示所有列，按照指定顺序
                row_data = {
                    "数据日期": date_value,
                    "所属用户": product_to_user_map.get(item.product_id, "未知用户"),
                    "产品名称": product_map.get(item.product_id, "未知产品"),
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
                # 客户：只显示扣减后的数据，按照指定顺序（不包含"所属用户"列）
                row_data = {
                    "数据日期": date_value,
                    "产品名称": product_map.get(item.product_id, "未知产品"),
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

        # 转换为DataFrame
        df = pd.DataFrame(data)

        # 写入Excel
        df.to_excel(writer, index=False, sheet_name="广告数据")

        # 设置列宽自适应
        worksheet = writer.sheets["广告数据"]
        # 根据内容自适应列宽
        for column_cells in worksheet.columns:
            max_length = max(len(str(cell.value)) for cell in column_cells)
            worksheet.column_dimensions[column_cells[0].column_letter].width = max_length + 2

    # 准备响应
    output.seek(0)
    filename = f"广告数据_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    # 对文件名进行URL编码以支持中文字符
    encoded_filename = quote(filename, safe='')
    # 使用RFC 2231格式支持中文文件名
    content_disposition = f"attachment; filename*=UTF-8''{encoded_filename}"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disposition}
    )
