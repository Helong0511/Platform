"""
广告数据管理API端点
提供广告数据的CRUD操作和统计分析功能，包括：
- 获取广告数据列表（支持分页、过滤、排序）
- 获取广告数据详情
- 更新广告数据（字段白名单验证）
- 获取广告数据汇总统计
- 支持按日期范围、客户ID、产品ID过滤
- 管理员可查看所有数据，客户只能查看自己的数据
"""
# 标准库导入
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any

# 第三方库导入
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy import delete, func, text, literal_column, case, Float
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# 本地导入
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.config import settings
from app.models.models import AdData, Client, Product, User, UserRole, ProductAssignment, CountryInfo
from sqlalchemy import and_, or_
from datetime import date as date_type
from app.core.query_utils import product_assignment_join_condition, check_use_assignment_table
from app.schemas.ad_data import (
    AdDataListResponse,
    AdDataResponse,
    AdDataSummaryResponse,
    AdDataUpdate,
)
from app.schemas.base import PaginatedResponseBaseSchema, ResponseBaseSchema, ListResponseBaseSchema
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


def join_country_info(query):
    """
    辅助函数：统一处理 CountryInfo 的 JOIN，解决排序规则冲突问题
    临时方案：使用 COLLATE 统一排序规则
    永久方案：运行 scripts/fix_collation_issue.sql 修改表结构
    """
    # 使用列对象的 collate() 方法统一排序规则
    # 这样可以确保 SQLAlchemy 正确处理表别名和列引用
    return query.outerjoin(
        CountryInfo,
        AdData.country_code.collate('utf8mb4_unicode_ci') == 
        CountryInfo.alpha_2_code.collate('utf8mb4_unicode_ci')
    )


