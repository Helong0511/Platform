"""淘宝搜索数据（TB Search Data）管理 API

职责：
- 分页查询 TB 搜索指标（redirects/searches/clicks/revenue/rpm 等）
- Excel 批量导入（管理员）
- 单条/批量删除与更新（管理员）
- 筛选下拉：有数据的客户、产品、国家列表

权限：
- 列表与筛选：登录用户；非管理员仅能看到自己名下客户数据
- 导入/更新/删除：仅管理员

主要端点：
- GET  /              分页列表（支持日期、客户、产品、国家筛选）
- POST /import         Excel 导入
- POST /{data_id}      更新单条
- DELETE /{data_id}    删除单条
- DELETE /batch        批量删除
- GET  /clients-with-data、/products-with-data、/countries-with-data  筛选选项。

说明：REST API 端点，统一 ResponseBaseSchema 响应；鉴权由各端点 Depends 声明。"""
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status, UploadFile, File
from sqlalchemy import delete, func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import pandas as pd

from app.core.audit_log import log_update, log_delete, log_user_action
from app.core.database import get_db
from app.core.security import get_current_user, is_admin
from app.core.constants import MAX_PAGE_SIZE
from app.core.config import settings
from app.core.validation import safe_strip
from app.models.models import TBSearchData, Client, Product, User, UserRole, CountryInfo, ProductAssignment
from app.schemas.tb_search_data import (
    TBSearchDataResponse,
    TBSearchDataUpdate,
)
from app.schemas.base import ResponseBaseSchema, ListResponseBaseSchema, PaginatedResponseBaseSchema
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.query_utils import (
    product_assignment_join_condition, 
    check_use_assignment_table, 
    join_country_info as join_country_info_util,
    apply_date_range_filter
)
from app.services.ad_data.queries.join_helpers import (
    build_products_with_data_base_query,
    join_tb_search_and_client_from_product,
    merge_product_options_with_ownership,
)
from app.core.utils import (
    find_or_create_default_client, optimize_page_size_for_device,
    get_product_name, get_client_name, get_user_name, apply_deduct_ratio
)
from app.core.country_code import resolve_country_name, find_country_code_by_any_format, preserve_unrecognized_country_code
from app.api_v1.excel.utils import (
    allowed_file, ALLOWED_MIME_TYPES, parse_date_value, normalize_date_key, validate_excel_file
)

router = APIRouter()
logger = logging.getLogger(__name__)

# 使用公共函数 join_country_info，传入 TBSearchData.country_code 列
def join_country_info(query):
    """
    辅助函数：统一处理 CountryInfo 的 JOIN，解决排序规则冲突问题
    
    注意：此函数是对公共函数 join_country_info 的包装，传入 TBSearchData.country_code
    """
    return join_country_info_util(query, TBSearchData.country_code)

