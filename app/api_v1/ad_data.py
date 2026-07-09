"""广告数据管理API端点
提供广告数据的CRUD操作和统计分析功能，包括：
- 获取广告数据列表（支持分页、过滤、排序）
- 获取广告数据详情
- 更新广告数据（字段白名单验证）
- 获取广告数据汇总统计
- 支持按日期范围、客户ID、产品ID过滤
- 管理员可查看所有数据，客户只能查看自己的数据。

说明：REST API 端点，统一 ResponseBaseSchema 响应；鉴权由各端点 Depends 声明。"""
# 标准库导入
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy import delete, func, text, literal_column, case, Float
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# 本地导入
from app.core.audit_log import log_update, log_delete, log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.security import get_current_user, require_admin, is_admin
from app.core.config import settings
from app.core.constants import MAX_PAGE_SIZE, ECPM_MULTIPLIER, PERCENTAGE_MULTIPLIER
from app.models.models import AdData, Client, Product, User, UserRole, ProductAssignment, CountryInfo
from sqlalchemy import and_, or_
from app.core.ad_data_metadata import format_data_source_label, format_report_type_label
from app.core.country_code import resolve_country_name
from app.core.query_utils import (
    product_assignment_join_condition, 
    check_use_assignment_table, 
    join_country_info as join_country_info_util,
    apply_date_range_filter
)
from app.core.dependencies import get_ad_data_service
from app.core.utils import (
    optimize_page_size_for_device, get_product_name, get_client_name, get_user_name,
    calculate_coverage_rate, calculate_display_rate, calculate_click_rate
)
from app.schemas.ad_data import (
    AdDataResponse,
    AdDataSummaryResponse,
    AdDataUpdate,
)
from app.schemas.base import PaginatedResponseBaseSchema, ResponseBaseSchema, ListResponseBaseSchema
from app.core.exceptions import raise_api_exception, raise_filter_validation_api_exception
from app.core.errors import ErrorCode
from app.services.ad_data.queries.filter_conditions import InvalidFilterParameterError
from app.services.ad_data_service import AdDataService

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