@router.get("/", response_model=ResponseBaseSchema[AdDataListResponse], summary="获取广告数据列表")
async def get_ad_data(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=100, description="每页条数"),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD"),
        client_id: int | None = Query(None, description="客户ID过滤"),
        product_id: str | None = Query(None, description="产品ID过滤"),
        country_code: str | None = Query(None, description="国家代码过滤（如：US、CN、ZZ表示全部区域）"),
        sort_by: str = Query("date", description="排序字段，默认为date"),
        sort_order: str = Query("desc", description="排序方向，asc或desc")
):
    """
    获取广告数据列表，支持分页、过滤和排序
    - 管理员可查看所有广告数据
    - 客户只能查看自己的广告数据
    - 支持按日期范围、客户ID和产品ID过滤
    - 支持按不同字段排序
    - 移动端自动优化分页大小
    """
    # ====== 设备类型优化：自动调整分页大小 ======
    from app.core.utils import optimize_page_size_for_device
    page_size = optimize_page_size_for_device(request, page_size, default_page_size=10)

    # ====== 构建查询基础 ======
    # 使用JOIN查询关联的产品、客户和用户信息，避免N+1查询问题
    # 注意：由于allowed_ips字段可能还未迁移，使用load_only避免选择该字段
    from sqlalchemy.orm import load_only
    from sqlalchemy import cast, Date
    
    # 检查product_assignments表是否存在且有数据，如果不存在或没有数据则使用旧的查询方式
    use_assignment_table = await check_use_assignment_table(db)
    if not settings.is_production:
        if use_assignment_table:
            logger.debug("使用产品分配历史表查询")
        else:
            logger.debug("使用旧的查询方式（直接通过Product.client_id关联）")
    
    if use_assignment_table:
        # 使用产品分配历史表进行查询
        query = select(AdData, Product, Client, User, ProductAssignment, CountryInfo)
        # 只加载Client需要的字段，排除allowed_ips（如果字段不存在会导致错误）
        query = query.options(load_only(
            Client.id, Client.user_id, Client.company_name, Client.contact_person,
            Client.phone, Client.address, Client.is_active, Client.created_at, Client.updated_at
        ))
        query = query.join(Product, AdData.product_id == Product.id)  # 关联产品
        # 关联产品分配历史表：根据广告数据的日期匹配正确的分配记录
        # 优化：避免在 AdData.date 列上使用 func.date()，改为直接比较 DATE 和 DATETIME
        # MySQL 会自动将 DATE 转换为 DATETIME（时间部分为 00:00:00）进行比较
        # 条件：AdData.date >= start_date AND (end_date IS NULL OR AdData.date < end_date + 1 DAY)
        # 注意：
        # 1. 使用 < end_date + 1 DAY 确保日期连续覆盖，避免日期间隙
        # 2. 由于日期不重叠（旧记录end_date = X，新记录start_date = X+1），每个日期只会匹配一条记录
        # 3. 重叠检查在 transfer_product_assignment 和 create_product_assignment 中完成，确保不会有重复占用时间
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
        query = query.join(Client, ProductAssignment.client_id == Client.id)  # 通过分配历史关联客户
        query = query.join(User, Client.user_id == User.id)  # 关联用户
        query = join_country_info(query)  # 左关联国家信息（已处理排序规则冲突）
    else:
        # 旧的查询方式：直接通过Product.client_id关联
        query = select(AdData, Product, Client, User, CountryInfo)
        # 只加载Client需要的字段，排除allowed_ips（如果字段不存在会导致错误）
        query = query.options(load_only(
            Client.id, Client.user_id, Client.company_name, Client.contact_person,
            Client.phone, Client.address, Client.is_active, Client.created_at, Client.updated_at
        ))
        query = query.join(Product, AdData.product_id == Product.id)  # 关联产品
        query = query.join(Client, Product.client_id == Client.id)  # 关联客户
        query = query.join(User, Client.user_id == User.id)  # 关联用户
        query = join_country_info(query)  # 左关联国家信息（已处理排序规则冲突）

    # 记录查询日志（仅在开发环境）
    if not settings.is_production:
        logger.debug(f"查询广告数据: 用户={current_user.username}, 页码={page}, 每页={page_size}")

    # ====== 权限过滤 ======
    # 根据用户角色设置权限过滤（数据隔离）
    if current_user.role != UserRole.ADMIN:
        # 客户只能查看自己的广告数据（基于产品分配历史）
        # 通过ProductAssignment匹配的Client.user_id来过滤
        query = query.where(Client.user_id == current_user.id)
    else:
        # 管理员可按客户ID过滤（可选）
        if client_id:
            query = query.where(Client.id == client_id)

    # ====== 产品状态过滤 ======
    # 只显示激活状态的产品（is_active = True）
    query = query.where(Product.is_active == True)

    # ====== 产品ID过滤 ======
    # 处理产品ID参数，允许空字符串并转换为整数（容错处理）
    if product_id and product_id.strip():
        try:
            product_id_int = int(product_id)
            query = query.where(AdData.product_id == product_id_int)
        except ValueError:
            # 忽略无效的产品ID（不抛出异常，继续查询）
            logger.warning(f"无效的产品ID参数: {product_id}")

    # ====== 国家代码过滤 ======
    if country_code and country_code.strip():
        country_code_clean = country_code.strip()
        # 如果传入 'ZZ' 或空字符串，不进行过滤（显示所有国家）
        # 验证国家代码长度（ISO 3166-1 二字母代码最多2个字符）
        if country_code_clean and country_code_clean != 'ZZ' and len(country_code_clean) <= 2:
            query = query.where(AdData.country_code == country_code_clean)
        elif country_code_clean and len(country_code_clean) > 2:
            # 国家代码长度超过2个字符，记录警告但不报错（可能是三字母代码或其他格式）
            logger.warning(f"国家代码长度超过2个字符: {country_code_clean}，将忽略此过滤条件")

    # ====== 日期范围过滤 ======
    # 注意：AdData.date 是 DateTime 类型，需要转换为 datetime 进行比较
    if start_date:
        # 将 date 转换为 datetime 的开始时间（00:00:00）进行比较
        start_datetime = datetime.combine(start_date, datetime.min.time())
        query = query.where(AdData.date >= start_datetime)
    if end_date:
        # 将 date 转换为 datetime 的结束时间（23:59:59）进行比较
        end_datetime = datetime.combine(end_date, datetime.max.time())
        query = query.where(AdData.date <= end_datetime)
    # 如果没有指定日期范围，默认查询当前月的数据（提高用户体验）
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

    # 验证排序字段并设置排序
    # 支持按日期、客户、产品以及广告数据字段排序
    valid_sort_fields = {
        "date": AdData.date,  # 日期
        "client": Client.company_name,  # 客户（按公司名称）
        "client_id": Client.id,  # 客户ID
        "product": Product.name,  # 产品（按产品名称）
        "product_id": Product.id,  # 产品ID
        "request_count": AdData.request_count,
        "match_count": AdData.match_count,
        "display_count": AdData.display_count,
        "click_count": AdData.click_count,
        "cpc": AdData.cpc,
        "pageviews": AdData.pageviews,
        "ecpm_after_deduct": AdData.ecpm_after_deduct,
        "ecpm_before_deduct": AdData.ecpm_before_deduct,
        "revenue_after_deduct": AdData.revenue_after_deduct,
        "revenue_before_deduct": AdData.revenue_before_deduct,
        "coverage_rate": AdData.coverage_rate,  # 覆盖率（数据库字段）
        "display_rate": AdData.display_rate,   # 展示率（数据库字段）
        "click_rate": AdData.click_rate,       # 点击率（数据库字段）
        "viewability_rate": AdData.viewability_rate  # 可见率（数据库字段）
    }
    
    # 默认排序字段
    if sort_by not in valid_sort_fields:
        sort_by = "date"
    
    # 获取排序字段
    sort_column = valid_sort_fields[sort_by]
    
    # 设置排序方向
    if sort_order.lower() == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # 计算偏移量
    offset = (page - 1) * page_size

    # 执行查询获取总数和分页数据
    # 优化：使用更高效的计数查询，减少不必要的JOIN
    try:

        # 构建过滤条件列表（复用主查询的逻辑）
        filter_conditions = []

        # 权限过滤
        if current_user.role != UserRole.ADMIN:
            filter_conditions.append(Client.user_id == current_user.id)
        elif client_id:
            filter_conditions.append(Client.id == client_id)

        # 产品状态过滤
        filter_conditions.append(Product.is_active == True)

        # 产品ID过滤
        if product_id and product_id.strip():
            try:
                product_id_int = int(product_id)
                filter_conditions.append(AdData.product_id == product_id_int)
            except ValueError:
                pass

        # 日期范围过滤
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            filter_conditions.append(AdData.date >= start_datetime)
        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())
            filter_conditions.append(AdData.date <= end_datetime)
        elif not start_date and not end_date:
            today = date.today()
            month_start = date(today.year, today.month, 1)
            _, last_day = monthrange(today.year, today.month)
            month_end = date(today.year, today.month, last_day)
            month_start_datetime = datetime.combine(month_start, datetime.min.time())
            month_end_datetime = datetime.combine(month_end, datetime.max.time())
            filter_conditions.append(AdData.date >= month_start_datetime)
            filter_conditions.append(AdData.date <= month_end_datetime)

        # 优化：计数查询不需要JOIN User表，减少JOIN数量
        count_query = select(func.count(AdData.id))
        count_query = count_query.join(Product, AdData.product_id == Product.id)
        if use_assignment_table:
            # 使用产品分配历史表（优化：避免在 AdData.date 上使用 func.date()）
            count_query = count_query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    product_assignment_join_condition(
                        AdData.date,
                        ProductAssignment.start_date,
                        ProductAssignment.end_date
                    )
                )
            )
            count_query = count_query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            # 旧的查询方式
            count_query = count_query.join(Client, Product.client_id == Client.id)

        # 应用所有过滤条件
        if filter_conditions:
            count_query = count_query.where(and_(*filter_conditions))

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0
    except Exception as e:
        logger.error(f"计算广告数据总数失败: {str(e)}")
        total = 0

    # 获取分页数据
    result = await db.execute(query.offset(offset).limit(page_size))
    data = result.unique().all()

    # 记录查询日志（仅在开发环境或数据为空时）
    if not settings.is_production:
        logger.debug(f"查询广告数据: 用户={current_user.username}, 总数={total}, 当前页数据量={len(data)}")
    if len(data) == 0:
        logger.debug(
            f"未查询到数据: page={page}, page_size={page_size}, start_date={start_date}, end_date={end_date}, product_id={product_id}")

    # 转换为响应模型
    ad_data_responses = []
    for row in data:
        try:
            # 根据是否使用ProductAssignment表，解构数据
            if use_assignment_table:
                # 使用ProductAssignment表时，返回6个对象（包含CountryInfo）
                if len(row) >= 6:
                    ad_data, product, client, user, assignment, country_info = row
                elif len(row) >= 5:
                    # 兼容旧数据（没有CountryInfo）
                    ad_data, product, client, user, assignment = row
                    country_info = None
                else:
                    # 如果数据不完整，跳过这条记录
                    logger.warning(f"数据不完整，跳过记录: {row}")
                    continue
            else:
                # 不使用ProductAssignment表时，返回5个对象（包含CountryInfo）
                if len(row) >= 5:
                    ad_data, product, client, user, country_info = row
                elif len(row) >= 4:
                    # 兼容旧数据（没有CountryInfo）
                    ad_data, product, client, user = row
                    country_info = None
                else:
                    logger.warning(f"数据不完整，跳过记录: {row}")
                    continue
        except Exception as e:
            logger.error(f"解构数据失败: {str(e)}, row={row}")
            continue
        # 使用数据库字段中的比率（如果为空则计算）
        coverage_rate = ad_data.coverage_rate if ad_data.coverage_rate is not None else round(
            (ad_data.match_count / ad_data.request_count * 100) if ad_data.request_count > 0 else 0.0,
            2
        )
        display_rate = ad_data.display_rate if ad_data.display_rate is not None else round(
            (ad_data.display_count / ad_data.match_count * 100) if ad_data.match_count > 0 else 0.0,
            2
        )
        click_rate = ad_data.click_rate if ad_data.click_rate is not None else round(
            (ad_data.click_count / ad_data.display_count * 100) if ad_data.display_count > 0 else 0.0,
            2
        )
        viewability_rate = ad_data.viewability_rate if ad_data.viewability_rate is not None else 0.0

        # 根据用户角色决定返回哪些字段
        # 将 DateTime 转换为 date
        date_value = ad_data.date
        if isinstance(date_value, datetime):
            date_value = date_value.date()
        elif hasattr(date_value, 'date'):
            date_value = date_value.date()

        # 获取国家名称：如果通过JOIN找到了国家信息，使用它；否则根据country_code回退
        if country_info:
            country_name_zh = country_info.country_name_zh
        elif ad_data.country_code == "AA":
            country_name_zh = "未知区域"
        elif ad_data.country_code == "ZZ":
            country_name_zh = "全部区域"
        else:
            country_name_zh = None

        response_data = {
            "id": ad_data.id,
            "date": date_value,
            "product_id": product.id,
            "product_name": product.name,
            "country_code": ad_data.country_code,
            "country_name_zh": country_name_zh,
            "request_count": ad_data.request_count,
            "match_count": ad_data.match_count,
            "coverage_rate": coverage_rate,
            "display_count": ad_data.display_count,
            "display_rate": display_rate,
            "click_count": ad_data.click_count,
            "click_rate": click_rate,
            "viewability_rate": round(viewability_rate, 2),
            "cpc": round(ad_data.cpc or 0.0, 2),
            "pageviews": ad_data.pageviews or 0,
            "ecpm_after_deduct": round(ad_data.ecpm_after_deduct, 4),
            "revenue_after_deduct": round(ad_data.revenue_after_deduct, 4)
        }

        # 管理员额外返回未减扣数据和客户信息
        if current_user.role == UserRole.ADMIN:
            response_data.update({
                "client_id": client.id,
                "client_name": client.company_name,
                "user_name": user.full_name or user.username,  # 添加用户名称
                "ecpm_before_deduct": round(ad_data.ecpm_before_deduct, 4),
                "revenue_before_deduct": round(ad_data.revenue_before_deduct, 4)
            })

        ad_data_responses.append(AdDataResponse(**response_data))

    return ResponseBaseSchema.success(data=AdDataListResponse(
        data=ad_data_responses,
        total=total,
        page=page,
        page_size=page_size
    ))


