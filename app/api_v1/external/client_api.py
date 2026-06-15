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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.api_auth import verify_client_request
from app.core.audit_log import log_user_action, commit_audit_log
from app.core.telegram import send_telegram_message_async
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.utils import get_user_name_by_id
from app.models.models import Product
from app.schemas.base import ResponseBaseSchema
from app.services.ad_data.queries.client_api_query import ClientAdDataQuery
from app.services.ad_data.queries.dimension_filter import ensure_valid_optional_dimension

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


# ====== 请求模型 ======
class ClientAPIBaseRequest(BaseModel):
    """
    客户 API 基础请求模型（所有对外接口共用）。

    字段：client_id、req_time（10 位秒级时间戳）、sign（MD5 签名）。
    服务端校验时间差 ≤10 秒且签名与 secret_key 匹配。
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

    class Config:
        """Pydantic 配置：允许从 SQLAlchemy ORM 对象构造响应实例。"""
        from_attributes = True


class AdDataItemResponse(BaseModel):
    """
    广告数据项响应模型
    
    注意：此模型设计考虑了Java客户端的兼容性：
    - 所有数值类型明确（int/float），不会返回字符串
    - 日期格式为ISO标准格式（YYYY-MM-DD）
    - 字符串字段确保不为null（空字符串代替）
    - 浮点数保留2位小数，避免精度问题
    """
    date: str = Field(..., description="数据日期（ISO格式：YYYY-MM-DD）")
    product_name: str = Field(..., description="产品名称")
    ad_unit: str = Field(default="", description="广告单元（可为空）")
    country_code: str = Field(..., description="国家二字代码（ISO 3166-1 alpha-2）")
    country_name_zh: str = Field(default="", description="国家中文名称")
    request_count: int = Field(..., description="请求数（整数）")
    match_count: int = Field(..., description="匹配数（整数）")
    coverage_rate: float = Field(..., description="覆盖率（%，浮点数，保留2位小数）")
    display_count: int = Field(..., description="展示数（整数）")
    display_rate: float = Field(..., description="展示率（%，浮点数，保留2位小数）")
    click_count: int = Field(..., description="点击数（整数）")
    click_rate: float = Field(..., description="点击率（%，浮点数，保留2位小数）")
    viewability_rate: float = Field(default=0.0, description="可见率（%，浮点数，保留2位小数）")
    cpc: float = Field(..., description="CPC（浮点数，保留2位小数）")
    pageviews: int = Field(..., description="PageViews（整数）")
    ecpm: float = Field(..., description="eCPM（减扣后的，浮点数，保留2位小数）")
    revenue: float = Field(..., description="收益（减扣后的，浮点数，保留2位小数）")

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

        # 记录API访问日志
        # ---------- 异常处理 ----------
        try:
            # 获取客户关联的用户名（如果有）
            user_id = client.user_id
            username = await get_user_name_by_id(db, client.user_id, "CLIENT", prefer_full_name=False)

            await log_user_action(
                db=db,
                action_type="API_ACCESS",
                user_id=user_id,
                username=username,
                resource_type="PRODUCT",
                resource_id=None,
                resource_name="产品列表",
                request=request,
                success=True,
                details={
                    "client_id": client.id,
                    "client_name": client.company_name,
                    "product_count": len(product_list),
                    "api_endpoint": "/client_products"
                }
            )
            await commit_audit_log(db)
        except Exception as log_error:
            # 日志记录失败不应该影响API响应
            logger.warning(f"记录客户API访问日志失败: {log_error}")

        # 确保data字段不为None（Java客户端兼容性）
        # 如果列表为空，返回空列表[]而不是None
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


@router.post("/client_data", response_model=ResponseBaseSchema[list[AdDataItemResponse]], summary="查询广告数据")
async def get_client_data(
        request: Request,
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
            dimension=parsed_dimension,
            start_date=api_request.start_date,
            end_date=api_request.end_date
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

        raw_rows = await ClientAdDataQuery(db).fetch(
            client=client,
            start_date=start_date_obj,
            end_date=end_date_obj,
            data_type=data_type,
            dimension=parsed_dimension,
        )
        data_list = [AdDataItemResponse(**row) for row in raw_rows]

        logger.info(
            f"客户 {client.id} 查询广告数据（data_type={data_type}, dimension={parsed_dimension or '未指定'}, "
            f"{start_date_obj} 至 {end_date_obj}），"
            f"返回 {len(data_list)} 条记录"
        )

        # 记录API访问日志
        # ---------- 异常处理 ----------
        try:
            # 获取客户关联的用户名（如果有）
            user_id = client.user_id
            username = await get_user_name_by_id(db, client.user_id, "CLIENT", prefer_full_name=False)

            await log_user_action(
                db=db,
                action_type="API_ACCESS",
                user_id=user_id,
                username=username,
                resource_type="AD_DATA",
                resource_id=None,
                resource_name="广告数据",
                request=request,
                success=True,
                details={
                    "client_id": client.id,
                    "client_name": client.company_name,
                    "data_count": len(data_list),
                    "date_range": {
                        "start": start_date_obj.isoformat(),
                        "end": end_date_obj.isoformat()
                    },
                    "data_type": data_type,
                    "dimension": parsed_dimension,
                    "api_endpoint": "/client_data"
                }
            )
            await commit_audit_log(db)
        except Exception as log_error:
            # 日志记录失败不应该影响API响应
            logger.warning(f"记录客户API访问日志失败: {log_error}")

        # 发送 Telegram 通知（仅在成功获取数据时）
        # ---------- 条件分支 ----------
        if len(data_list) > 0:

            # 获取用户全名（优先使用 full_name，否则使用 username）
            user_full_name = await get_user_name_by_id(db, client.user_id, "CLIENT", prefer_full_name=True)

            # 构建通知消息
            telegram_msg = f"📡 API 数据获取成功\n\n"
            telegram_msg += f"客户: {user_full_name}\n"
            telegram_msg += f"数据类型: {data_type}\n"
            if parsed_dimension:
                telegram_msg += f"统计维度: {parsed_dimension}\n"
            telegram_msg += f"✅ 成功获取: {len(data_list)} 条数据"

            # ---------- 条件分支 ----------
            if start_date_obj and end_date_obj:
                telegram_msg += f"\n日期范围: {start_date_obj.strftime('%Y-%m-%d')} 至 {end_date_obj.strftime('%Y-%m-%d')}"

            # 使用 await 发送消息，设置超时避免阻塞太久
            # send_telegram_message 内部已有完整的容错处理
            # ---------- 异常处理 ----------
            try:
                await asyncio.wait_for(
                    send_telegram_message_async(telegram_msg),
                    timeout=5.0
                )
                logger.info(f"Telegram 通知发送成功，客户: {user_full_name}, 数据条数: {len(data_list)}")
            except asyncio.TimeoutError:
                logger.warning(f"发送 Telegram 通知超时，客户: {user_full_name}")
            # 其他异常已在 send_telegram_message 内部处理，这里不需要捕获

        # 确保data字段不为None（Java客户端兼容性）
        # 如果列表为空，返回空列表[]而不是None
        return ResponseBaseSchema.success(
            data=data_list if data_list else [],  # 确保返回空列表而不是None
            message=f"成功获取 {len(data_list)} 条广告数据"
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