def _serialize_ad_data_list_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    序列化明细列表项：经 AdDataResponse 校验后，保留 list_query 中的全部字段。

    避免 response_model 仅含旧字段时，data_source / report_type 等元数据被丢弃。
    """
    serialized: list[dict[str, Any]] = []
    for item in items:
        validated = AdDataResponse.model_validate(item)
        row = validated.model_dump(mode="json")
        for key, value in item.items():
            if key not in row:
                row[key] = value
        serialized.append(row)
    return serialized


# 使用公共函数 join_country_info，传入 AdData.country_code 列
def join_country_info(query):
    """
    辅助函数：统一处理 CountryInfo 的 JOIN，解决排序规则冲突问题
    临时方案：使用 COLLATE 统一排序规则
    永久方案：运行 scripts/fix_collation_issue.sql 修改表结构
    
    注意：此函数是对公共函数 join_country_info 的包装，传入 AdData.country_code
    """
    return join_country_info_util(query, AdData.country_code)


@router.get("/", response_model=PaginatedResponseBaseSchema[list[dict[str, Any]]], summary="获取广告数据列表")
async def get_ad_data(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD"),
        client_id: str | None = Query(None, description="客户ID过滤，支持逗号分隔多选"),
        product_id: str | None = Query(None, description="产品ID过滤，支持逗号分隔多选"),
        country_code: str | None = Query(None, description="国家代码过滤（如：US、CN、ZZ表示全部区域），支持逗号分隔多选"),
        ad_unit: str | None = Query(None, description="广告单元精确过滤，支持逗号分隔多选"),
        dimension: str | None = Query(
            "country",
            description="统计维度：country=按国家，ad_unit=按广告单元，ad_unit_country=按广告单元+国家（country_ad_unit 为兼容别名）",
        ),
        data_source: str | None = Query(None, description="数据来源过滤（管理员），支持逗号分隔多选，如 zhisuo,gam"),
        upstream_account: str | None = Query(None, description="上游账号过滤（管理员），支持逗号分隔多选，如 KE11"),
        report_type: str | None = Query(None, description="报表类型过滤（管理员），支持逗号分隔多选，如 unit,country,cross"),
        sort_by: str = Query("date", description="排序字段，默认为date"),
        sort_order: str = Query("desc", description="排序方向，asc或desc")
):
    """
    获取广告数据列表，支持分页、过滤和排序（已重构使用服务层）
    - 管理员可查看所有广告数据
    - 客户只能查看自己的广告数据
    - 支持按日期范围、客户ID和产品ID过滤
    - 支持按不同字段排序
    - 移动端自动优化分页大小
    """
    # ====== 设备类型优化：自动调整分页大小 ======
    page_size = optimize_page_size_for_device(request, page_size, default_page_size=10)

    # 使用服务层（业务逻辑在AdDataService中）
    ad_data_service: AdDataService = await get_ad_data_service(db)
    
    # 调用服务层获取广告数据列表（服务层会处理查询、过滤、排序、分页等）
    ad_data_responses, total, grand_total = await ad_data_service.get_ad_data(
        current_user=current_user,
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        client_id=client_id,
        product_id=product_id,
        country_code=country_code,
        ad_unit=ad_unit,
        dimension=dimension,
        data_source=data_source,
        upstream_account=upstream_account,
        report_type=report_type,
        sort_by=sort_by,
        sort_order=sort_order
    )

    # 转换为响应格式（保留元数据字段，避免 Schema 未热更新时被剥离）
    ad_data_list = _serialize_ad_data_list_items(ad_data_responses)

    return PaginatedResponseBaseSchema.success(
        data=ad_data_list,
        total=total,
        page=page,
        page_size=page_size,
        grand_total=grand_total,
    )


@router.get("/clients-with-data", response_model=ListResponseBaseSchema[list[dict]], summary="获取有数据的客户列表")
async def get_clients_with_data(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD")
):
    """
    获取有广告数据的客户列表（用于下拉选择，已重构使用服务层）
    - 只返回在指定日期范围内有数据的客户
    - 如果没有指定日期范围，使用当前月作为默认范围
    - 管理员可查看所有有数据的客户
    - 客户只能看到自己
    - 使用缓存提升性能（缓存 5 分钟）
    """
    # 使用服务层（业务逻辑在AdDataService中）
    ad_data_service: AdDataService = await get_ad_data_service(db)
    
    try:
        clients_list = await ad_data_service.get_clients_with_data(
            current_user=current_user,
            start_date=start_date,
            end_date=end_date
        )
        return ListResponseBaseSchema.success(data=clients_list, count=len(clients_list))
    except HTTPException:
        raise
    except InvalidFilterParameterError as exc:
        raise_filter_validation_api_exception(str(exc))
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
        client_id: str | None = Query(None, description="客户ID过滤，支持逗号分隔多选"),
        product_id: str | None = Query(None, description="产品ID过滤，支持逗号分隔多选"),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD"),
        dimension: str | None = Query(
            "country",
            description="统计维度：country=按国家，ad_unit=按广告单元，ad_unit_country=按广告单元+国家（country_ad_unit 为兼容别名）",
        ),
        ad_unit: str | None = Query(None, description="广告单元过滤，用于级联筛选国家"),
):
    """
    获取有广告数据的国家列表（用于下拉选择，已重构使用服务层）
    - 只返回在指定条件下有数据的国家
    - 如果没有指定日期范围，使用当前月作为默认范围
    - 管理员可查看所有有数据的国家
    - 客户只能看到自己数据中的国家
    """
    # 使用服务层（业务逻辑在AdDataService中）
    ad_data_service: AdDataService = await get_ad_data_service(db)

    try:
        countries_list = await ad_data_service.get_countries_with_data(
            current_user=current_user,
            client_id=client_id,
            product_id=product_id,
            start_date=start_date,
            end_date=end_date,
            dimension=dimension,
            ad_unit=ad_unit,
        )
        return ListResponseBaseSchema.success(data=countries_list, count=len(countries_list))
    except HTTPException:
        raise
    except InvalidFilterParameterError as exc:
        raise_filter_validation_api_exception(str(exc))
    except Exception as e:
        logger.error(f"获取有数据的国家列表失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取有数据的国家列表失败：{str(e)}。请稍后重试或联系管理员"
        )


@router.get("/ad-units-with-data", response_model=ListResponseBaseSchema[list[dict]], summary="获取有数据的广告单元列表")
async def get_ad_units_with_data(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        client_id: str | None = Query(None, description="客户ID过滤，支持逗号分隔多选"),
        product_id: str | None = Query(None, description="产品ID过滤，支持逗号分隔多选"),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD"),
        dimension: str | None = Query(
            "ad_unit",
            description="统计维度：country=按国家，ad_unit=按广告单元，ad_unit_country=按广告单元+国家（country_ad_unit 为兼容别名）",
        ),
        country_code: str | None = Query(None, description="国家代码过滤，用于级联筛选广告单元"),
):
    """获取有广告数据的广告单元列表（用于下拉选择）。"""
    ad_data_service: AdDataService = await get_ad_data_service(db)

    try:
        ad_units_list = await ad_data_service.get_ad_units_with_data(
            current_user=current_user,
            client_id=client_id,
            product_id=product_id,
            start_date=start_date,
            end_date=end_date,
            dimension=dimension,
            country_code=country_code,
        )
        return ListResponseBaseSchema.success(data=ad_units_list, count=len(ad_units_list))
    except HTTPException:
        raise
    except InvalidFilterParameterError as exc:
        raise_filter_validation_api_exception(str(exc))
    except Exception as e:
        logger.error(f"获取有数据的广告单元列表失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取有数据的广告单元列表失败：{str(e)}。请稍后重试或联系管理员"
        )


@router.get("/products-with-data", response_model=ListResponseBaseSchema[list[dict]], summary="获取有数据的产品列表")
async def get_products_with_data(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        client_id: str | None = Query(None, description="客户ID过滤，支持逗号分隔多选"),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD")
):
    """
    获取有广告数据的产品列表（用于下拉选择，已重构使用服务层）

    筛选逻辑：
    1. 分配历史：按每条数据行的日期匹配 ProductAssignment，随 start_date/end_date 动态变化
    2. 当前归属（客户角色且启用分配表时）：补充 Product.client_id 名下、日期范围内有数据的产品
    3. 未指定日期范围时默认当前月；仅返回激活产品
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 使用服务层（业务逻辑在AdDataService中）
    ad_data_service: AdDataService = await get_ad_data_service(db)
    
    # ---------- 异常处理 ----------
    try:
        products_list = await ad_data_service.get_products_with_data(
            current_user=current_user,
            client_id=client_id,
            start_date=start_date,
            end_date=end_date
        )
        return ListResponseBaseSchema.success(data=products_list, count=len(products_list))
    except HTTPException:
        raise
    except InvalidFilterParameterError as exc:
        raise_filter_validation_api_exception(str(exc))
    except Exception as e:
        logger.error(f"获取有数据的产品列表失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取有数据的产品列表失败：{str(e)}。请稍后重试或联系管理员"
        )