@router.get("/clients-with-data", response_model=ListResponseBaseSchema[list[dict]], summary="获取有数据的客户列表")
async def get_clients_with_data(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD")
):
    """
    获取有广告数据的客户列表（用于下拉选择）
    - 只返回在指定日期范围内有数据的客户
    - 如果没有指定日期范围，使用当前月作为默认范围
    - 管理员可查看所有有数据的客户
    - 客户只能看到自己
    - 使用缓存提升性能（缓存 5 分钟）
    """
    try:
        # ====== 缓存优化 ======
        from app.core.cache import get_cached, set_cached, generate_cache_key
        cache_key = generate_cache_key("clients_with_data", current_user.id, start_date, end_date)
        cached = await get_cached(cache_key)
        if cached:
            logger.debug(f"缓存命中: clients_with_data, user={current_user.id}")
            return ListResponseBaseSchema.success(data=cached.get("data", []), count=cached.get("count", 0))
        
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(db)
        
        # 构建基础查询 - 返回 Client.id 和 User.full_name
        if use_assignment_table:
            # 使用产品分配历史表：从AdData开始，明确指定FROM子句
            query = select(func.distinct(Client.id), User.full_name, User.username, Client.user_id)
            query = query.select_from(AdData)
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    product_assignment_join_condition(
                        AdData.date,
                        ProductAssignment.start_date,
                        ProductAssignment.end_date
                    )
                )
            )
            query = query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            # 旧的查询方式：从Client开始
            query = select(func.distinct(Client.id), User.full_name, User.username, Client.user_id)
            query = query.select_from(Client)
            query = query.join(Product, Product.client_id == Client.id)
            query = query.join(AdData, AdData.product_id == Product.id)
        
        query = query.join(User, Client.user_id == User.id)

        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)

        # 权限过滤
        if current_user.role != UserRole.ADMIN:
            query = query.where(Client.user_id == current_user.id)

        # 日期范围过滤
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            query = query.where(AdData.date >= start_datetime)
        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())
            query = query.where(AdData.date <= end_datetime)
        # 如果没有指定日期范围，默认查询当前月的数据
        elif not start_date and not end_date:
            today = date.today()
            month_start = date(today.year, today.month, 1)
            _, last_day = monthrange(today.year, today.month)
            month_end = date(today.year, today.month, last_day)

            month_start_datetime = datetime.combine(month_start, datetime.min.time())
            month_end_datetime = datetime.combine(month_end, datetime.max.time())
            query = query.where(AdData.date >= month_start_datetime)
            query = query.where(AdData.date <= month_end_datetime)

        # 执行查询
        result = await db.execute(query)
        clients_data = result.all()

        # 转换为响应格式 - 使用 full_name，如果没有则使用 username
        clients_list = []
        for client_id, full_name, username, user_id in clients_data:
            clients_list.append({
                "id": client_id,
                "full_name": full_name or username or "未知客户",
                "user_id": user_id
            })

        # 按用户名称排序
        clients_list.sort(key=lambda x: x["full_name"])

        # 缓存结果（缓存 5 分钟）
        await set_cached(cache_key, {"data": clients_list, "count": len(clients_list)}, ttl=300)

        return ListResponseBaseSchema.success(data=clients_list, count=len(clients_list))
    except Exception as e:
        logger.error(f"获取有数据的客户列表失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取有数据的客户列表失败：{str(e)}。请稍后重试或联系管理员"
        )


@router.get("/countries-with-data", response_model=ListResponseBaseSchema[list[dict]], summary="获取有数据的国家列表")
async def get_countries_with_data(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        client_id: int | None = Query(None, description="客户ID过滤，None表示全部客户"),
        product_id: int | None = Query(None, description="产品ID过滤，None表示全部产品"),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD")
):
    """
    获取有广告数据的国家列表（用于下拉选择）
    - 只返回在指定条件下有数据的国家
    - 如果没有指定日期范围，使用当前月作为默认范围
    - 管理员可查看所有有数据的国家
    - 客户只能看到自己数据中的国家
    """
    try:
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(db)
        
        # 构建基础查询 - 返回 distinct 的 country_code
        if use_assignment_table:
            query = select(func.distinct(AdData.country_code), CountryInfo.country_name_zh)
            query = query.select_from(AdData)
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    product_assignment_join_condition(
                        AdData.date,
                        ProductAssignment.start_date,
                        ProductAssignment.end_date
                    )
                )
            )
            query = query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            query = select(func.distinct(AdData.country_code), CountryInfo.country_name_zh)
            query = query.select_from(AdData)
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)
        
        query = join_country_info(query)  # 左关联国家信息（已处理排序规则冲突）
        
        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)

        # 权限过滤
        if current_user.role != UserRole.ADMIN:
            query = query.where(Client.user_id == current_user.id)
        else:
            if client_id:
                query = query.where(Client.id == client_id)

        # 产品ID过滤
        if product_id:
            query = query.where(AdData.product_id == product_id)

        # 日期范围过滤
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            query = query.where(AdData.date >= start_datetime)
        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())
            query = query.where(AdData.date <= end_datetime)
        elif not start_date and not end_date:
            today = date.today()
            month_start = date(today.year, today.month, 1)
            _, last_day = monthrange(today.year, today.month)
            month_end = date(today.year, today.month, last_day)

            month_start_datetime = datetime.combine(month_start, datetime.min.time())
            month_end_datetime = datetime.combine(month_end, datetime.max.time())
            query = query.where(AdData.date >= month_start_datetime)
            query = query.where(AdData.date <= month_end_datetime)

        # 过滤掉空的国家代码（使用 and_ 组合条件，更高效）
        query = query.where(
            and_(
                AdData.country_code.isnot(None),
                AdData.country_code != ''
            )
        )

        # 执行查询
        result = await db.execute(query)
        countries_data = result.all()

        # 转换为响应格式
        countries_list = []
        for country_code, country_name_zh in countries_data:
            if not country_code:
                continue
            
            # 处理特殊国家代码
            if country_code == 'ZZ':
                display_name = '全部区域'
            elif country_code == 'AA':
                display_name = '未知区域'
            else:
                display_name = country_name_zh or country_code
            
            countries_list.append({
                "code": country_code,
                "name_zh": display_name
            })

        # 按国家名称排序
        countries_list.sort(key=lambda x: x["name_zh"])

        return ListResponseBaseSchema.success(data=countries_list, count=len(countries_list))
    except Exception as e:
        logger.error(f"获取有数据的国家列表失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取有数据的国家列表失败：{str(e)}。请稍后重试或联系管理员"
        )


@router.get("/products-with-data", response_model=ListResponseBaseSchema[list[dict]], summary="获取有数据的产品列表")
async def get_products_with_data(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        client_id: int | None = Query(None, description="客户ID过滤，None表示全部客户"),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD")
):
    """
    获取有广告数据的产品列表（用于下拉选择）
    
    筛选逻辑：
    1. 默认显示本月数据：
       - client_id=None（全部客户）→ 返回本月全部产品
       - client_id=具体值（特定客户）→ 返回该客户本月全部产品
    
    2. 选择了日期范围：
       - client_id=None（全部客户）→ 返回该日期范围全部产品
       - client_id=具体值（特定客户）→ 返回该客户该日期范围全部产品
    
    其他规则：
    - 只返回在指定日期范围内有数据的产品
    - 如果没有指定日期范围，使用当前月作为默认范围
    - 只返回激活状态的产品
    - 使用产品分配历史表时，会根据日期匹配正确的客户归属
    - 产品列表按名称排序
    - 使用缓存提升性能（缓存 5 分钟）
    """
    try:
        # ====== 缓存优化 ======
        from app.core.cache import get_cached, set_cached, generate_cache_key
        cache_key = generate_cache_key("products_with_data", current_user.id, client_id, start_date, end_date)
        cached = await get_cached(cache_key)
        if cached:
            logger.debug(f"缓存命中: products_with_data, user={current_user.id}")
            return ListResponseBaseSchema.success(data=cached.get("data", []), count=cached.get("count", 0))
        
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(db)
        
        # 构建基础查询
        if use_assignment_table:
            # 使用产品分配历史表
            query = select(func.distinct(Product.id), Product.name, Product.client_id)
            query = query.join(AdData, AdData.product_id == Product.id)
            # 关联产品分配历史表：根据广告数据的日期匹配正确的分配记录（优化：避免在 AdData.date 上使用 func.date()）
            query = query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    product_assignment_join_condition(
                        AdData.date,
                        ProductAssignment.start_date,
                        ProductAssignment.end_date
                    )
                )
            )
            query = query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            # 旧的查询方式
            query = select(func.distinct(Product.id), Product.name, Product.client_id)
            query = query.join(Client, Product.client_id == Client.id)
            query = query.join(AdData, AdData.product_id == Product.id)

        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)

        # 权限过滤
        if current_user.role != UserRole.ADMIN:
            # 客户用户：通过 Client.user_id 过滤，只能看到自己的产品
            query = query.where(Client.user_id == current_user.id)
        elif client_id:
            # 管理员按客户ID过滤：如果指定了客户，只返回该客户的产品
            # 如果 client_id=None，返回所有客户的产品
            query = query.where(Client.id == client_id)

        # 日期范围过滤
        if start_date:
            # 如果指定了开始日期，使用指定的日期范围
            start_datetime = datetime.combine(start_date, datetime.min.time())
            query = query.where(AdData.date >= start_datetime)
        if end_date:
            # 如果指定了结束日期，使用指定的日期范围
            end_datetime = datetime.combine(end_date, datetime.max.time())
            query = query.where(AdData.date <= end_datetime)
        # 如果没有指定日期范围，默认查询当前月的数据
        elif not start_date and not end_date:
            today = date.today()
            month_start = date(today.year, today.month, 1)
            _, last_day = monthrange(today.year, today.month)
            month_end = date(today.year, today.month, last_day)

            month_start_datetime = datetime.combine(month_start, datetime.min.time())
            month_end_datetime = datetime.combine(month_end, datetime.max.time())
            query = query.where(AdData.date >= month_start_datetime)
            query = query.where(AdData.date <= month_end_datetime)

        # 执行查询
        result = await db.execute(query)
        products_data = result.all()

        # 转换为响应格式
        products_list = []
        for product_id, product_name, product_client_id in products_data:
            products_list.append({
                "id": product_id,
                "name": product_name or "未知产品",
                "client_id": product_client_id
            })

        # 按产品 id 倒序排序（从大到小）
        products_list.sort(key=lambda x: x["id"], reverse=True)

        # 缓存结果（缓存 5 分钟）
        await set_cached(cache_key, {"data": products_list, "count": len(products_list)}, ttl=300)

        return ListResponseBaseSchema.success(data=products_list, count=len(products_list))
    except Exception as e:
        logger.error(f"获取有数据的产品列表失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取有数据的产品列表失败：{str(e)}。请稍后重试或联系管理员"
        )