@router.get("/", response_model=PaginatedResponseBaseSchema[list[TBSearchDataResponse]], summary="获取TB搜索数据列表")
async def get_tb_search_data(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    start_date: date | None = Query(None, description="开始日期"),
    end_date: date | None = Query(None, description="结束日期"),
    client_id: int | None = Query(None, description="客户ID"),
    product_id: str | None = Query(None, description="产品ID"),
    country_code: str | None = Query(None, description="国家代码"),
    sort_by: str = Query("date", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向")
):
    """
    分页获取 TB 搜索数据列表。

    - 支持按日期、客户、产品、国家筛选；未传日期时默认当前月
    - 自动选择产品分配历史表或旧 client_id 关联方式
    - 非管理员仅能查看自己名下客户数据
    """
    # ---------- 入口：参数与依赖准备 ----------
    page_size = optimize_page_size_for_device(request, page_size, default_page_size=10)

    # 检查是否使用产品分配历史表
    use_assignment_table = await check_use_assignment_table(db)
    # ---------- 条件分支 ----------
    if not settings.is_production:
        # ---------- 条件分支 ----------
        if use_assignment_table:
            logger.debug("TB搜索数据：使用产品分配历史表查询")
        else:
            logger.debug("TB搜索数据：使用旧的查询方式（直接通过Product.client_id关联）")

    # 构建查询
    # 使用LEFT JOIN确保即使关联数据缺失也能查询到TB搜索数据
    # ---------- 条件分支 ----------
    if use_assignment_table:
        # 使用产品分配历史表进行查询
        query = select(TBSearchData, Product, Client, User, ProductAssignment, CountryInfo)
        query = query.outerjoin(Product, TBSearchData.product_id == Product.id)
        # 关联产品分配历史表：根据TB搜索数据的日期匹配正确的分配记录
        query = query.outerjoin(
            ProductAssignment,
            and_(
                ProductAssignment.product_id == Product.id,
                product_assignment_join_condition(
                    TBSearchData.date,
                    ProductAssignment.start_date,
                    ProductAssignment.end_date
                )
            )
        )
        # 通过产品分配历史表关联客户
        query = query.outerjoin(Client, ProductAssignment.client_id == Client.id)
        query = query.outerjoin(User, Client.user_id == User.id)
        query = join_country_info(query)
    else:
        # 旧的查询方式：直接通过Product.client_id关联
        query = select(TBSearchData, Product, Client, User, CountryInfo)
        query = query.outerjoin(Product, TBSearchData.product_id == Product.id)
        query = query.outerjoin(Client, Product.client_id == Client.id)
        query = query.outerjoin(User, Client.user_id == User.id)
        query = join_country_info(query)

    # 权限过滤
    # ---------- 条件分支 ----------
    if not is_admin(current_user):
        query = query.where(Client.user_id == current_user.id)
    # ---------- 条件分支 ----------
    elif client_id:
        query = query.where(Client.id == client_id)

    # 产品状态过滤：只显示激活状态的产品（如果产品存在）
    # 使用 Product.id 判断是否有产品行
    query = query.where(or_(Product.id.is_(None), Product.is_active == True))

    # 过滤条件
    # ---------- 条件分支 ----------
    if safe_strip(product_id):
        # ---------- 异常处理 ----------
        try:
            pid = int(product_id)
            query = query.where(TBSearchData.product_id == pid)
        except ValueError:
            pass

    code = safe_strip(country_code)
    # ---------- 条件分支 ----------
    if code and code != 'ZZ' and len(code) <= 2:
        query = query.where(TBSearchData.country_code == code)

    # 日期范围过滤
    # 如果传递了日期范围，使用传递的日期范围
    # 如果没有传递日期范围，默认显示当前月的数据（与其他端点保持一致）
    # 但前端可以通过传递一个很大的日期范围来显示所有数据
    # ---------- 条件分支 ----------
    if start_date:
        query = query.where(TBSearchData.date >= datetime.combine(start_date, datetime.min.time()))
    # ---------- 条件分支 ----------
    if end_date:
        query = query.where(TBSearchData.date <= datetime.combine(end_date, datetime.max.time()))
    # ---------- 条件分支 ----------
    elif not start_date and not end_date:
        # 如果没有传递日期范围，默认显示当前月的数据
        today = date.today()
        month_start = date(today.year, today.month, 1)
        _, last_day = monthrange(today.year, today.month)
        month_end = date(today.year, today.month, last_day)
        query = query.where(TBSearchData.date >= datetime.combine(month_start, datetime.min.time()))
        query = query.where(TBSearchData.date <= datetime.combine(month_end, datetime.max.time()))

    # 排序
    sort_fields = {
        "date": TBSearchData.date,
        "product_id": TBSearchData.product_id,
        "redirects": TBSearchData.redirects,
        "searches": TBSearchData.searches,
        "monetized": TBSearchData.monetized,
        "clicks": TBSearchData.clicks,
        "revenue": TBSearchData.revenue,
        "rpm": TBSearchData.rpm,
        "revenue_before_deduct": TBSearchData.revenue_before_deduct,
        "rpm_before_deduct": TBSearchData.rpm_before_deduct
    }
    
    sort_col = sort_fields.get(sort_by, TBSearchData.date)
    # ---------- 条件分支 ----------
    if sort_order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    # 计数
    # 简化计数查询，使用LEFT JOIN确保即使关联数据缺失也能正确计数
    count_query = select(func.count(TBSearchData.id))
    count_query = count_query.outerjoin(Product, TBSearchData.product_id == Product.id)
    
    # ---------- 条件分支 ----------
    if use_assignment_table:
        # 使用产品分配历史表
        count_query = count_query.outerjoin(
            ProductAssignment,
            and_(
                ProductAssignment.product_id == Product.id,
                product_assignment_join_condition(
                    TBSearchData.date,
                    ProductAssignment.start_date,
                    ProductAssignment.end_date
                )
            )
        )
        count_query = count_query.outerjoin(Client, ProductAssignment.client_id == Client.id)
    else:
        # 旧的查询方式
        count_query = count_query.outerjoin(Client, Product.client_id == Client.id)
    
    # 应用相同的过滤条件
    # ---------- 条件分支 ----------
    if not is_admin(current_user):
        count_query = count_query.where(Client.user_id == current_user.id)
    # ---------- 条件分支 ----------
    elif client_id:
        count_query = count_query.where(Client.id == client_id)
    
    # 产品状态过滤：只显示激活状态的产品（如果产品存在）
    count_query = count_query.where(or_(Product.id.is_(None), Product.is_active == True))
        
    # ---------- 条件分支 ----------
    if safe_strip(product_id):
        # ---------- 异常处理 ----------
        try:
            pid = int(product_id)
            count_query = count_query.where(TBSearchData.product_id == pid)
        except ValueError:
            pass
            
    code = safe_strip(country_code)
    # ---------- 条件分支 ----------
    if code and code != 'ZZ' and len(code) <= 2:
        count_query = count_query.where(TBSearchData.country_code == code)
            
    # 日期范围过滤（与主查询保持一致）
    # ---------- 条件分支 ----------
    if start_date:
        count_query = count_query.where(TBSearchData.date >= datetime.combine(start_date, datetime.min.time()))
    # ---------- 条件分支 ----------
    if end_date:
        count_query = count_query.where(TBSearchData.date <= datetime.combine(end_date, datetime.max.time()))
    # ---------- 条件分支 ----------
    elif not start_date and not end_date:
        # 如果没有传递日期范围，默认显示当前月的数据
        today = date.today()
        month_start = date(today.year, today.month, 1)
        _, last_day = monthrange(today.year, today.month)
        month_end = date(today.year, today.month, last_day)
        count_query = count_query.where(TBSearchData.date >= datetime.combine(month_start, datetime.min.time()))
        count_query = count_query.where(TBSearchData.date <= datetime.combine(month_end, datetime.max.time()))

    total = (await db.execute(count_query)).scalar() or 0

    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    data = result.unique().all()

    response_list = []
    # ---------- 循环处理 ----------
    for row in data:
        # 根据是否使用产品分配历史表，解包不同的结果
        # ---------- 条件分支 ----------
        if use_assignment_table:
            tb_data, product, client, user, product_assignment, country_info = row
        else:
            tb_data, product, client, user, country_info = row
            product_assignment = None
        
        # 处理可能为None的关联数据
        # 即使产品不存在，也显示数据，但标记为"未知产品"
        # 这样可以发现数据完整性问题
        
        # 使用统一的国家名称解析函数
        country_name = resolve_country_name(
            country_info, 
            tb_data.country_code,
            default_unknown="未知区域",
            default_all="全部区域"
        ) or "未知区域"

        # 处理日期：使用统一的日期键规范化函数
        date_val = normalize_date_key(tb_data.date)

        # 使用统一的名称获取函数
        
        item = TBSearchDataResponse(
            id=tb_data.id,
            date=date_val,
            product_id=product.id if product else tb_data.product_id,  # 使用原始product_id
            product_name=get_product_name(product, tb_data.product_id),
            country_code=tb_data.country_code,
            country_name_zh=country_name,
            redirects=tb_data.redirects,
            searches=tb_data.searches,
            monetized=tb_data.monetized,
            clicks=tb_data.clicks,
            revenue=tb_data.revenue,
            rpm=tb_data.rpm,
            revenue_before_deduct=tb_data.revenue_before_deduct,
            rpm_before_deduct=tb_data.rpm_before_deduct,
            created_at=tb_data.created_at,
            updated_at=tb_data.updated_at,
            client_id=client.id if client else 0,
            client_name=get_client_name(client),
            user_name=get_user_name(user)
        )
        response_list.append(item)

    # ---------- 构建响应 ----------
    return PaginatedResponseBaseSchema.success(
        data=response_list,
        total=total,
        page=page,
        page_size=page_size
    )

@router.post("/import", response_model=ResponseBaseSchema[dict], summary="导入Excel数据")
async def import_tb_search_data(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    从 Excel 批量导入 TB 搜索数据（仅管理员）。

    必需列：DATE、SUBID（产品名）、GEO；可选 REDIRECTS/SEARCHES/MONETIZED/CLICKS/REVENUE/RPM。
    产品不存在时自动创建；同日期+产品+国家已存在则更新；按产品扣量比例计算 revenue/rpm。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 条件分支 ----------
    if not is_admin(current_user):
        raise_api_exception(ErrorCode.PERMISSION_DENIED, detail="仅管理员可导入")

    # 验证文件并读取内容（使用公共验证函数）
    contents = await validate_excel_file(file)
    # ---------- 异常处理 ----------
    try:
        from app.core.excel_io import read_excel_from_bytes
        df = await read_excel_from_bytes(contents)
    except HTTPException:
        raise
    except Exception as e:
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"读取Excel失败: {str(e)}")

    # 列名映射
    # DATE, SUBID, GEO, REDIRECTS, SEARCHES, MONETIZED, CLICKS, REVENUE, RPM
    # 忽略大小写
    df.columns = [str(col).upper().strip() for col in df.columns]
    
    required_cols = ["DATE", "SUBID", "GEO"]
    missing = [col for col in required_cols if col not in df.columns]
    # ---------- 条件分支 ----------
    if missing:
        #raise_api_exception(ErrorCode.INVALID_PARAMS, detail=f"缺少必要列: {', '.join(missing)}")
        return ResponseBaseSchema.success(data={"message": f"导入失败：缺少必要列 {', '.join(missing)}。请检查Excel文件格式。", "errors": [f"缺少必要列: {', '.join(missing)}"]})
        
    success_count = 0
    errors = []
    
    # ---------- 循环处理 ----------
    for index, row in df.iterrows():
        # ---------- 异常处理 ----------
        try:
            # 解析日期：使用统一的日期键规范化函数
            date_val = normalize_date_key(parse_date_value(row["DATE"]))
                
            # 解析产品名称（SUBID）
            product_name = str(row["SUBID"]).strip()
            # ---------- 条件分支 ----------
            if not product_name:
                raise ValueError("SUBID(产品名称)不能为空")
                
            # 根据名称查找产品
            # 注意：如果存在同名产品（不同客户），这里可能会有歧义
            # 这里取第一个匹配的产品
            product_res = await db.execute(select(Product).where(Product.name == product_name))
            product = product_res.scalars().first()
            
            # ---------- 条件分支 ----------
            if not product:
                # 产品不存在，自动创建
                # 1. 查找或创建默认客户：使用统一的辅助函数
                client = await find_or_create_default_client(db, current_user.id)
                
                # 2. 创建新产品
                new_product = Product(
                    client_id=client.id,
                    name=product_name,
                    is_active=True,
                    ecpm_deduct_ratio=0.0,
                    revenue_deduct_ratio=0.0
                )
                db.add(new_product)
                await db.flush() # 获取ID
                product = new_product
            
            subid = product.id
                
            # 解析 GEO：能识别则用标准二字码，否则保留原始值（截断至字段长度）
            geo_raw = str(row["GEO"]).strip() if pd.notna(row.get("GEO")) else ""
            if geo_raw:
                found = await find_country_code_by_any_format(db, geo_raw)
                geo = found if found else preserve_unrecognized_country_code(geo_raw)
            else:
                geo = "ZZ"
            
            # 查找是否已存在
            existing_query = select(TBSearchData).where(
                and_(
                    TBSearchData.date == datetime.combine(date_val, datetime.min.time()),
                    TBSearchData.product_id == subid,
                    TBSearchData.country_code == geo
                )
            )
            existing_res = await db.execute(existing_query)
            existing = existing_res.scalar_one_or_none()
            

            # 解析数值
            redirects = int(row.get("REDIRECTS", 0)) if pd.notna(row.get("REDIRECTS")) else 0
            searches = int(row.get("SEARCHES", 0)) if pd.notna(row.get("SEARCHES")) else 0
            monetized = int(row.get("MONETIZED", 0)) if pd.notna(row.get("MONETIZED")) else 0
            clicks = int(row.get("CLICKS", 0)) if pd.notna(row.get("CLICKS")) else 0
            
            # 原始收入
            revenue_origin = float(row.get("REVENUE", 0.0)) if pd.notna(row.get("REVENUE")) else 0.0

            # RPM：只有在单元格为空/NaN时才按公式计算；如果有值（包括0），则直接使用
            rpm_cell = row.get("RPM", None)
            rpm_origin: float | None = None
            # ---------- 条件分支 ----------
            if rpm_cell is None or (isinstance(rpm_cell, float) and pd.isna(rpm_cell)) or (isinstance(rpm_cell, str) and rpm_cell.strip() == ""):
                rpm_origin = None
            else:
                # ---------- 异常处理 ----------
                try:
                    rpm_origin = float(rpm_cell)
                except Exception:
                    rpm_origin = None

            # ---------- 条件分支 ----------
            if rpm_origin is None and searches > 0:
                rpm_origin = (revenue_origin / searches) * 1000
            # ---------- 条件分支 ----------
            if rpm_origin is None:
                rpm_origin = 0.0
            
            # 获取扣减比例
            revenue_deduct_ratio = product.revenue_deduct_ratio or 0.0
            ecpm_deduct_ratio = product.ecpm_deduct_ratio or 0.0 # RPM 对应 eCPM 扣减比例
            
            # 计算扣减后的值：无扣减保留原始精度，有扣减截断两位小数
            revenue = apply_deduct_ratio(revenue_origin, revenue_deduct_ratio)
            rpm = apply_deduct_ratio(rpm_origin, ecpm_deduct_ratio)
            
            # ---------- 条件分支 ----------
            if existing:
                # 更新
                existing.redirects = redirects
                existing.searches = searches
                existing.monetized = monetized
                existing.clicks = clicks
                existing.revenue = revenue
                existing.rpm = rpm
                existing.revenue_before_deduct = revenue_origin
                existing.rpm_before_deduct = rpm_origin
            else:
                # 创建
                new_data = TBSearchData(
                    date=datetime.combine(date_val, datetime.min.time()),
                    product_id=subid,
                    country_code=geo,
                    redirects=redirects,
                    searches=searches,
                    monetized=monetized,
                    clicks=clicks,
                    revenue=revenue,
                    rpm=rpm,
                    revenue_before_deduct=revenue_origin,
                    rpm_before_deduct=rpm_origin
                )
                db.add(new_data)
                
            success_count += 1
            
        except Exception as e:
            errors.append(f"行 {index+2}: {str(e)}")
            
    # 注意：不需要手动提交事务，get_db 依赖会自动处理
    # 如果发生异常，get_db 会自动回滚
        
    msg = f"成功导入 {success_count} 条数据"
    # ---------- 条件分支 ----------
    if errors:
        msg += f"，{len(errors)} 条失败"

    await log_user_action(
        db=db,
        action_type="IMPORT",
        user=current_user,
        resource_type="TB_SEARCH_DATA",
        request=request,
        success=True,
        details={
            "filename": file.filename,
            "success_count": success_count,
            "error_count": len(errors),
        },
    )

    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data={"message": msg, "errors": errors[:10]}) # 只返回前10个错误