@router.get("/daily-summary", response_model=PaginatedResponseBaseSchema[list[AdDataResponse]], summary="获取每日汇总数据")
async def get_daily_summary(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD"),
        client_id: str | None = Query(None, description="客户ID过滤，支持逗号分隔多选"),
        product_id: str | None = Query(None, description="产品ID过滤，支持逗号分隔多选"),
        country_code: str | None = Query(None, description="国家代码过滤，支持逗号分隔多选"),
        ad_unit: str | None = Query(None, description="广告单元精确过滤，支持逗号分隔多选"),
        dimension: str | None = Query(
            "country",
            description="统计维度：country=按国家，ad_unit=按广告单元，ad_unit_country=按广告单元+国家（country_ad_unit 为兼容别名）",
        ),
        split_by_country: bool = Query(
            False,
            description="国家维度日汇总是否按国家分行（国家数据页）；交叉维度时后端自动按国家分组",
        ),
        sort_by: str = Query("date", description="排序字段，默认为date"),
        sort_order: str = Query("desc", description="排序方向，asc或desc")
):
    """
    获取每日汇总数据（按统计维度分组，已重构使用服务层）
    - 按国家：筛选国家级明细，按产品+日期汇总；split_by_country=true 时按国家分行
    - 按广告单元：按产品+日期+广告单元汇总
    - 按广告单元+国家：筛选交叉明细，按产品+日期+广告单元+国家汇总
    - 支持分页、过滤和排序
    - 管理员可查看所有数据，客户只能查看自己的数据
    """
    # ====== 设备类型优化：自动调整分页大小 ======
    page_size = optimize_page_size_for_device(request, page_size, default_page_size=10)

    # 使用服务层（业务逻辑在AdDataService中）
    ad_data_service: AdDataService = await get_ad_data_service(db)
    
    # 调用服务层获取每日汇总数据（服务层会处理查询、分组、排序、分页等）
    ad_data_responses, total, grand_total = await ad_data_service.get_daily_summary(
        current_user=current_user,
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        client_id=client_id,
        product_id=product_id,
        country_code=country_code,
        ad_unit=ad_unit,
        dimension=dimension,
        split_by_country=split_by_country,
        sort_by=sort_by,
        sort_order=sort_order
    )

    # 转换为响应格式
    ad_data_list = [AdDataResponse(**item) for item in ad_data_responses]

    return PaginatedResponseBaseSchema.success(
        data=ad_data_list,
        total=total,
        page=page,
        page_size=page_size,
        grand_total=grand_total,
    )