@router.get("/daily-summary", response_model=ResponseBaseSchema[AdDataListResponse], summary="获取每日汇总数据")
async def get_daily_summary(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=100, description="每页条数"),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD"),
        client_id: int | None = Query(None, description="客户ID过滤"),
        product_id: str | None = Query(None, description="产品ID过滤"),
        sort_by: str = Query("date", description="排序字段，默认为date"),
        sort_order: str = Query("desc", description="排序方向，asc或desc")
):
    """
    获取每日汇总数据（按产品+日期汇总，国家显示"全部区域"）
    - 按产品ID和日期分组汇总
    - 国家统一显示"全部区域"
    - 支持分页、过滤和排序
    - 管理员可查看所有数据，客户只能查看自己的数据
    """
    # ====== 设备类型优化：自动调整分页大小 ======
    from app.core.utils import optimize_page_size_for_device
    page_size = optimize_page_size_for_device(request, page_size, default_page_size=10)

    # ====== 构建汇总查询 ======
    use_assignment_table = await check_use_assignment_table(db)
    
    # 调试：记录使用的查询方式
    if not settings.is_production:
        logger.debug(f"每日汇总查询：使用分配历史表={use_assignment_table}, 用户={current_user.username}, 角色={current_user.role}")
    
    # 构建汇总查询：按产品+日期分组
    # 注意：覆盖率、展示率、点击率、eCPM 不在查询中计算，而是在返回数据时根据汇总后的数值重新计算
    query = select(
        func.date(AdData.date).label("date"),
        Product.id.label("product_id"),
        Product.name.label("product_name"),
        Client.id.label("client_id"),
        Client.company_name.label("client_name"),
        User.full_name.label("user_full_name"),
        User.username.label("user_username"),
        func.sum(AdData.request_count).label("request_count"),
        func.sum(AdData.match_count).label("match_count"),
        func.sum(AdData.display_count).label("display_count"),
        func.sum(AdData.click_count).label("click_count"),
        func.avg(AdData.viewability_rate).label("viewability_rate"),
        func.sum(AdData.cpc).label("cpc"),
        func.sum(AdData.pageviews).label("pageviews"),
        func.sum(AdData.revenue_after_deduct).label("revenue_after_deduct"),
        func.sum(AdData.revenue_before_deduct).label("revenue_before_deduct")
    ).join(
        Product, AdData.product_id == Product.id
    )
    
    # 只显示激活状态的产品
    query = query.where(Product.is_active == True)
    
    if use_assignment_table:
        # 使用产品分配历史表
        end_date_with_default = func.coalesce(
            func.date_add(ProductAssignment.end_date, text("INTERVAL 1 DAY")),
            literal_column("'2099-12-31'")
        )
        query = query.join(
            ProductAssignment,
            and_(
                ProductAssignment.product_id == Product.id,
                AdData.date >= ProductAssignment.start_date,
                AdData.date < end_date_with_default
            )
        )
        query = query.join(Client, ProductAssignment.client_id == Client.id)
    else:
        # 旧的查询方式
        query = query.join(Client, Product.client_id == Client.id)
    query = query.join(User, Client.user_id == User.id)
    
    # ====== 权限过滤 ======
    if current_user.role != UserRole.ADMIN:
        query = query.where(Client.user_id == current_user.id)
    else:
        if client_id:
            query = query.where(Client.id == client_id)
    
    # ====== 产品ID过滤 ======
    if product_id and product_id.strip():
        try:
            product_id_int = int(product_id)
            query = query.where(AdData.product_id == product_id_int)
        except ValueError:
            logger.warning(f"无效的产品ID参数: {product_id}")
    
    # ====== 日期范围过滤 ======
    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time())
        query = query.where(AdData.date >= start_datetime)
    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time())
        query = query.where(AdData.date <= end_datetime)
    elif not start_date and not end_date:
        today = date.today()
        month_start = date(today.year, today.month, 1)
        _, last_day = monthrange(today.year, today.month)
        month_end = date(today.year, today.month, last_day)
        month_start_datetime = datetime.combine(month_start, datetime.min.time())
        month_end_datetime = datetime.combine(month_end, datetime.max.time())
        query = query.where(AdData.date >= month_start_datetime)
        query = query.where(AdData.date <= month_end_datetime)
    
    # ====== 分组和排序 ======
    query = query.group_by(
        func.date(AdData.date),
        Product.id,
        Product.name,
        Client.id,
        Client.company_name,
        User.full_name,
        User.username
    )
    
    # 验证排序字段
    # 注意：覆盖率、展示率、点击率、eCPM等计算字段无法在SQL中直接排序
    # 这些字段需要在获取数据后在前端或内存中排序
    # 对于可以在SQL中排序的字段，使用SQL排序；对于计算字段，标记为需要内存排序
    valid_sort_fields = {
        "date": func.date(AdData.date),
        "product": Product.name,
        "product_id": Product.id,
        "request_count": func.sum(AdData.request_count),
        "match_count": func.sum(AdData.match_count),
        "display_count": func.sum(AdData.display_count),
        "click_count": func.sum(AdData.click_count),
        "cpc": func.sum(AdData.cpc),
        "pageviews": func.sum(AdData.pageviews),
        "coverage_rate": func.avg(AdData.coverage_rate),  # 使用平均值作为排序依据
        "display_rate": func.avg(AdData.display_rate),
        "click_rate": func.avg(AdData.click_rate),
        "viewability_rate": func.avg(AdData.viewability_rate),
        "ecpm_after_deduct": func.sum(AdData.revenue_after_deduct),  # 使用收益排序作为eCPM的近似排序
        "revenue_after_deduct": func.sum(AdData.revenue_after_deduct),
        "revenue_before_deduct": func.sum(AdData.revenue_before_deduct)
    }
    
    # 需要内存排序的字段（计算字段，无法在SQL中直接排序）
    memory_sort_fields = {
        "ecpm_before_deduct"  # 扣减前eCPM = 扣减前收益 / 展示数 * 1000（每日汇总时需要计算）
    }
    
    # 判断是否需要内存排序
    need_memory_sort = sort_by in memory_sort_fields
    
    # 如果排序字段在SQL可排序列表中，使用SQL排序
    if sort_by in valid_sort_fields:
        sort_column = valid_sort_fields[sort_by]
        if sort_order.lower() == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
    elif not need_memory_sort:
        # 无效的排序字段，使用默认排序
        sort_by = "date"
        sort_column = valid_sort_fields[sort_by]
        if sort_order.lower() == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
    # 如果是需要内存排序的字段，先不排序，后面在内存中排序
    
    # ====== 计算总数 ======
    # 如果需要在内存中排序，总数会在排序后计算
    # 否则使用SQL计算总数
    if not need_memory_sort:
        try:
            # 优化：使用子查询优化计数，避免复杂的DISTINCT CONCAT操作
            # 先获取满足条件的所有(date, product_id)组合，然后计数
            subquery = select(
                func.date(AdData.date).label("date"),
                Product.id.label("product_id")
            ).select_from(AdData)
            subquery = subquery.join(Product, AdData.product_id == Product.id)
            subquery = subquery.where(Product.is_active == True)
            
            if use_assignment_table:
                end_date_with_default = func.coalesce(
                    func.date_add(ProductAssignment.end_date, text("INTERVAL 1 DAY")),
                    literal_column("'2099-12-31'")
                )
                subquery = subquery.join(
                    ProductAssignment,
                    and_(
                        ProductAssignment.product_id == Product.id,
                        AdData.date >= ProductAssignment.start_date,
                        AdData.date < end_date_with_default
                    )
                )
                subquery = subquery.join(Client, ProductAssignment.client_id == Client.id)
            else:
                subquery = subquery.join(Client, Product.client_id == Client.id)
            
            # 应用相同的过滤条件
            if current_user.role != UserRole.ADMIN:
                subquery = subquery.where(Client.user_id == current_user.id)
            else:
                if client_id:
                    subquery = subquery.where(Client.id == client_id)
            
            if product_id and product_id.strip():
                try:
                    product_id_int = int(product_id)
                    subquery = subquery.where(AdData.product_id == product_id_int)
                except ValueError:
                    pass
            
            if start_date:
                start_datetime = datetime.combine(start_date, datetime.min.time())
                subquery = subquery.where(AdData.date >= start_datetime)
            if end_date:
                end_datetime = datetime.combine(end_date, datetime.max.time())
                subquery = subquery.where(AdData.date <= end_datetime)
            elif not start_date and not end_date:
                today = date.today()
                month_start = date(today.year, today.month, 1)
                _, last_day = monthrange(today.year, today.month)
                month_end = date(today.year, today.month, last_day)
                month_start_datetime = datetime.combine(month_start, datetime.min.time())
                month_end_datetime = datetime.combine(month_end, datetime.max.time())
                subquery = subquery.where(AdData.date >= month_start_datetime)
                subquery = subquery.where(AdData.date <= month_end_datetime)
            
            # 分组去重
            subquery = subquery.group_by(
                func.date(AdData.date),
                Product.id
            )
            
            # 外层查询计数
            count_query = select(func.count()).select_from(subquery.alias("distinct_groups"))
            count_result = await db.execute(count_query)
            total = count_result.scalar() or 0
        except Exception as e:
            logger.error(f"计算每日汇总总数失败: {str(e)}")
            total = 0
    else:
        # 内存排序时，总数会在排序后计算
        total = 0
    
    # ====== 分页查询 ======
    # 如果需要在内存中排序，先获取所有数据，排序后再分页
    # 否则直接使用SQL分页
    if need_memory_sort:
        # 获取所有数据（不分页）
        result = await db.execute(query)
        all_summary_data = result.all()
    else:
        # 使用SQL分页
        offset = (page - 1) * page_size
        result = await db.execute(query.offset(offset).limit(page_size))
        all_summary_data = result.all()
    
    # 调试：记录查询结果
    if not settings.is_production:
        logger.debug(f"每日汇总查询结果：总数={total}, 当前页数据量={len(all_summary_data)}, 使用分配历史表={use_assignment_table}")
    
    # ====== 转换为响应格式 ======
    ad_data_responses = []
    for row in all_summary_data:
        date_obj = row.date if isinstance(row.date, date) else row.date.date() if hasattr(row.date, 'date') else row.date
        date_str = date_obj.isoformat() if hasattr(date_obj, 'isoformat') else str(date_obj)
        
        # 获取汇总后的数值
        total_request_count = int(row.request_count or 0)
        total_match_count = int(row.match_count or 0)
        total_display_count = int(row.display_count or 0)
        total_click_count = int(row.click_count or 0)
        total_viewability_rate = float(row.viewability_rate or 0.0)
        total_cpc = float(row.cpc or 0.0)
        total_pageviews = int(row.pageviews or 0)
        total_revenue_after = float(row.revenue_after_deduct or 0.0)
        total_revenue_before = float(row.revenue_before_deduct or 0.0)
        
        # 根据汇总后的数值重新计算比率（每日汇总时，使用汇总后的数值计算）
        # 覆盖率 = 匹配数 / 请求数 * 100
        coverage_rate = round(
            (total_match_count / total_request_count * 100) if total_request_count > 0 else 0.0,
            2
        )
        
        # 展示率 = 展示数 / 匹配数 * 100
        display_rate = round(
            (total_display_count / total_match_count * 100) if total_match_count > 0 else 0.0,
            2
        )
        
        # 点击率 = 点击数 / 展示数 * 100
        click_rate = round(
            (total_click_count / total_display_count * 100) if total_display_count > 0 else 0.0,
            2
        )
        
        # eCPM = 收益 / 展示数 * 1000
        ecpm_after_deduct = round(
            (total_revenue_after / total_display_count * 1000) if total_display_count > 0 else 0.0,
            4
        )
        
        # 扣减前eCPM = 扣减前收益 / 展示数 * 1000
        ecpm_before_deduct = round(
            (total_revenue_before / total_display_count * 1000) if total_display_count > 0 else 0.0,
            4
        )
        
        client_name = row.client_name or ""
        user_name = row.user_full_name or row.user_username or ""

        response_data = {
            "id": 0,  # 汇总数据没有ID
            "date": date_str,
            "product_id": row.product_id,
            "product_name": row.product_name or "",
            "country_code": "ZZ",  # 全部区域
            "country_name_zh": "全部区域",
            "request_count": total_request_count,
            "match_count": total_match_count,
            "coverage_rate": coverage_rate,
            "display_count": total_display_count,
            "display_rate": display_rate,
            "click_count": total_click_count,
            "click_rate": click_rate,
            "viewability_rate": round(total_viewability_rate, 2),
            "cpc": round(total_cpc, 2),
            "pageviews": total_pageviews,
            "ecpm_after_deduct": ecpm_after_deduct,
            "revenue_after_deduct": round(total_revenue_after, 4),
            "user_name": user_name
        }
        
        # 管理员额外返回未减扣数据
        if current_user.role == UserRole.ADMIN:
            response_data.update({
                "client_id": row.client_id,
                "client_name": client_name,
                "ecpm_before_deduct": ecpm_before_deduct,
                "revenue_before_deduct": round(total_revenue_before, 4)
            })
        
        ad_data_responses.append(AdDataResponse(**response_data))
    
    # ====== 内存排序（如果需要） ======
    if need_memory_sort:
        # 按计算字段排序
        reverse_order = sort_order.lower() == "desc"
        
        # 注意：coverage_rate、display_rate、click_rate 现在可以在SQL中排序，不需要内存排序
        if sort_by == "ecpm_before_deduct":
            ad_data_responses.sort(key=lambda x: x.ecpm_before_deduct or 0, reverse=reverse_order)
        
        # 内存排序后，需要重新计算总数和分页
        total = len(ad_data_responses)
        offset = (page - 1) * page_size
        ad_data_responses = ad_data_responses[offset:offset + page_size]
    
    return ResponseBaseSchema.success(data=AdDataListResponse(
        data=ad_data_responses,
        total=total,
        page=page,
        page_size=page_size
    ))


