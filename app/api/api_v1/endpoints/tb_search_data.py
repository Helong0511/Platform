"""
TB搜索数据管理API端点
"""
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status, UploadFile, File
from sqlalchemy import delete, func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import pandas as pd
from io import BytesIO

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.models.models import TBSearchData, Client, Product, User, UserRole, CountryInfo, ProductAssignment
from app.schemas.tb_search_data import (
    TBSearchDataListResponse,
    TBSearchDataResponse,
    TBSearchDataUpdate,
)
from app.schemas.base import ResponseBaseSchema
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.query_utils import product_assignment_join_condition, check_use_assignment_table
from app.api.api_v1.endpoints.excel.utils import allowed_file, ALLOWED_MIME_TYPES, parse_date_value

router = APIRouter()
logger = logging.getLogger(__name__)

def join_country_info(query):
    return query.outerjoin(
        CountryInfo,
        TBSearchData.country_code.collate('utf8mb4_unicode_ci') == 
        CountryInfo.alpha_2_code.collate('utf8mb4_unicode_ci')
    )

@router.get("/", response_model=ResponseBaseSchema[TBSearchDataListResponse], summary="获取TB搜索数据列表")
async def get_tb_search_data(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
    start_date: date | None = Query(None, description="开始日期"),
    end_date: date | None = Query(None, description="结束日期"),
    client_id: int | None = Query(None, description="客户ID"),
    product_id: str | None = Query(None, description="产品ID"),
    country_code: str | None = Query(None, description="国家代码"),
    sort_by: str = Query("date", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向")
):
    from app.core.utils import optimize_page_size_for_device
    page_size = optimize_page_size_for_device(request, page_size, default_page_size=10)

    # 检查是否使用产品分配历史表
    use_assignment_table = await check_use_assignment_table(db)
    if not settings.is_production:
        if use_assignment_table:
            logger.debug("TB搜索数据：使用产品分配历史表查询")
        else:
            logger.debug("TB搜索数据：使用旧的查询方式（直接通过Product.client_id关联）")

    # 构建查询
    # 使用LEFT JOIN确保即使关联数据缺失也能查询到TB搜索数据
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
    if current_user.role != UserRole.ADMIN:
        query = query.where(Client.user_id == current_user.id)
    elif client_id:
        query = query.where(Client.id == client_id)

    # 产品状态过滤：只显示激活状态的产品（如果产品存在）
    # 注意：使用 outerjoin 时，Product 可能为 None，所以需要检查
    query = query.where(or_(Product.is_(None), Product.is_active == True))

    # 过滤条件
    if product_id and product_id.strip():
        try:
            pid = int(product_id)
            query = query.where(TBSearchData.product_id == pid)
        except ValueError:
            pass

    if country_code and country_code.strip():
        code = country_code.strip()
        if code != 'ZZ' and len(code) <= 2:
            query = query.where(TBSearchData.country_code == code)

    # 日期范围过滤
    # 如果传递了日期范围，使用传递的日期范围
    # 如果没有传递日期范围，默认显示当前月的数据（与其他端点保持一致）
    # 但前端可以通过传递一个很大的日期范围来显示所有数据
    if start_date:
        query = query.where(TBSearchData.date >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.where(TBSearchData.date <= datetime.combine(end_date, datetime.max.time()))
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
    if sort_order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    # 计数
    # 简化计数查询，使用LEFT JOIN确保即使关联数据缺失也能正确计数
    count_query = select(func.count(TBSearchData.id))
    count_query = count_query.outerjoin(Product, TBSearchData.product_id == Product.id)
    
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
    if current_user.role != UserRole.ADMIN:
        count_query = count_query.where(Client.user_id == current_user.id)
    elif client_id:
        count_query = count_query.where(Client.id == client_id)
    
    # 产品状态过滤：只显示激活状态的产品（如果产品存在）
    count_query = count_query.where(or_(Product.is_(None), Product.is_active == True))
        
    if product_id and product_id.strip():
        try:
            pid = int(product_id)
            count_query = count_query.where(TBSearchData.product_id == pid)
        except ValueError:
            pass
            
    if country_code and country_code.strip():
        code = country_code.strip()
        if code != 'ZZ' and len(code) <= 2:
            count_query = count_query.where(TBSearchData.country_code == code)
            
    # 日期范围过滤（与主查询保持一致）
    if start_date:
        count_query = count_query.where(TBSearchData.date >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        count_query = count_query.where(TBSearchData.date <= datetime.combine(end_date, datetime.max.time()))
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
    for row in data:
        # 根据是否使用产品分配历史表，解包不同的结果
        if use_assignment_table:
            tb_data, product, client, user, product_assignment, country_info = row
        else:
            tb_data, product, client, user, country_info = row
            product_assignment = None
        
        # 处理可能为None的关联数据
        # 即使产品不存在，也显示数据，但标记为"未知产品"
        # 这样可以发现数据完整性问题
        
        country_name = "未知区域"
        if country_info:
            country_name = country_info.country_name_zh
        elif tb_data.country_code == "ZZ":
            country_name = "全部区域"

        # 处理日期
        date_val = tb_data.date.date() if isinstance(tb_data.date, datetime) else tb_data.date

        item = TBSearchDataResponse(
            id=tb_data.id,
            date=date_val,
            product_id=product.id if product else tb_data.product_id,  # 使用原始product_id
            product_name=product.name if product else f"未知产品(ID:{tb_data.product_id})",
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
            client_name=client.company_name if client else "未知客户",
            user_name=(user.full_name or user.username) if user else "未知用户"
        )
        response_list.append(item)

    return ResponseBaseSchema.success(data=TBSearchDataListResponse(
        data=response_list,
        total=total,
        page=page,
        page_size=page_size
    ))

@router.post("/import", response_model=ResponseBaseSchema[dict], summary="导入Excel数据")
async def import_tb_search_data(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(ErrorCode.PERMISSION_DENIED, detail="仅管理员可导入")

    if not allowed_file(file.filename):
         raise_api_exception(ErrorCode.INVALID_PARAMS, detail="不支持的文件类型")
         
    contents = await file.read()
    try:
        df = pd.read_excel(BytesIO(contents))
    except Exception as e:
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"读取Excel失败: {str(e)}")

    # 列名映射
    # DATE, SUBID, GEO, REDIRECTS, SEARCHES, MONETIZED, CLICKS, REVENUE, RPM
    # 忽略大小写
    df.columns = [str(col).upper().strip() for col in df.columns]
    
    required_cols = ["DATE", "SUBID", "GEO"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        #raise_api_exception(ErrorCode.INVALID_PARAMS, detail=f"缺少必要列: {', '.join(missing)}")
        return ResponseBaseSchema.success(data={"message": f"导入失败：缺少必要列 {', '.join(missing)}。请检查Excel文件格式。", "errors": [f"缺少必要列: {', '.join(missing)}"]})
        
    success_count = 0
    errors = []
    
    for index, row in df.iterrows():
        try:
            # 解析日期
            date_val = parse_date_value(row["DATE"])
            if isinstance(date_val, datetime):
                date_val = date_val.date()
                
            # 解析产品名称（SUBID）
            product_name = str(row["SUBID"]).strip()
            if not product_name:
                raise ValueError("SUBID(产品名称)不能为空")
                
            # 根据名称查找产品
            # 注意：如果存在同名产品（不同客户），这里可能会有歧义
            # 这里取第一个匹配的产品
            product_res = await db.execute(select(Product).where(Product.name == product_name))
            product = product_res.scalars().first()
            
            if not product:
                # 产品不存在，自动创建
                # 1. 查找或创建默认客户
                default_client_name = "默认客户（导入数据）"
                client_res = await db.execute(select(Client).where(Client.company_name == default_client_name))
                client = client_res.scalars().first()
                
                if not client:
                    # 创建默认客户
                    new_client = Client(
                        user_id=current_user.id,
                        key=str(uuid.uuid4()),
                        company_name=default_client_name,
                        is_active=True,
                        api_enabled=False
                    )
                    db.add(new_client)
                    await db.flush() # 获取ID
                    client = new_client
                
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
                
            # 解析GEO
            geo = str(row["GEO"]).strip()
            # 简单验证GEO
            if len(geo) > 2:
                # 尝试查找对应的二字代码
                # 这里简单处理，如果找不到且长度>2则设为ZZ
                from app.core.country_code import find_country_code_by_any_format
                found = await find_country_code_by_any_format(db, geo)
                if found:
                    geo = found
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
            
            from app.core.utils import truncate_to_2_decimal

            # 解析数值
            redirects = int(row.get("REDIRECTS", 0)) if pd.notna(row.get("REDIRECTS")) else 0
            searches = int(row.get("SEARCHES", 0)) if pd.notna(row.get("SEARCHES")) else 0
            monetized = int(row.get("MONETIZED", 0)) if pd.notna(row.get("MONETIZED")) else 0
            clicks = int(row.get("CLICKS", 0)) if pd.notna(row.get("CLICKS")) else 0
            
            # 原始收入和RPM
            revenue_origin = float(row.get("REVENUE", 0.0)) if pd.notna(row.get("REVENUE")) else 0.0
            rpm_origin = float(row.get("RPM", 0.0)) if pd.notna(row.get("RPM")) else 0.0
            
            # 如果 RPM 没有值，根据公式计算：RPM = REVENUE / SEARCHES * 1000
            if (rpm_origin == 0 or pd.isna(rpm_origin)) and searches > 0:
                rpm_origin = (revenue_origin / searches) * 1000
            
            # 获取扣减比例
            revenue_deduct_ratio = product.revenue_deduct_ratio or 0.0
            ecpm_deduct_ratio = product.ecpm_deduct_ratio or 0.0 # RPM 对应 eCPM 扣减比例
            
            # 计算扣减后的值（保留两位小数）
            revenue = truncate_to_2_decimal(revenue_origin * (1 - revenue_deduct_ratio))
            rpm = truncate_to_2_decimal(rpm_origin * (1 - ecpm_deduct_ratio))
            
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
            
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"保存失败: {str(e)}")
        
    msg = f"成功导入 {success_count} 条数据"
    if errors:
        msg += f"，{len(errors)} 条失败"
        
    return ResponseBaseSchema.success(data={"message": msg, "errors": errors[:10]}) # 只返回前10个错误

@router.delete("/batch", response_model=ResponseBaseSchema[dict], summary="批量删除TB搜索数据")
async def batch_delete_tb_search_data(
    data_ids: list[int] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(ErrorCode.PERMISSION_DENIED, detail="仅管理员可删除")
        
    if not data_ids:
        raise_api_exception(ErrorCode.INVALID_PARAMS, detail="ID列表不能为空")
        
    stmt = delete(TBSearchData).where(TBSearchData.id.in_(data_ids))
    result = await db.execute(stmt)
    await db.commit()
    
    return ResponseBaseSchema.success(data={"message": f"成功删除 {result.rowcount} 条数据"})

@router.delete("/{data_id}", response_model=ResponseBaseSchema[dict], summary="删除TB搜索数据")
async def delete_tb_search_data(
    data_id: int = Path(..., ge=1, description="TB搜索数据ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(ErrorCode.PERMISSION_DENIED, detail="仅管理员可删除")

    query = select(TBSearchData).where(TBSearchData.id == data_id)
    result = await db.execute(query)
    tb_data = result.scalar_one_or_none()
    
    if not tb_data:
        raise_api_exception(ErrorCode.NOT_FOUND, detail="数据不存在")
        
    await db.delete(tb_data)
    await db.commit()
    
    return ResponseBaseSchema.success(data={"message": "删除成功"})

@router.post("/{data_id}", response_model=ResponseBaseSchema[TBSearchDataResponse], summary="更新TB搜索数据")
async def update_tb_search_data(
    data_id: int = Path(..., ge=1, description="TB搜索数据ID"),
    data_update: TBSearchDataUpdate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(ErrorCode.PERMISSION_DENIED, detail="仅管理员可修改")

    query = select(TBSearchData).where(TBSearchData.id == data_id)
    result = await db.execute(query)
    tb_data = result.scalar_one_or_none()
    
    if not tb_data:
        raise_api_exception(ErrorCode.NOT_FOUND, detail="数据不存在")

    update_dict = data_update.model_dump(exclude_unset=True)
    for k, v in update_dict.items():
        setattr(tb_data, k, v)
    
    await db.commit()
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
    
    country_name = "未知区域"
    if country_info:
        country_name = country_info.country_name_zh
    elif tb_data.country_code == "ZZ":
        country_name = "全部区域"

    date_val = tb_data.date.date() if isinstance(tb_data.date, datetime) else tb_data.date

    return ResponseBaseSchema.success(data=TBSearchDataResponse(
        id=tb_data.id,
        date=date_val,
        product_id=product.id,
        product_name=product.name,
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
        client_id=client.id,
        client_name=client.company_name,
        user_name=user.full_name or user.username
    ))