@router.get("/date-range", response_model=ResponseBaseSchema[dict], summary="获取数据的日期范围")
async def get_ad_data_date_range(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    client_id: int | None = Query(None, description="客户ID过滤"),
):
    """
    获取广告数据的日期范围（最早日期和最新日期，已重构使用服务层）
    用于前端自动选择有数据的日期范围
    - 管理员可查看所有数据的日期范围
    - 客户只能查看自己数据的日期范围
    """
    # 使用服务层（业务逻辑在AdDataService中）
    ad_data_service: AdDataService = await get_ad_data_service(db)
    
    try:
        date_range = await ad_data_service.get_date_range(
            current_user=current_user,
            client_id=client_id
        )
        return ResponseBaseSchema.success(data=date_range)
    except HTTPException:
        raise
    except InvalidFilterParameterError as exc:
        raise_filter_validation_api_exception(str(exc))
    except Exception as e:
        logger.error(f"获取日期范围失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取日期范围失败: {str(e)}"
        )


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
    获取广告数据汇总统计（已重构使用服务层）
    - 计算指定条件下的广告数据总和
    - 包括请求数、匹配数、展示数、点击数等关键指标的汇总
    - 计算平均覆盖率、展示率、点击率等指标
    - 使用产品分配历史表时，会根据日期匹配正确的客户归属
    - 使用缓存提升性能（缓存 2 分钟）
    """
    # 使用服务层（业务逻辑在AdDataService中）
    ad_data_service: AdDataService = await get_ad_data_service(db)
    
    # 调用服务层获取汇总数据（服务层会处理查询、缓存和权限检查）
    response_data = await ad_data_service.get_ad_data_summary(
        current_user=current_user,
        start_date=start_date,
        end_date=end_date,
        client_id=client_id,
        product_id=product_id
    )

    return ResponseBaseSchema.success(data=AdDataSummaryResponse(**response_data))


@router.get("/{data_id}", response_model=ResponseBaseSchema[AdDataResponse], summary="获取广告数据详情")
async def get_ad_data_detail(
        data_id: int = Path(..., ge=1, description="广告数据ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取指定广告数据的详细信息（已重构使用服务层）
    - 管理员可查看所有广告数据详情
    - 客户只能查看自己的广告数据详情
    - 返回完整的广告指标，包括计算出的各种比率
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 使用服务层（业务逻辑在AdDataService中）
    ad_data_service: AdDataService = await get_ad_data_service(db)
    
    # 获取广告数据及关联信息（服务层会处理查询、验证和权限检查）
    ad_data, product, client, user, assignment, country_info = await ad_data_service.get_ad_data_by_id(
        data_id, current_user
    )

    # 使用统一的比率计算函数
    
    coverage_rate = calculate_coverage_rate(
        ad_data.match_count,
        ad_data.request_count,
        ad_data.coverage_rate
    )
    display_rate = calculate_display_rate(
        ad_data.display_count,
        ad_data.match_count,
        ad_data.display_rate
    )
    click_rate = calculate_click_rate(
        ad_data.click_count,
        ad_data.display_count,
        ad_data.click_rate
    )

    # 将 DateTime 转换为 date
    date_value = ad_data.date
    # ---------- 条件分支 ----------
    if isinstance(date_value, datetime):
        date_value = date_value.date()
    # ---------- 条件分支 ----------
    elif hasattr(date_value, 'date'):
        date_value = date_value.date()

    country_name_zh = resolve_country_name(country_info, ad_data.country_code)

    # 构建响应数据
    response_data = {
        "id": ad_data.id,
        "date": date_value,
        "client_id": client.id,
        "client_name": client.company_name,
        "user_name": user.full_name or user.username,  # 添加用户名称
        "product_id": product.id,
        "product_name": product.name,
        "ad_unit": ad_data.ad_unit or "",
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
    if is_admin(current_user):
        response_data.update(
            {
                "data_source": ad_data.data_source or "legacy",
                "data_source_label": format_data_source_label(ad_data.data_source),
                "upstream_account": ad_data.upstream_account or "",
                "report_type": ad_data.report_type or "legacy",
                "report_type_label": format_report_type_label(ad_data.report_type),
            }
        )

    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data=AdDataResponse(**response_data))


@router.put("/{data_id}", response_model=ResponseBaseSchema[AdDataResponse], summary="更新广告数据")
async def update_ad_data(
        request: Request,
        data_id: int = Path(..., ge=1, description="广告数据ID"),
        ad_data_update: AdDataUpdate = Body(...),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    更新指定ID的广告数据（已重构使用服务层）
    - 仅管理员可更新广告数据
    - 支持部分字段更新
    - 不允许更新date、id、created_at等系统字段
    - 使用PUT方法符合RESTful规范
    """
    # 使用服务层（业务逻辑在AdDataService中）
    ad_data_service: AdDataService = await get_ad_data_service(db)
    
    # 获取更新数据
    update_data = ad_data_update.model_dump(exclude_unset=True)
    
    # 调用服务层更新广告数据（服务层会处理所有验证、唯一性检查、比率计算和错误处理）
    ad_data = await ad_data_service.update_ad_data(data_id, update_data, current_user)

    if update_data:
        await log_update(
            db=db,
            user=current_user,
            resource_type="AD_DATA",
            resource_id=data_id,
            resource_name=f"广告数据-{data_id}",
            request=request,
            details={"updated_fields": list(update_data.keys())},
        )

    # 返回更新后的广告数据
    return ResponseBaseSchema.success(data=AdDataResponse.model_validate(ad_data))