@router.get("/{data_id}", response_model=ResponseBaseSchema[AdDataResponse], summary="获取广告数据详情")
async def get_ad_data_detail(
        data_id: int = Path(..., ge=1, description="广告数据ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取指定广告数据的详细信息
    - 管理员可查看所有广告数据详情
    - 客户只能查看自己的广告数据详情
    - 返回完整的广告指标，包括计算出的各种比率
    """
    # 获取广告数据及关联的产品、客户和用户
    # 添加错误处理以提高健壮性
    try:
        from sqlalchemy.orm import load_only
        
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(db)
        
        if use_assignment_table:
            # 使用产品分配历史表
            query = select(AdData, Product, Client, User, ProductAssignment, CountryInfo)
            query = query.options(load_only(
                Client.id, Client.user_id, Client.company_name, Client.contact_person,
                Client.phone, Client.address, Client.is_active, Client.created_at, Client.updated_at
            ))
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    product_assignment_join_condition(
                        AdData.date,
                        ProductAssignment.start_date,
                        ProductAssignment.end_date
                    )
                )
            )
            query = query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            # 旧的查询方式
            query = select(AdData, Product, Client, User, CountryInfo)
            query = query.options(load_only(
                Client.id, Client.user_id, Client.company_name, Client.contact_person,
                Client.phone, Client.address, Client.is_active, Client.created_at, Client.updated_at
            ))
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)
        
        query = query.join(User, Client.user_id == User.id)
        query = join_country_info(query)  # 左关联国家信息（已处理排序规则冲突）
        query = query.where(AdData.id == data_id)
        # 只显示激活状态的产品（is_active = True）
        query = query.where(Product.is_active == True)

        result = await db.execute(query)
        data = result.unique().first()

        if not data:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据ID {data_id} 不存在"
            )

        # 根据是否使用ProductAssignment表，解构数据
        try:
            if use_assignment_table:
                if len(data) >= 6:
                    ad_data, product, client, user, assignment, country_info = data
                elif len(data) >= 5:
                    ad_data, product, client, user, assignment = data
                    country_info = None
                else:
                    ad_data, product, client, user = data
                    country_info = None
            else:
                if len(data) >= 5:
                    ad_data, product, client, user, country_info = data
                else:
                    ad_data, product, client, user = data
                    country_info = None
        except Exception as e:
            logger.error(f"解构数据失败: {str(e)}, data={data}")
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据ID {data_id} 数据格式错误"
            )

        # 验证关联数据完整性
        if not product:
            raise_api_exception(
                ErrorCode.AD_DATA_PRODUCT_NOT_FOUND,
                detail=f"广告数据关联的产品ID {ad_data.product_id} 不存在"
            )
        if not client:
            raise_api_exception(
                ErrorCode.CLIENT_NOT_FOUND,
                detail=f"广告数据关联的客户ID {product.client_id if product else '未知'} 不存在"
            )
        if not user:
            raise_api_exception(
                ErrorCode.USER_NOT_FOUND,
                detail=f"广告数据关联的用户ID {client.user_id if client else '未知'} 不存在"
            )

        # 权限检查
        if current_user.role != UserRole.ADMIN and client.user_id != current_user.id:
            raise_api_exception(
                ErrorCode.AD_DATA_NO_PERMISSION,
                detail=f"您没有权限访问广告数据ID {data_id}，该数据不属于您的客户账户"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取广告数据详情失败: {str(e)}")
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"查询广告数据失败：{str(e)}。请稍后重试或联系管理员"
        )

    # 使用数据库字段中的比率（如果为空则计算）
    coverage_rate = ad_data.coverage_rate if ad_data.coverage_rate is not None else round(
        (ad_data.match_count / ad_data.request_count * 100) if ad_data.request_count > 0 else 0.0,
        2
    )
    display_rate = ad_data.display_rate if ad_data.display_rate is not None else round(
        (ad_data.display_count / ad_data.match_count * 100) if ad_data.match_count > 0 else 0.0,
        2
    )
    click_rate = ad_data.click_rate if ad_data.click_rate is not None else round(
        (ad_data.click_count / ad_data.display_count * 100) if ad_data.display_count > 0 else 0.0,
        2
    )

    # 将 DateTime 转换为 date
    date_value = ad_data.date
    if isinstance(date_value, datetime):
        date_value = date_value.date()
    elif hasattr(date_value, 'date'):
        date_value = date_value.date()

    # 获取国家名称：如果通过JOIN找到了国家信息，使用它；否则根据country_code回退
    if country_info:
        country_name_zh = country_info.country_name_zh
    elif ad_data.country_code == "AA":
        country_name_zh = "未知区域"
    elif ad_data.country_code == "ZZ":
        country_name_zh = "全部区域"
    else:
        country_name_zh = None

    # 构建响应数据
    response_data = {
        "id": ad_data.id,
        "date": date_value,
        "client_id": client.id,
        "client_name": client.company_name,
        "user_name": user.full_name or user.username,  # 添加用户名称
        "product_id": product.id,
        "product_name": product.name,
        "country_code": ad_data.country_code,
        "country_name_zh": country_name_zh,
        "request_count": ad_data.request_count,
        "match_count": ad_data.match_count,
        "coverage_rate": coverage_rate,
        "display_count": ad_data.display_count,
        "display_rate": display_rate,
        "click_count": ad_data.click_count,
        "click_rate": click_rate,
        "viewability_rate": round(ad_data.viewability_rate or 0.0, 2),
        "ecpm_before_deduct": round(ad_data.ecpm_before_deduct, 4),
        "ecpm_after_deduct": round(ad_data.ecpm_after_deduct, 4),
        "revenue_before_deduct": round(ad_data.revenue_before_deduct, 4),
        "revenue_after_deduct": round(ad_data.revenue_after_deduct, 4),
        "created_at": ad_data.created_at,
        "updated_at": ad_data.updated_at
    }

    return ResponseBaseSchema.success(data=AdDataResponse(**response_data))


@router.post("/{data_id}", response_model=ResponseBaseSchema[AdDataResponse], summary="更新广告数据")
async def update_ad_data(
        data_id: int = Path(..., ge=1, description="广告数据ID"),
        ad_data_update: AdDataUpdate = Body(...),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    更新指定ID的广告数据
    - 仅管理员可更新广告数据
    - 支持部分字段更新
    - 不允许更新date、id、created_at等系统字段
    """
    # 权限检查
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(
            ErrorCode.AD_DATA_UPDATE_FORBIDDEN,
            detail="仅管理员可以更新广告数据。客户用户没有更新权限"
        )

    # 查询广告数据
    query = select(AdData).where(AdData.id == data_id)
    result = await db.execute(query)
    ad_data = result.scalars().first()

    if not ad_data:
        raise_api_exception(
            ErrorCode.AD_DATA_NOT_FOUND,
            detail=f"广告数据ID {data_id} 不存在"
        )

    # 定义允许更新的字段白名单
    allowed_fields = {
        'product_id', 'country_code', 'request_count', 'match_count', 'display_count',
        'click_count', 'viewability_rate', 'ecpm_after_deduct', 'ecpm_before_deduct',
        'revenue_after_deduct', 'revenue_before_deduct'
    }

    # 更新字段
    update_data = ad_data_update.model_dump(exclude_unset=True)

    # 如果更新product_id，验证产品是否存在
    if 'product_id' in update_data:
        product_id = update_data['product_id']
        product_result = await db.execute(select(Product).where(Product.id == product_id))
        product = product_result.scalars().first()
        if not product:
            raise_api_exception(
                ErrorCode.AD_DATA_PRODUCT_NOT_FOUND,
                detail=f"指定的产品ID {product_id} 不存在，请确认产品是否存在"
            )

    # 如果更新country_code，验证国家代码是否有效
    if 'country_code' in update_data:
        country_input = update_data['country_code']
        if country_input:
            # 支持多种格式：alpha_2_code、alpha_3_code、numeric_code、country_name_en、country_name_zh、official_name_en、official_name_zh
            from app.core.country_code import find_country_code_by_any_format
            found_country_code = await find_country_code_by_any_format(db, country_input)
            if found_country_code:
                update_data['country_code'] = found_country_code
            else:
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"无法识别国家代码格式: {country_input}。请使用有效的国家代码（如 'US'、'USA'、'840'、'United States of America' 或 '美国'）"
                )
        else:
            # 如果传入空字符串或 None，设置为 'ZZ'（全部区域）
            update_data['country_code'] = 'ZZ'

    # 检查唯一性约束：如果更新了 product_id 或 country_code，需要检查是否会违反唯一性约束
    # 唯一性约束：同一日期、产品ID和国家代码只能有一条记录
    if 'product_id' in update_data or 'country_code' in update_data:
        # 确定更新后的值
        new_product_id = update_data.get('product_id', ad_data.product_id)
        new_country_code = update_data.get('country_code', ad_data.country_code)
        
        # 构建日期范围查询（AdData.date 是 DateTime 类型）
        if isinstance(ad_data.date, datetime):
            date_start = ad_data.date.replace(hour=0, minute=0, second=0, microsecond=0)
            date_end = ad_data.date.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            date_start = datetime.combine(ad_data.date, datetime.min.time())
            date_end = datetime.combine(ad_data.date, datetime.max.time())
        
        # 查询是否存在相同的记录（排除当前记录）
        from sqlalchemy import or_
        # 国家代码匹配逻辑：如果新国家代码是'ZZ'，匹配'ZZ'或NULL
        if new_country_code == "ZZ":
            country_condition = or_(
                AdData.country_code == "ZZ",
                AdData.country_code.is_(None)
            )
        else:
            country_condition = AdData.country_code == new_country_code
        
        existing_query = select(AdData).where(
            AdData.id != ad_data.id,  # 排除当前记录
            AdData.date >= date_start,
            AdData.date <= date_end,
            AdData.product_id == new_product_id,
            country_condition
        )
        existing_result = await db.execute(existing_query)
        existing_data = existing_result.scalars().first()
        
        if existing_data:
            # 存在冲突记录，获取详细信息
            existing_country_name = "全部区域"
            if existing_data.country_code and existing_data.country_code != "ZZ":
                country_info_result = await db.execute(
                    select(CountryInfo).where(CountryInfo.alpha_2_code == existing_data.country_code)
                )
                country_info = country_info_result.scalar_one_or_none()
                if country_info:
                    existing_country_name = country_info.country_name_zh
            
            product_result = await db.execute(select(Product).where(Product.id == new_product_id))
            product = product_result.scalar_one_or_none()
            product_name = product.name if product else f"产品ID {new_product_id}"
            
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新失败：已存在相同的记录（日期={ad_data.date.date() if hasattr(ad_data.date, 'date') else ad_data.date}，产品={product_name}，国家={existing_country_name}）。请先删除或修改冲突的记录（ID: {existing_data.id}）"
            )

    for key, value in update_data.items():
        if key in allowed_fields and hasattr(ad_data, key):
            setattr(ad_data, key, value)
    
    # 如果基础数据字段有变化，重新计算比率字段
    if any(key in update_data for key in ['request_count', 'match_count', 'display_count', 'click_count']):
        ad_data.calculate_rates()

    # 保存更新
    try:
        db.add(ad_data)
        await db.commit()
        await db.refresh(ad_data)
    except Exception as e:
        await db.rollback()
        error_msg = str(e)
        
        # 检查是否是唯一性约束冲突
        if "IntegrityError" in str(type(e)) or "Duplicate entry" in error_msg or "uq_ad_data_date_product_country" in error_msg:
            # 提取冲突信息
            conflict_info = ""
            if "Duplicate entry" in error_msg:
                # 从错误信息中提取冲突的键值
                import re
                match = re.search(r"Duplicate entry '([^']+)'", error_msg)
                if match:
                    conflict_info = f"冲突的键值: {match.group(1)}"
            
            # 获取更新后的值用于错误提示
            new_product_id = update_data.get('product_id', ad_data.product_id)
            new_country_code = update_data.get('country_code', ad_data.country_code)
            
            # 获取产品名称
            product_result = await db.execute(select(Product).where(Product.id == new_product_id))
            product = product_result.scalar_one_or_none()
            product_name = product.name if product else f"产品ID {new_product_id}"
            
            # 获取国家名称
            country_name = "全部区域"
            if new_country_code and new_country_code != "ZZ":
                country_info_result = await db.execute(
                    select(CountryInfo).where(CountryInfo.alpha_2_code == new_country_code)
                )
                country_info = country_info_result.scalar_one_or_none()
                if country_info:
                    country_name = country_info.country_name_zh
            
            # 获取日期
            date_value = ad_data.date
            if isinstance(date_value, datetime):
                date_value = date_value.date()
            elif hasattr(date_value, 'date'):
                date_value = date_value.date()
            
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新失败：已存在相同的记录（日期={date_value}，产品={product_name}，国家={country_name}）。同一日期、产品和国家的组合必须唯一，请先删除或修改冲突的记录。{conflict_info}"
            )
        
        logger.error(f"更新广告数据失败: {error_msg}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新广告数据失败：{error_msg}。请检查数据格式或联系管理员"
        )

    # 返回更新后的广告数据
    return ResponseBaseSchema.success(data=AdDataResponse.model_validate(ad_data))


