"""客户API端点
提供客户通过API密钥访问的接口，包括：
- 查询所有产品名称
- 查询广告数据（默认当前月数据）

请求验证：
- 验证客户ID和API密钥（secret_key）
- 验证请求时间差异（10秒内）
- 验证MD5签名。

说明：对外开放接口，含客户 API（密钥+签名鉴权）与 Telegram 管理。"""
import asyncio
import logging
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.api_auth import verify_client_request
from app.core.audit_log import log_user_action, commit_audit_log
from app.core.constants import CLIENT_API_DEFAULT_PAGE_SIZE, CLIENT_API_MAX_PAGE_SIZE
from app.core.database import AsyncSessionLocal, get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import get_current_user
from app.core.telegram import send_telegram_message_async
from app.core.utils import get_client_ip
from app.models.models import Client, Product, User, UserRole
from app.schemas.base import BaseSchema, PaginatedResponseBaseSchema, ResponseBaseSchema
from app.services.ad_data.queries.client_api_query import ClientAdDataQuery
from app.services.ad_data.queries.dimension_filter import ensure_valid_optional_dimension

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


async def _get_client_user_names(db: AsyncSession, user_id: int | None) -> tuple[str, str]:
    """一次查询获取 username 与展示用 full_name。"""
    if not user_id:
        return "CLIENT_None", "CLIENT_None"
    try:
        result = await db.execute(
            select(User.username, User.full_name).where(User.id == user_id)
        )
        row = result.first()
        if not row:
            return f"CLIENT_{user_id}", f"CLIENT_{user_id}"
        username = row.username or f"CLIENT_{user_id}"
        full_name = row.full_name or username
        return username, full_name
    except Exception:
        return f"CLIENT_{user_id}", f"CLIENT_{user_id}"