@router.delete("/batch", response_model=ResponseBaseSchema[dict], summary="批量删除广告数据")
async def batch_delete_ad_data(
        request: Request,
        data_ids: list[int] = Body(..., description="广告数据ID列表"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    批量删除广告数据（已重构使用服务层）
    - 管理员可删除任何广告数据
    - 客户只能删除自己的广告数据
    - 永久删除数据
    """
    # 使用服务层（业务逻辑在AdDataService中）
    ad_data_service: AdDataService = await get_ad_data_service(db)
    
    # 调用服务层批量删除广告数据（服务层会处理权限检查和批量删除）
    deleted_count = await ad_data_service.batch_delete_ad_data(data_ids, current_user)

    await log_user_action(
        db=db,
        action_type="DELETE",
        user=current_user,
        resource_type="AD_DATA",
        resource_id=data_ids[0] if len(data_ids) == 1 else 0,
        resource_name=f"批量删除广告数据({deleted_count}条)",
        request=request,
        details={"data_ids": data_ids, "deleted_count": deleted_count},
    )
    await commit_audit_log(db)

    return ResponseBaseSchema.success(data={
        "message": f"成功删除 {deleted_count} 条广告数据",
        "deleted_count": deleted_count
    })


@router.delete("/{data_id}", response_model=ResponseBaseSchema[dict], summary="删除广告数据")
async def delete_ad_data(
        request: Request,
        data_id: int = Path(..., ge=1, description="广告数据ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    删除广告数据（已重构使用服务层）
    - 管理员可删除任何广告数据
    - 客户只能删除自己的广告数据
    - 永久删除数据
    """
    # 使用服务层（业务逻辑在AdDataService中）
    ad_data_service: AdDataService = await get_ad_data_service(db)
    
    # 调用服务层删除广告数据（服务层会处理权限检查）
    await ad_data_service.delete_ad_data(data_id, current_user)

    await log_delete(
        db=db,
        user=current_user,
        resource_type="AD_DATA",
        resource_id=data_id,
        resource_name=f"广告数据-{data_id}",
        request=request,
    )
    await commit_audit_log(db)

    return ResponseBaseSchema.success(data={"message": "广告数据已成功删除"})