@router.delete("/batch", response_model=ResponseBaseSchema[dict], summary="批量删除广告数据")
async def batch_delete_ad_data(
        data_ids: list[int] = Body(..., description="广告数据ID列表"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    批量删除广告数据
    - 管理员可删除任何广告数据
    - 客户只能删除自己的广告数据
    - 永久删除数据
    """
    if not data_ids or len(data_ids) == 0:
        raise_api_exception(
            ErrorCode.AD_DATA_EMPTY_SELECTION,
            detail="请选择要删除的广告数据。数据ID列表不能为空"
        )

    # 检查是否使用产品分配历史表
    use_assignment_table = await check_use_assignment_table(db)
    
    # 获取所有广告数据及关联的产品和客户信息
    if use_assignment_table:
        # 使用产品分配历史表
        query = select(AdData, Product, Client, ProductAssignment).join(
            Product, AdData.product_id == Product.id
        ).join(
            ProductAssignment,
            and_(
                ProductAssignment.product_id == Product.id,
                product_assignment_join_condition(
                    AdData.date,
                    ProductAssignment.start_date,
                    ProductAssignment.end_date
                )
            )
        ).join(
            Client, ProductAssignment.client_id == Client.id
        ).where(AdData.id.in_(data_ids))
    else:
        # 旧的查询方式
        query = select(AdData, Product, Client).join(
            Product, AdData.product_id == Product.id
        ).join(
            Client, Product.client_id == Client.id
        ).where(AdData.id.in_(data_ids))

    result = await db.execute(query)
    all_data = result.unique().all()

    if not all_data:
        raise_api_exception(
            ErrorCode.AD_DATA_NOT_FOUND,
            detail=f"未找到要删除的广告数据。请确认数据ID是否正确"
        )

    # 权限检查和过滤
    deletable_data = []
    if current_user.role != UserRole.ADMIN:
        # 客户只能删除自己的广告数据
        for data_row in all_data:
            if use_assignment_table:
                ad_data, product, client, product_assignment = data_row
            else:
                ad_data, product, client = data_row
            
            if client.user_id == current_user.id:
                deletable_data.append(ad_data)
            else:
                logger.warning(f"用户 {current_user.username} 尝试删除无权访问的数据 ID: {ad_data.id}")
    else:
        # 管理员可以删除所有数据
        if use_assignment_table:
            deletable_data = [ad_data for ad_data, _, _, _ in all_data]
        else:
            deletable_data = [ad_data for ad_data, _, _ in all_data]

    if not deletable_data:
        raise_api_exception(
            ErrorCode.AD_DATA_DELETE_FORBIDDEN,
            detail="您没有权限删除选中的广告数据。部分数据不属于您的客户账户"
        )

    # 批量删除（使用批量操作优化性能）
    deleted_count = 0
    try:
        # 获取要删除的数据ID列表
        deletable_ids = [ad_data.id for ad_data in deletable_data]

        # 使用批量删除语句（更高效）
        delete_stmt = delete(AdData).where(AdData.id.in_(deletable_ids))
        result = await db.execute(delete_stmt)
        deleted_count = result.rowcount

        await db.commit()
        logger.info(f"Batch deleted {deleted_count} ad data records by {current_user.username}")
    except Exception as e:
        await db.rollback()
        logger.error(f"批量删除广告数据失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"批量删除广告数据失败：{str(e)}。请稍后重试或联系管理员"
        )

    return ResponseBaseSchema.success(data={
        "message": f"成功删除 {deleted_count} 条广告数据",
        "deleted_count": deleted_count
    })


@router.delete("/{data_id}", response_model=ResponseBaseSchema[dict], summary="删除广告数据")
async def delete_ad_data(
        data_id: int = Path(..., ge=1, description="广告数据ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    删除广告数据
    - 管理员可删除任何广告数据
    - 客户只能删除自己的广告数据
    - 永久删除数据
    """
    # 检查是否使用产品分配历史表
    use_assignment_table = await check_use_assignment_table(db)
    
    # 获取广告数据及关联的产品和客户信息
    if use_assignment_table:
        # 使用产品分配历史表（优化：避免在 AdData.date 上使用 func.date()）
        query = select(AdData, Product, Client, ProductAssignment).join(
            Product, AdData.product_id == Product.id
        ).join(
            ProductAssignment,
            and_(
                ProductAssignment.product_id == Product.id,
                product_assignment_join_condition(
                    AdData.date,
                    ProductAssignment.start_date,
                    ProductAssignment.end_date
                )
            )
        ).join(
            Client, ProductAssignment.client_id == Client.id
        ).where(AdData.id == data_id)
    else:
        # 旧的查询方式
        query = select(AdData, Product, Client).join(
            Product, AdData.product_id == Product.id
        ).join(
            Client, Product.client_id == Client.id
        ).where(AdData.id == data_id)

    result = await db.execute(query)
    data = result.unique().first()

    if not data:
        raise_api_exception(
            ErrorCode.AD_DATA_NOT_FOUND,
            detail=f"广告数据ID {data_id} 不存在"
        )

    # 根据是否使用产品分配历史表来正确解包
    try:
        if use_assignment_table:
            ad_data, product, client, product_assignment = data
        else:
            ad_data, product, client = data
    except (ValueError, TypeError) as e:
        logger.error(f"解构数据失败: {str(e)}, data={data}, use_assignment_table={use_assignment_table}")
        raise_api_exception(
            ErrorCode.AD_DATA_NOT_FOUND,
            detail=f"广告数据ID {data_id} 数据格式错误，无法解析"
        )

    # 权限检查
    if current_user.role != UserRole.ADMIN:
        # 客户只能删除自己的广告数据
        if client.user_id != current_user.id:
            raise_api_exception(
                ErrorCode.AD_DATA_DELETE_FORBIDDEN,
                detail=f"您没有权限删除广告数据ID {data_id}，该数据不属于您的客户账户"
            )

    # 删除广告数据
    try:
        await db.delete(ad_data)
        await db.commit()
        logger.info(
            f"Ad data {data_id} (date: {ad_data.date}, product: {product.name}) deleted by {current_user.username}")
    except Exception as e:
        await db.rollback()
        logger.error(f"删除广告数据失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除广告数据失败：{str(e)}。请稍后重试或联系管理员"
        )

    return ResponseBaseSchema.success(data={"message": "广告数据已成功删除"})


@router.get("/summary", response_model=ResponseBaseSchema[AdDataSummaryResponse], summary="获取广告数据汇总")
async def get_ad_data_summary(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD"),
        client_id: int | None = Query(None, description="客户ID过滤"),
        product_id: int | None = Query(None, description="产品ID过滤")
):
    """
    获取广告数据汇总统计
    - 计算指定条件下的广告数据总和
    - 包括请求数、匹配数、展示数、点击数等关键指标的汇总
    - 计算平均覆盖率、展示率、点击率等指标
    - 使用产品分配历史表时，会根据日期匹配正确的客户归属
    - 使用缓存提升性能（缓存 2 分钟）
    """
    # ====== 缓存优化 ======
    from app.core.cache import get_cached, set_cached, generate_cache_key
    cache_key = generate_cache_key("ad_data_summary", current_user.id, start_date, end_date, client_id, product_id)
    cached = await get_cached(cache_key)
    if cached:
        logger.debug(f"缓存命中: ad_data_summary, user={current_user.id}")
        return ResponseBaseSchema.success(data=AdDataSummaryResponse(**cached))
    
    # 检查是否使用产品分配历史表
    use_assignment_table = await check_use_assignment_table(db)
    
    # 构建查询基础
    # 使用数据库字段计算平均值，如果字段为空则使用计算值（使用 COALESCE 确保向后兼容）
    query = select(
        func.sum(AdData.request_count).label("total_requests"),
        func.sum(AdData.match_count).label("total_matches"),
        func.sum(AdData.display_count).label("total_displays"),
        func.sum(AdData.click_count).label("total_clicks"),
        func.sum(AdData.ecpm_after_deduct).label("total_ecpm_after"),
        func.sum(AdData.revenue_after_deduct).label("total_revenue_after"),
        func.coalesce(
            func.avg(AdData.coverage_rate),
            case((func.sum(AdData.request_count) == 0, 0),
                 else_=func.cast(func.sum(AdData.match_count), Float) * 100.0 / func.cast(
                     func.sum(AdData.request_count), Float))
        ).label("avg_coverage_rate"),
        func.coalesce(
            func.avg(AdData.display_rate),
            case((func.sum(AdData.match_count) == 0, 0),
                 else_=func.cast(func.sum(AdData.display_count), Float) * 100.0 / func.cast(
                     func.sum(AdData.match_count), Float))
        ).label("avg_display_rate"),
        func.coalesce(
            func.avg(AdData.click_rate),
            case((func.sum(AdData.display_count) == 0, 0),
                 else_=func.cast(func.sum(AdData.click_count), Float) * 100.0 / func.cast(
                     func.sum(AdData.display_count), Float))
        ).label("avg_click_rate")
    )
    query = query.join(Product, AdData.product_id == Product.id)
    
    if use_assignment_table:
        # 使用产品分配历史表
        # 优化：避免在 AdData.date 列上使用 func.date()，改为直接比较 DATE 和 DATETIME
        # MySQL 会自动将 DATE 转换为 DATETIME（时间部分为 00:00:00）进行比较
        # 为了包含整天的数据，结束日期需要加 1 天
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
        query = query.join(Client, ProductAssignment.client_id == Client.id)
    else:
        # 旧的查询方式
        query = query.join(Client, Product.client_id == Client.id)

    # 根据用户角色设置权限过滤
    if current_user.role != UserRole.ADMIN:
        # 客户只能查看自己的广告数据汇总
        query = query.where(Client.user_id == current_user.id)
    else:
        # 管理员可按客户ID过滤
        if client_id:
            query = query.where(Client.id == client_id)

    # 只显示激活状态的产品（is_active = True）
    query = query.where(Product.is_active == True)

    # 产品ID过滤
    if product_id:
        query = query.where(AdData.product_id == product_id)

    # 日期范围过滤
    # 注意：AdData.date 是 DateTime 类型，需要转换为 datetime 进行比较
    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time())
        query = query.where(AdData.date >= start_datetime)
    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time())
        query = query.where(AdData.date <= end_datetime)
    # 如果没有指定日期范围，默认查询当前月的数据
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

    # 执行汇总查询
    result = await db.execute(query)
    summary = result.first()

    # 处理空结果 - 添加None检查以提高健壮性
    if summary is None:
        total_requests = 0
        total_matches = 0
        total_displays = 0
        total_clicks = 0
        total_ecpm_after = 0
        total_revenue_after = 0
        avg_coverage_rate = 0
        avg_display_rate = 0
        avg_click_rate = 0
    else:
        total_requests = summary.total_requests or 0
        total_matches = summary.total_matches or 0
        total_displays = summary.total_displays or 0
        total_clicks = summary.total_clicks or 0
        total_ecpm_after = summary.total_ecpm_after or 0
        total_revenue_after = summary.total_revenue_after or 0
        avg_coverage_rate = summary.avg_coverage_rate or 0
        avg_display_rate = summary.avg_display_rate or 0
        avg_click_rate = summary.avg_click_rate or 0

    # 如果是管理员，还需要汇总未减扣的数据
    if current_user.role == UserRole.ADMIN:
        admin_query = select(
            func.sum(AdData.ecpm_before_deduct).label("total_ecpm_before"),
            func.sum(AdData.revenue_before_deduct).label("total_revenue_before")
        )
        admin_query = admin_query.join(Product, AdData.product_id == Product.id)
        
        # 使用与主查询相同的产品分配历史表逻辑
        if use_assignment_table:
            # 使用产品分配历史表
            admin_query = admin_query.join(
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
            admin_query = admin_query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            # 旧的查询方式
            admin_query = admin_query.join(Client, Product.client_id == Client.id)

        # 只显示激活状态的产品（is_active = True）
        admin_query = admin_query.where(Product.is_active == True)

        if client_id:
            admin_query = admin_query.where(Client.id == client_id)
        if product_id:
            admin_query = admin_query.where(AdData.product_id == product_id)
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            admin_query = admin_query.where(AdData.date >= start_datetime)
        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())
            admin_query = admin_query.where(AdData.date <= end_datetime)
        # 如果没有指定日期范围，默认查询当前月的数据
        elif not start_date and not end_date:
            today = date.today()
            # 当前月的第一天
            month_start = date(today.year, today.month, 1)
            # 当前月的最后一天
            _, last_day = monthrange(today.year, today.month)
            month_end = date(today.year, today.month, last_day)

            month_start_datetime = datetime.combine(month_start, datetime.min.time())
            month_end_datetime = datetime.combine(month_end, datetime.max.time())
            admin_query = admin_query.where(AdData.date >= month_start_datetime)
            admin_query = admin_query.where(AdData.date <= month_end_datetime)

        admin_result = await db.execute(admin_query)
        admin_summary = admin_result.first()
        if admin_summary is None:
            total_ecpm_before = 0
            total_revenue_before = 0
        else:
            total_ecpm_before = admin_summary.total_ecpm_before or 0
            total_revenue_before = admin_summary.total_revenue_before or 0
    else:
        total_ecpm_before = 0
        total_revenue_before = 0

    # 构建响应数据
    response_data = {
        "date_range": {
            "start_date": start_date or (date.today() - timedelta(days=30)),
            "end_date": end_date or date.today()
        },
        "total_requests": total_requests,
        "total_matches": total_matches,
        "total_displays": total_displays,
        "total_clicks": total_clicks,
        "avg_coverage_rate": round(avg_coverage_rate, 4),
        "avg_display_rate": round(avg_display_rate, 4),
        "avg_click_rate": round(avg_click_rate, 4),
        "total_ecpm_after_deduct": round(total_ecpm_after, 4),
        "total_revenue_after_deduct": round(total_revenue_after, 4)
    }

    # 管理员额外返回未减扣汇总数据
    if current_user.role == "admin":
        response_data.update({
            "total_ecpm_before_deduct": round(total_ecpm_before, 4),
            "total_revenue_before_deduct": round(total_revenue_before, 4)
        })

    # 缓存结果（缓存 2 分钟）
    await set_cached(cache_key, response_data, ttl=120)

    return ResponseBaseSchema.success(data=AdDataSummaryResponse(**response_data))