@router.delete("/batch", response_model=ResponseBaseSchema[dict], summary="批量删除TB搜索数据")
async def batch_delete_tb_search_data(
    request: Request,
    data_ids: list[int] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    按 ID 列表批量删除 TB 搜索数据。

    权限：仅管理员。
    """
    if not is_admin(current_user):
        raise_api_exception(ErrorCode.PERMISSION_DENIED, detail="仅管理员可删除")
        
    if not data_ids:
        raise_api_exception(ErrorCode.INVALID_PARAMS, detail="ID列表不能为空")
        
    stmt = delete(TBSearchData).where(TBSearchData.id.in_(data_ids))
    result = await db.execute(stmt)
    deleted_count = int(result.rowcount or 0)

    await log_user_action(
        db=db,
        action_type="DELETE",
        user=current_user,
        resource_type="TB_SEARCH_DATA",
        resource_id=data_ids[0] if len(data_ids) == 1 else 0,
        resource_name=f"批量删除TB搜索数据({deleted_count}条)",
        request=request,
        details={"data_ids": data_ids, "deleted_count": deleted_count},
    )

    return ResponseBaseSchema.success(data={"message": f"成功删除 {deleted_count} 条数据"})

@router.delete("/{data_id}", response_model=ResponseBaseSchema[dict], summary="删除TB搜索数据")
async def delete_tb_search_data(
    request: Request,
    data_id: int = Path(..., ge=1, description="TB搜索数据ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    按主键删除单条 TB 搜索数据记录。

    删除不可恢复；用于纠正错误或清理测试数据。
    权限：仅管理员。
    """
    if not is_admin(current_user):
        raise_api_exception(ErrorCode.PERMISSION_DENIED, detail="仅管理员可删除")

    query = select(TBSearchData).where(TBSearchData.id == data_id)
    result = await db.execute(query)
    tb_data = result.scalar_one_or_none()
    
    if not tb_data:
        raise_api_exception(ErrorCode.NOT_FOUND, detail="数据不存在")
        
    await db.delete(tb_data)

    await log_delete(
        db=db,
        user=current_user,
        resource_type="TB_SEARCH_DATA",
        resource_id=data_id,
        resource_name=f"TB搜索数据-{data_id}",
        request=request,
    )

    return ResponseBaseSchema.success(data={"message": "删除成功"})

@router.post("/{data_id}", response_model=ResponseBaseSchema[TBSearchDataResponse], summary="更新TB搜索数据")
async def update_tb_search_data(
    request: Request,
    data_id: int = Path(..., ge=1, description="TB搜索数据ID"),
    data_update: TBSearchDataUpdate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    更新单条 TB 搜索数据字段。

    权限：仅管理员。
    返回含关联产品、客户信息的完整响应体。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 条件分支 ----------
    if not is_admin(current_user):
        raise_api_exception(ErrorCode.PERMISSION_DENIED, detail="仅管理员可修改")

    query = select(TBSearchData).where(TBSearchData.id == data_id)
    result = await db.execute(query)
    tb_data = result.scalar_one_or_none()
    
    # ---------- 条件分支 ----------
    if not tb_data:
        raise_api_exception(ErrorCode.NOT_FOUND, detail="数据不存在")

    update_dict = data_update.model_dump(exclude_unset=True)
    # ---------- 循环处理 ----------
    for k, v in update_dict.items():
        setattr(tb_data, k, v)

    # ---------- 条件分支 ----------
    if update_dict:
        await log_update(
            db=db,
            user=current_user,
            resource_type="TB_SEARCH_DATA",
            resource_id=data_id,
            resource_name=f"TB搜索数据-{data_id}",
            request=request,
            details={"updated_fields": list(update_dict.keys())},
        )

    # 注意：不需要手动提交事务，get_db 依赖会自动处理
    # 刷新对象以获取最新数据（在自动提交之前）
    await db.flush()
    await db.refresh(tb_data)
    
    # 重新查询以获取关联信息
    query = select(TBSearchData, Product, Client, User, CountryInfo)
    query = query.join(Product, TBSearchData.product_id == Product.id)
    query = query.join(Client, Product.client_id == Client.id)
    query = query.join(User, Client.user_id == User.id)
    query = join_country_info(query)
    query = query.where(TBSearchData.id == data_id)
    
    result = await db.execute(query)
    row = result.unique().first()
    tb_data, product, client, user, country_info = row
    
    # 使用统一的国家名称解析函数
    country_name = resolve_country_name(
        country_info,
        tb_data.country_code,
        default_unknown="未知区域",
        default_all="全部区域"
    ) or "未知区域"

    date_val = normalize_date_key(tb_data.date)

    # 使用统一的名称获取函数
    
    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data=TBSearchDataResponse(
        id=tb_data.id,
        date=date_val,
        product_id=product.id,
        product_name=get_product_name(product),
        country_code=tb_data.country_code,
        country_name_zh=country_name,
        redirects=tb_data.redirects,
        searches=tb_data.searches,
        monetized=tb_data.monetized,
        clicks=tb_data.clicks,
        revenue=tb_data.revenue,
        rpm=tb_data.rpm,
        revenue_before_deduct=tb_data.revenue_before_deduct,
        rpm_before_deduct=tb_data.rpm_before_deduct,
        created_at=tb_data.created_at,
        updated_at=tb_data.updated_at,
        client_id=client.id if client else 0,
        client_name=get_client_name(client),
        user_name=get_user_name(user)
    ))

@router.get("/clients-with-data", response_model=ListResponseBaseSchema[list[dict]], summary="获取有TB搜索数据的客户列表")
async def get_clients_with_tb_search_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
    end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD")
):
    """
    获取有TB搜索数据的客户列表（用于下拉选择）
    - 只返回在指定日期范围内有数据的客户
    - 如果没有指定日期范围，使用当前月作为默认范围
    - 管理员可查看所有有数据的客户
    - 客户只能看到自己
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(db)
        
        # 构建基础查询 - 返回 Client.id 和 User.full_name
        # ---------- 条件分支 ----------
        if use_assignment_table:
            # 使用产品分配历史表
            query = select(func.distinct(Client.id), User.full_name, User.username, Client.user_id)
            query = query.select_from(TBSearchData)
            query = query.join(Product, TBSearchData.product_id == Product.id)
            query = query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    product_assignment_join_condition(
                        TBSearchData.date,
                        ProductAssignment.start_date,
                        ProductAssignment.end_date
                    )
                )
            )
            query = query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            # 旧的查询方式
            query = select(func.distinct(Client.id), User.full_name, User.username, Client.user_id)
            query = query.select_from(Client)
            query = query.join(Product, Product.client_id == Client.id)
            query = query.join(TBSearchData, TBSearchData.product_id == Product.id)
        
        query = query.join(User, Client.user_id == User.id)
        
        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)
        
        # 权限过滤
        # ---------- 条件分支 ----------
        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        
        # 日期范围过滤
        # ---------- 条件分支 ----------
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            query = query.where(TBSearchData.date >= start_datetime)
        # ---------- 条件分支 ----------
        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())
            query = query.where(TBSearchData.date <= end_datetime)
        # 如果没有指定日期范围，默认查询当前月的数据
        # ---------- 条件分支 ----------
        elif not start_date and not end_date:
            today = date.today()
            month_start = date(today.year, today.month, 1)
            _, last_day = monthrange(today.year, today.month)
            month_end = date(today.year, today.month, last_day)
            
            month_start_datetime = datetime.combine(month_start, datetime.min.time())
            month_end_datetime = datetime.combine(month_end, datetime.max.time())
            query = query.where(TBSearchData.date >= month_start_datetime)
            query = query.where(TBSearchData.date <= month_end_datetime)
        
        # 执行查询
        result = await db.execute(query)
        clients_data = result.all()
        
        # 转换为响应格式
        clients_list = []
        # ---------- 循环处理 ----------
        for client_id, full_name, username, user_id in clients_data:
            clients_list.append({
                "id": client_id,
                "full_name": full_name or username or "未知客户",
                "user_id": user_id
            })
        
        # 按用户名称排序
        clients_list.sort(key=lambda x: x["full_name"])
        
        return ListResponseBaseSchema.success(data=clients_list, count=len(clients_list))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取有TB搜索数据的客户列表失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取有数据的客户列表失败：{str(e)}。请稍后重试或联系管理员"
        )

@router.get("/products-with-data", response_model=ListResponseBaseSchema[list[dict]], summary="获取有TB搜索数据的产品列表")
async def get_products_with_tb_search_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    client_id: int | None = Query(None, description="客户ID过滤，None表示全部客户"),
    start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
    end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD")
):
    """
    获取有TB搜索数据的产品列表（用于下拉选择）
    - 分配历史：按数据行日期匹配 ProductAssignment，随日期范围动态变化
    - 客户角色且启用分配表时：并集补充当前 Product.client_id 名下有数据的产品
    - 未指定日期范围时默认当前月；仅返回激活产品
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        use_assignment_table = await check_use_assignment_table(db)

        # 路径 1：分配历史 — 按 TB 数据行日期匹配当时归属（随日期范围动态变化）
        assignment_query = build_products_with_data_base_query()
        assignment_query = join_tb_search_and_client_from_product(
            assignment_query, use_assignment_table
        )
        if not is_admin(current_user):
            assignment_query = assignment_query.where(Client.user_id == current_user.id)
        elif client_id:
            assignment_query = assignment_query.where(Client.id == client_id)

        assignment_query = apply_date_range_filter(
            assignment_query,
            TBSearchData.date,
            start_date,
            end_date,
            default_to_current_month=True,
        )
        assignment_rows = (await db.execute(assignment_query)).all()

        has_dual_path = use_assignment_table and not is_admin(current_user)
        current_rows = None
        if has_dual_path:
            current_query = build_products_with_data_base_query()
            current_query = current_query.join(
                TBSearchData, TBSearchData.product_id == Product.id
            )
            current_query = current_query.join(Client, Product.client_id == Client.id)
            current_query = current_query.where(Client.user_id == current_user.id)
            current_query = apply_date_range_filter(
                current_query,
                TBSearchData.date,
                start_date,
                end_date,
                default_to_current_month=True,
            )
            current_rows = (await db.execute(current_query)).all()

        scope_client_ids = [client_id] if use_assignment_table and is_admin(current_user) and client_id else None

        merged = merge_product_options_with_ownership(
            assignment_rows,
            current_rows,
            scope_client_ids=scope_client_ids,
            has_dual_path=has_dual_path,
        )
        products_list = sorted(merged, key=lambda x: x["name"])
        
        return ListResponseBaseSchema.success(data=products_list, count=len(products_list))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取有TB搜索数据的产品列表失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取有数据的产品列表失败：{str(e)}。请稍后重试或联系管理员"
        )