async def _background_client_api_side_effects(
    *,
    action_type: str,
    user_id: int | None,
    username: str,
    resource_type: str,
    resource_id: int | None,
    resource_name: str,
    ip_address: str,
    user_agent: str,
    success: bool,
    details: dict[str, Any],
    request_method: str,
    request_path: str,
    telegram_msg: str | None = None,
) -> None:
    """审计写库与 Telegram 通知均在响应返回后执行，避免阻塞客户 API。"""
    try:
        async with AsyncSessionLocal() as bg_db:
            await log_user_action(
                db=bg_db,
                action_type=action_type,
                user_id=user_id,
                username=username,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                ip_address=ip_address,
                user_agent=user_agent,
                request_method=request_method,
                request_path=request_path,
                success=success,
                details=details,
            )
            await commit_audit_log(bg_db)
    except Exception as log_error:
        logger.warning(f"后台记录客户API访问日志失败: {log_error}")

    if telegram_msg:
        try:
            await asyncio.wait_for(
                send_telegram_message_async(telegram_msg),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.warning("后台发送 Telegram 通知超时")
        except Exception as notify_error:
            logger.warning(f"后台发送 Telegram 通知失败: {notify_error}")


@router.get(
    "/client/api-key",
    response_model=ResponseBaseSchema[dict],
    summary="获取当前客户 API 密钥",
)
async def get_client_api_key(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """客户登录后按需获取 API 密钥，用于对接文档与签名示例。"""
    if current_user.role != UserRole.CLIENT:
        raise_api_exception(ErrorCode.FORBIDDEN, detail="仅客户账号可获取 API 密钥")
    result = await db.execute(
        select(Client).where(Client.user_id == current_user.id, Client.is_active == True)
    )
    client = result.scalars().first()
    if not client:
        raise_api_exception(ErrorCode.CLIENT_NOT_FOUND, detail="客户信息不存在")
    if not client.api_enabled:
        raise_api_exception(ErrorCode.FORBIDDEN, detail="API 访问未启用")
    return ResponseBaseSchema.success(data={"key": client.key})


# ====== 请求模型 ======
class ClientAPIBaseRequest(BaseModel):
    """
    客户 API 基础请求模型（所有对外接口共用）。

    字段：client_id、req_time（10 位秒级时间戳）、sign（MD5 签名）。
    服务端校验时间差 ≤15 秒且签名与 secret_key 匹配。
    """
    client_id: int = Field(..., description="客户ID")
    req_time: int = Field(..., description="请求时间戳（10位秒级）")
    sign: str = Field(..., description="MD5签名")


class ClientProductsRequest(ClientAPIBaseRequest):
    """查询客户名下全部激活产品名称列表，无额外参数。（详见字段 Field description）。"""
    pass


class ClientDataRequest(ClientAPIBaseRequest):
    """
    查询客户广告数据请求。

    data_type：all=明细，day=日汇总。
    dimension（可选）：country / ad_unit / ad_unit_country（country_ad_unit 为兼容别名），与后台报表统计维度一致；不传则保持历史全量返回。
    日期缺省为当前自然月首尾。
    """
    data_type: str = Field(default="all",
                           description="数据类型：'all' 表示详细数据，'day' 表示每日汇总，默认为 'all'")
    dimension: str | None = Field(
        default=None,
        description="统计维度（可选）：country=按国家，ad_unit=按广告单元，ad_unit_country=按广告单元+国家（country_ad_unit 为兼容别名）；不传则不过滤维度",
    )
    start_date: str | None = Field(default=None, description="起始日期（格式：YYYY-MM-DD），可选，不提供则使用当前月第一天")
    end_date: str | None = Field(default=None, description="终止日期（格式：YYYY-MM-DD），可选，不提供则使用当前月最后一天")
    page: int | None = Field(default=None, ge=1, description="页码，从 1 开始；不传默认 1")
    page_size: int | None = Field(
        default=None,
        ge=1,
        le=CLIENT_API_MAX_PAGE_SIZE,
        description=f"每页条数；不传默认 {CLIENT_API_DEFAULT_PAGE_SIZE}，最大 {CLIENT_API_MAX_PAGE_SIZE}",
    )


# ====== 响应模型 ======
class ProductNameResponse(BaseModel):
    """
    产品名称响应模型
    
    注意：此模型设计考虑了Java客户端的兼容性：
    - id为整数类型，不会返回字符串
    - name确保不为null（空字符串代替）
    """
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class AdDataItemResponse(BaseSchema):
    """
    广告数据项响应模型
    
    注意：此模型设计考虑了Java客户端的兼容性：
    - 数值字段使用 Decimal 校验，JSON 输出为数字
    - 日期格式为ISO标准格式（YYYY-MM-DD）
    - 字符串字段确保不为null（空字符串代替）
    """
    date: str = Field(..., description="数据日期（ISO格式：YYYY-MM-DD）")
    product_name: str = Field(..., description="产品名称")
    ad_unit: str = Field(default="", description="广告单元（可为空）")
    country_code: str = Field(..., description="国家二字代码（ISO 3166-1 alpha-2）")
    country_name_zh: str = Field(default="", description="国家中文名称")
    request_count: int = Field(..., description="请求数（整数）")
    match_count: int = Field(..., description="匹配数（整数）")
    coverage_rate: Decimal = Field(..., description="覆盖率（%）")
    display_count: int = Field(..., description="展示数（整数）")
    display_rate: Decimal = Field(..., description="展示率（%）")
    click_count: int = Field(..., description="点击数（整数）")
    click_rate: Decimal = Field(..., description="点击率（%）")
    viewability_rate: Decimal = Field(default=Decimal('0'), description="可见率（%）")
    cpc: Decimal = Field(..., description="CPC")
    pageviews: int = Field(..., description="PageViews（整数）")
    ecpm: Decimal = Field(..., description="eCPM")
    revenue: Decimal = Field(..., description="收益")

    """
    查询客户的所有产品名称
    - 需要提供client_id、req_time和sign
    - 返回该客户的所有激活产品名称列表
    
    功能：查询单条或详情（get_client_products）。
    实现：异步端点，通过 Service 层访问数据库/缓存。
    鉴权：由 Depends(get_current_user) 或 require_admin 控制访问范围。
    响应：统一 ResponseBaseSchema / PaginatedResponseBaseSchema 包装。
    """
# 签名验证函数已移至 app/core/api_auth.py


# ====== API端点 ======
@router.post("/client_products", response_model=ResponseBaseSchema[list[ProductNameResponse]],
             summary="查询所有产品名称")
async def get_client_products(
        request: Request,
        background_tasks: BackgroundTasks,
        api_request: ClientProductsRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    查询客户的所有产品名称
    - 需要提供client_id、req_time和sign
    - 返回该客户的所有激活产品名称列表
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        # 验证请求（产品接口不需要额外的参数）
        client = await verify_client_request(api_request, db)

        # 查询该客户的所有激活产品
        result = await db.execute(
            select(Product).where(Product.client_id == client.id, Product.is_active == True).order_by(Product.id.asc())
        )
        products = result.scalars().all()

        # 转换为响应格式（确保Java兼容性）
        product_list = [
            ProductNameResponse(
                id=int(product.id),  # 明确转换为整数
                name=product.name or ""  # 确保不为None
            )
            for product in products
        ]

        logger.info(f"客户 {client.id} 查询产品列表，返回 {len(product_list)} 个产品")

        username, _ = await _get_client_user_names(db, client.user_id)
        background_tasks.add_task(
            _background_client_api_side_effects,
            action_type="API_ACCESS",
            user_id=client.user_id,
            username=username,
            resource_type="PRODUCT",
            resource_id=None,
            resource_name="产品列表",
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:500],
            success=True,
            request_method=request.method,
            request_path=request.url.path,
            details={
                "client_id": client.id,
                "client_name": client.company_name,
                "product_count": len(product_list),
                "api_endpoint": "/client_products",
            },
        )

        return ResponseBaseSchema.success(
            data=product_list if product_list else [],  # 确保返回空列表而不是None
            message=f"成功获取 {len(product_list)} 个产品"
        )

    except Exception as e:
        # ---------- 条件分支 ----------
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"查询产品列表失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"查询产品列表失败：{str(e)}"
        )


@router.post(
    "/client_data",
    response_model=PaginatedResponseBaseSchema[list[AdDataItemResponse]],
    summary="查询广告数据",
)
async def get_client_data(
        request: Request,
        background_tasks: BackgroundTasks,
        api_request: ClientDataRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    查询客户的广告数据
    
    参数说明：
    - client_id: 客户ID（必填）
    - req_time: 请求时间戳（必填）
    - data_type: 数据类型，'all' 表示详细数据，'day' 表示每日汇总，默认为 'all'
    - dimension: 统计维度（可选），'country' / 'ad_unit' / 'ad_unit_country'（'country_ad_unit' 为兼容别名）；不传则保持历史行为
    - start_date: 起始日期（格式：YYYY-MM-DD），可选，不提供则使用当前月第一天
    - end_date: 终止日期（格式：YYYY-MM-DD），可选，不提供则使用当前月最后一天
    - page / page_size: 分页参数（可选）；不传时默认第 1 页、每页 {CLIENT_API_DEFAULT_PAGE_SIZE} 条
    - sign: MD5签名（必填），包含所有非空参数
    
    返回说明：
    - data_type='all': 返回明细行；传入 dimension 时与后台「详细报表」口径一致
    - data_type='day': 返回日汇总；传入 dimension 时按维度分组，与后台「每日统计」一致
    - 未传 dimension：返回库中全部匹配行（兼容旧版；若同时存在国家/单元 API 数据可能重复统计，建议传 dimension）
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        try:
            parsed_dimension = ensure_valid_optional_dimension(api_request.dimension)
        except ValueError as exc:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=str(exc),
            )

        client = await verify_client_request(
            api_request,
            db,
            data_type=api_request.data_type,
            # 签名须与请求体原文一致；country_ad_unit 等别名在查询前才规范化
            dimension=api_request.dimension,
            start_date=api_request.start_date,
            end_date=api_request.end_date,
            page=api_request.page,
            page_size=api_request.page_size,
        )

        page = api_request.page or 1
        page_size = min(
            api_request.page_size or CLIENT_API_DEFAULT_PAGE_SIZE,
            CLIENT_API_MAX_PAGE_SIZE,
        )

        # 确定日期范围
        today = date.today()
        default_month_start = date(today.year, today.month, 1)
        _, last_day = monthrange(today.year, today.month)
        default_month_end = date(today.year, today.month, last_day)

        # ---------- 条件分支 ----------
        if api_request.start_date:
            # ---------- 异常处理 ----------
            try:
                start_date_obj = datetime.strptime(api_request.start_date, "%Y-%m-%d").date()
            except ValueError:
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail="起始日期格式错误，请使用 YYYY-MM-DD 格式"
                )
        else:
            # 未提供起始日期，使用当前月第一天
            start_date_obj = default_month_start

        # ---------- 条件分支 ----------
        if api_request.end_date:
            # ---------- 异常处理 ----------
            try:
                end_date_obj = datetime.strptime(api_request.end_date, "%Y-%m-%d").date()
            except ValueError:
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail="终止日期格式错误，请使用 YYYY-MM-DD 格式"
                )
        else:
            # 未提供终止日期，使用当前月最后一天
            end_date_obj = default_month_end

        # 验证日期范围
        # ---------- 条件分支 ----------
        if start_date_obj > end_date_obj:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="起始日期不能大于终止日期"
            )

        data_type = api_request.data_type or "all"
        if data_type not in ("all", "day"):
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="data_type 参数无效，仅支持 'all' 或 'day'",
            )

        raw_rows, total = await ClientAdDataQuery(db).fetch(
            client=client,
            start_date=start_date_obj,
            end_date=end_date_obj,
            data_type=data_type,
            dimension=parsed_dimension,
            page=page,
            page_size=page_size,
        )
        data_list = [AdDataItemResponse(**row) for row in raw_rows]

        logger.info(
            f"客户 {client.id} 查询广告数据（data_type={data_type}, dimension={parsed_dimension or '未指定'}, "
            f"{start_date_obj} 至 {end_date_obj}，page={page}, page_size={page_size}），"
            f"返回 {len(data_list)}/{total} 条记录"
        )

        username, user_full_name = await _get_client_user_names(db, client.user_id)
        client_ip = get_client_ip(request)

        telegram_msg = None
        if len(data_list) > 0:
            telegram_msg = (
                f"📡 API 数据获取成功\n\n"
                f"客户: {user_full_name}\n"
                f"数据类型: {data_type}\n"
            )
            if parsed_dimension:
                telegram_msg += f"统计维度: {parsed_dimension}\n"
            telegram_msg += f"✅ 成功获取: {len(data_list)}/{total} 条数据"
            if start_date_obj and end_date_obj:
                telegram_msg += (
                    f"\n日期范围: {start_date_obj.strftime('%Y-%m-%d')} 至 "
                    f"{end_date_obj.strftime('%Y-%m-%d')}"
                )
            if total > len(data_list):
                telegram_msg += f"\n分页: 第 {page} 页，每页 {page_size} 条"
            if client_ip:
                telegram_msg += f"\n来源IP: {client_ip}"

        background_tasks.add_task(
            _background_client_api_side_effects,
            action_type="API_ACCESS",
            user_id=client.user_id,
            username=username,
            resource_type="AD_DATA",
            resource_id=None,
            resource_name="广告数据",
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent", "")[:500],
            success=True,
            request_method=request.method,
            request_path=request.url.path,
            details={
                "client_id": client.id,
                "client_name": client.company_name,
                "data_count": len(data_list),
                "total_count": total,
                "page": page,
                "page_size": page_size,
                "date_range": {
                    "start": start_date_obj.isoformat(),
                    "end": end_date_obj.isoformat(),
                },
                "data_type": data_type,
                "dimension": parsed_dimension,
                "api_endpoint": "/client_data",
            },
            telegram_msg=telegram_msg,
        )

        return PaginatedResponseBaseSchema.success(
            data=data_list if data_list else [],
            total=total,
            page=page,
            page_size=page_size,
            message=f"成功获取 {len(data_list)} 条广告数据（共 {total} 条）",
        )

    except HTTPException:
        raise
    except Exception as e:
        # ---------- 条件分支 ----------
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"查询广告数据失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"查询广告数据失败：{str(e)}"
        )