@router.get("/date-range", response_model=ResponseBaseSchema[dict], summary="获取数据的日期范围")
async def get_ad_data_date_range(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    client_id: int | None = Query(None, description="客户ID过滤"),
):
    """
    获取广告数据的日期范围（最早日期和最新日期）
    用于前端自动选择有数据的日期范围
    - 管理员可查看所有数据的日期范围
    - 客户只能查看自己数据的日期范围
    """
    try:
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(db)
        
        # 构建查询：获取日期的最小值和最大值
        if use_assignment_table:
            # 使用产品分配历史表
            query = select(
                func.min(func.date(AdData.date)).label("min_date"),
                func.max(func.date(AdData.date)).label("max_date")
            )
            query = query.join(Product, AdData.product_id == Product.id)
            
            end_date_with_default = func.coalesce(
                func.date_add(ProductAssignment.end_date, text("INTERVAL 1 DAY")),
                literal_column("'2099-12-31'")
            )
            query = query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    AdData.date >= ProductAssignment.start_date,
                    AdData.date < end_date_with_default
                )
            )
            query = query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            # 旧的查询方式
            query = select(
                func.min(func.date(AdData.date)).label("min_date"),
                func.max(func.date(AdData.date)).label("max_date")
            )
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)
        
        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)
        
        # 权限过滤
        if current_user.role != UserRole.ADMIN:
            query = query.where(Client.user_id == current_user.id)
        else:
            if client_id:
                query = query.where(Client.id == client_id)
        
        # 执行查询
        result = await db.execute(query)
        row = result.first()
        
        if row and row.min_date and row.max_date:
            return ResponseBaseSchema.success(data={
                "min_date": row.min_date.isoformat() if hasattr(row.min_date, 'isoformat') else str(row.min_date),
                "max_date": row.max_date.isoformat() if hasattr(row.max_date, 'isoformat') else str(row.max_date)
            })
        else:
            # 没有数据
            return ResponseBaseSchema.success(data={
                "min_date": None,
                "max_date": None
            })
    except Exception as e:
        logger.error(f"获取日期范围失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取日期范围失败: {str(e)}"
        )