@router.get("/countries-with-data", response_model=ListResponseBaseSchema[list[dict]], summary="获取有TB搜索数据的国家列表")
async def get_countries_with_tb_search_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    client_id: int | None = Query(None, description="客户ID过滤，None表示全部客户"),
    product_id: int | None = Query(None, description="产品ID过滤，None表示全部产品"),
    start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
    end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD")
):
    """
    获取有TB搜索数据的国家列表（用于下拉选择）
    - 只返回在指定条件下有数据的国家
    - 如果没有指定日期范围，使用当前月作为默认范围
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(db)
        
        # 构建基础查询
        # ---------- 条件分支 ----------
        if use_assignment_table:
            # 使用产品分配历史表
            query = select(func.distinct(TBSearchData.country_code), CountryInfo.country_name_zh)
            query = query.select_from(TBSearchData)
            query = query.join(Product, TBSearchData.product_id == Product.id)
            query = query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    product_assignment_join_condition(
                        TBSearchData.date,
                        ProductAssignment.start_date,
                        ProductAssignment.end_date
                    )
                )
            )
            query = query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            # 旧的查询方式
            query = select(func.distinct(TBSearchData.country_code), CountryInfo.country_name_zh)
            query = query.select_from(TBSearchData)
            query = query.join(Product, TBSearchData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)
        
        query = join_country_info(query)
        
        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)
        
        # 权限过滤
        # ---------- 条件分支 ----------
        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        # ---------- 条件分支 ----------
        elif client_id:
            query = query.where(Client.id == client_id)
        
        # 产品ID过滤
        # ---------- 条件分支 ----------
        if product_id:
            # ---------- 异常处理 ----------
            try:
                pid = int(product_id)
                query = query.where(TBSearchData.product_id == pid)
            except ValueError:
                pass
        
        # 日期范围过滤
        # ---------- 条件分支 ----------
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            query = query.where(TBSearchData.date >= start_datetime)
        # ---------- 条件分支 ----------
        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())
            query = query.where(TBSearchData.date <= end_datetime)
        # 如果没有指定日期范围，默认查询当前月的数据
        # ---------- 条件分支 ----------
        elif not start_date and not end_date:
            today = date.today()
            month_start = date(today.year, today.month, 1)
            _, last_day = monthrange(today.year, today.month)
            month_end = date(today.year, today.month, last_day)
            
            month_start_datetime = datetime.combine(month_start, datetime.min.time())
            month_end_datetime = datetime.combine(month_end, datetime.max.time())
            query = query.where(TBSearchData.date >= month_start_datetime)
            query = query.where(TBSearchData.date <= month_end_datetime)
        
        # 执行查询
        result = await db.execute(query)
        countries_data = result.all()
        
        # 转换为响应格式
        countries_list = []
        # ---------- 循环处理 ----------
        for country_code, country_name_zh in countries_data:
            # ---------- 条件分支 ----------
            if country_code and country_code != 'ZZ':
                display_name = (
                    country_name_zh
                    or resolve_country_name(None, country_code)
                    or country_code
                    or "未知区域"
                )
                countries_list.append({
                    "code": country_code,
                    "name_zh": display_name,
                })
        
        # 去重并排序
        seen = set()
        unique_countries = []
        # ---------- 循环处理 ----------
        for country in countries_list:
            # ---------- 条件分支 ----------
            if country["code"] not in seen:
                seen.add(country["code"])
                unique_countries.append(country)
        
        unique_countries.sort(key=lambda x: x["name_zh"])
        
        return ListResponseBaseSchema.success(data=unique_countries, count=len(unique_countries))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取有TB搜索数据的国家列表失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取有数据的国家列表失败：{str(e)}。请稍后重试或联系管理员"
        )

