"""
客户API端点
提供客户通过API密钥访问的接口，包括：
- 查询所有产品名称
- 查询广告数据（默认当前月数据）

请求验证：
- 验证客户ID和API密钥（secret_key）
- 验证请求时间差异（10秒内）
- 验证MD5签名
"""
import hashlib
import logging
import asyncio
from calendar import monthrange
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.audit_log import log_user_action
from app.models.models import AdData, Client, Product, User, ProductAssignment
from sqlalchemy import func, and_, or_, text, literal_column, case
from app.schemas.base import ResponseBaseSchema
from app.core.query_utils import date_range_condition, check_use_assignment_table

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


# ====== 请求模型 ======
class ClientAPIBaseRequest(BaseModel):
    """客户API基础请求模型（所有接口共用）"""
    client_id: int = Field(..., description="客户ID")
    req_time: int = Field(..., description="请求时间戳（10位秒级）")
    sign: str = Field(..., description="MD5签名")


class ClientProductsRequest(ClientAPIBaseRequest):
    """查询产品信息请求模型"""
    pass


class ClientDataRequest(ClientAPIBaseRequest):
    """查询广告数据请求模型"""
    data_type: str = Field(..., description="数据类型：'all' 表示详细数据（按国家），'day' 表示每日汇总（按产品+日期）")
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
    country_code: str = Field(..., description="国家二字代码（ISO 3166-1 alpha-2）")
    country_name_zh: str = Field(default="", description="国家中文名称")
    request_count: int = Field(..., description="请求数（整数）")
    match_count: int = Field(..., description="匹配数（整数）")
    coverage_rate: float = Field(..., description="覆盖率（%，浮点数，保留2位小数）")
    display_count: int = Field(..., description="展示数（整数）")
    display_rate: float = Field(..., description="展示率（%，浮点数，保留2位小数）")
    click_count: int = Field(..., description="点击数（整数）")
    click_rate: float = Field(..., description="点击率（%，浮点数，保留2位小数）")
    pageviews: int = Field(..., description="PageViews（整数）")
    ecpm: float = Field(..., description="eCPM（减扣后的，浮点数，保留2位小数）")
    revenue: float = Field(..., description="收益（减扣后的，浮点数，保留2位小数）")

    class Config:
        from_attributes = True


# ====== 签名验证函数 ======
def verify_signature(
    client_id: int, 
    secret_key: str, 
    req_time: int, 
    sign: str,
    data_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None
) -> bool:
    """
    验证MD5签名
    
    签名算法：
    1. 按字母排序参数：client_id, data_type, end_date, req_time, start_date（只包含非空参数）
    2. 拼接：client_id=1000&data_type=all&req_time=1745656222&start_date=2024-01-01
    3. 在末尾追加：&key={SECRET_KEY}
    4. 最终字符串：client_id=1000&data_type=all&req_time=1745656222&start_date=2024-01-01&key=3716607b-04cb-4f71-91c0-2dae7a87fa63
    5. MD5加密并转为小写
    
    注意：
    - secret_key不通过请求传递，而是从数据库查询客户的key字段
    - 只包含非空参数参与签名计算
    - data_type默认为"all"，如果未提供则使用默认值
    """
    # 构建参数字典（只包含非空参数）
    params = {
        'client_id': str(client_id),
        'req_time': str(req_time)
    }
    
    # 添加可选参数（如果提供了的话）
    if data_type:
        params['data_type'] = str(data_type)
    if start_date:
        params['start_date'] = str(start_date)
    if end_date:
        params['end_date'] = str(end_date)

    # 按key排序并拼接
    sorted_keys = sorted(params.keys())
    temp_str = '&'.join([f"{key}={params[key]}" for key in sorted_keys])

    # 在末尾追加 &key={SECRET_KEY}
    temp_str = temp_str + f'&key={secret_key}'

    # MD5加密并转为小写
    calculated_sign = hashlib.md5(temp_str.encode('utf-8')).hexdigest().lower()

    # 比较签名（不区分大小写）
    return calculated_sign.lower() == sign.lower()


async def verify_client_request(
        request: ClientAPIBaseRequest,
        db: AsyncSession,
        data_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None
) -> Client:
    """
    验证客户请求
    1. 通过client_id查询客户（不暴露secret_key）
    2. 验证请求时间差异（正负5秒内）
    3. 使用客户的key验证签名
    """
    # 1. 通过client_id查询客户（secret_key不通过请求传递，从数据库获取）
    result = await db.execute(
        select(Client).where(
            Client.id == request.client_id,
            Client.is_active == True
        )
    )
    client = result.scalars().first()

    if not client:
        logger.warning(
            f"客户验证失败: client_id={request.client_id} 不存在或未激活"
        )
        raise_api_exception(
            ErrorCode.CLIENT_NOT_FOUND,
            detail="客户不存在或未激活"
        )
    
    # 检查API是否启用
    if not client.api_enabled:
        logger.warning(
            f"客户API访问被禁用: client_id={request.client_id}"
        )
        raise_api_exception(
            ErrorCode.CLIENT_API_VALIDATION_FAILED,
            detail="客户API访问未启用，请联系管理员开启"
        )

    # 2. 验证请求时间差异（正负5秒内）
    current_timestamp = int(datetime.now(timezone.utc).timestamp())
    time_diff = abs(current_timestamp - request.req_time)

    if time_diff > 5:
        logger.warning(
            f"请求时间验证失败: client_id={request.client_id}, "
            f"req_time={request.req_time}, current_time={current_timestamp}, diff={time_diff}秒"
        )
        raise_api_exception(
            ErrorCode.CLIENT_API_VALIDATION_FAILED,
            detail=f"请求时间差异过大（{time_diff}秒），请确保系统时间正确（允许正负5秒）"
        )

    # 3. 使用客户的key验证签名（secret_key从数据库获取，不通过请求传递）
    if not verify_signature(
            request.client_id,
            client.key,  # 使用从数据库查询到的key
            request.req_time,
            request.sign,
            data_type,
            start_date,
            end_date
    ):
        logger.warning(
            f"签名验证失败: client_id={request.client_id}, "
            f"sign={request.sign[:8]}... (前8位)"
        )
        raise_api_exception(
            ErrorCode.CLIENT_API_VALIDATION_FAILED,
            detail="签名验证失败"
        )

    logger.info(f"客户API请求验证成功: client_id={request.client_id}")
    return client


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
        try:
            # 获取客户关联的用户（如果有）- 使用轻量级查询只获取用户名
            user_id = client.user_id
            username = f"CLIENT_{client.id}"
            if client.user_id:
                user_result = await db.execute(
                    select(User.username).where(User.id == client.user_id)
                )
                user_username = user_result.scalar_one_or_none()
                if user_username:
                    username = user_username

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
    - data_type: 数据类型，'all' 表示详细数据（按国家），'day' 表示每日汇总（按产品+日期），默认为 'all'
    - start_date: 起始日期（格式：YYYY-MM-DD），可选，不提供则使用当前月第一天
    - end_date: 终止日期（格式：YYYY-MM-DD），可选，不提供则使用当前月最后一天
    - sign: MD5签名（必填），包含所有非空参数
    
    返回说明：
    - data_type='all': 返回详细数据，按国家分组
    - data_type='day': 返回每日汇总数据，按产品+日期汇总，国家显示"全部区域"
    """
    try:
        # 验证请求（传递额外的参数用于签名验证）
        client = await verify_client_request(
            api_request, 
            db,
            data_type=api_request.data_type,
            start_date=api_request.start_date,
            end_date=api_request.end_date
        )

        # 确定日期范围
        today = date.today()
        default_month_start = date(today.year, today.month, 1)
        _, last_day = monthrange(today.year, today.month)
        default_month_end = date(today.year, today.month, last_day)
        
        if api_request.start_date:
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
        
        if api_request.end_date:
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
        if start_date_obj > end_date_obj:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="起始日期不能大于终止日期"
            )

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(db)
        
        # 根据 data_type 决定查询逻辑（data_type 现在是必填参数）
        data_type = api_request.data_type
        
        if data_type == "day":
            # 每日汇总模式：按产品+日期汇总，国家显示"全部区域"
            from app.models.models import CountryInfo
            
            # 构建汇总查询
            # 注意：覆盖率、展示率、点击率、eCPM 不在查询中计算，而是在返回数据时根据汇总后的数值重新计算
            query = select(
                func.date(AdData.date).label("date"),
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                func.sum(AdData.request_count).label("request_count"),
                func.sum(AdData.match_count).label("match_count"),
                func.sum(AdData.display_count).label("display_count"),
                func.sum(AdData.click_count).label("click_count"),
                func.sum(AdData.pageviews).label("pageviews"),
                func.sum(AdData.revenue_after_deduct).label("revenue")
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
                query = query.where(ProductAssignment.client_id == client.id)
            else:
                # 旧的查询方式
                query = query.where(Product.client_id == client.id)
            
            # 应用日期范围过滤
            date_condition = date_range_condition(AdData.date, start_date_obj, end_date_obj)
            if date_condition is not None:
                query = query.where(date_condition)
            
            # 按产品ID和日期分组
            query = query.group_by(
                func.date(AdData.date),
                Product.id,
                Product.name
            ).order_by(
                func.date(AdData.date).asc(),
                Product.id.asc()
            )
            
            result = await db.execute(query)
            summary_data = result.all()
            
            # 转换为响应格式
            data_list = []
            for row in summary_data:
                date_obj = row.date if isinstance(row.date, date) else row.date.date()
                date_str = date_obj.isoformat()
                
                # 获取汇总后的数值
                total_request_count = int(row.request_count or 0)
                total_match_count = int(row.match_count or 0)
                total_display_count = int(row.display_count or 0)
                total_click_count = int(row.click_count or 0)
                total_pageviews = int(row.pageviews or 0)
                total_revenue = float(row.revenue or 0.0)
                
                # 根据汇总后的数值重新计算比率
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
                ecpm = round(
                    (total_revenue / total_display_count * 1000) if total_display_count > 0 else 0.0,
                    2
                )
                
                data_list.append(AdDataItemResponse(
                    date=date_str,
                    product_name=row.product_name or "",
                    country_code="ZZ",  # 每日汇总模式使用"ZZ"表示全部区域
                    country_name_zh="全部区域",  # 每日汇总模式统一显示"全部区域"
                    request_count=total_request_count,
                    match_count=total_match_count,
                    coverage_rate=float(coverage_rate),
                    display_count=total_display_count,
                    display_rate=float(display_rate),
                    click_count=total_click_count,
                    click_rate=float(click_rate),
                    pageviews=total_pageviews,
                    ecpm=float(ecpm),
                    revenue=round(total_revenue, 2)
                ))
        else:
            # 详细数据模式（data_type='all'）：按国家分组，保持原有逻辑
            from app.models.models import CountryInfo
            query = select(AdData, Product.name, CountryInfo.country_name_zh).join(
                Product, AdData.product_id == Product.id
            ).outerjoin(
                CountryInfo,
                AdData.country_code.collate('utf8mb4_unicode_ci') == 
                CountryInfo.alpha_2_code.collate('utf8mb4_unicode_ci')
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
                query = query.where(ProductAssignment.client_id == client.id)
            else:
                # 旧的查询方式
                query = query.where(Product.client_id == client.id)
            
            # 应用日期范围过滤
            date_condition = date_range_condition(AdData.date, start_date_obj, end_date_obj)
            if date_condition is not None:
                query = query.where(date_condition)
            query = query.order_by(AdData.date.asc())

            result = await db.execute(query)
            ad_data_list = result.all()

            # 转换为响应格式
            data_list = []
            for row in ad_data_list:
                # 解构数据：ad_data, product_name, country_name_zh
                if len(row) >= 3:
                    ad_data, product_name, country_name_zh = row
                elif len(row) >= 2:
                    ad_data, product_name = row
                    country_name_zh = None
                else:
                    continue
                # 格式化日期为ISO格式字符串
                date_obj = ad_data.date.date() if hasattr(ad_data.date, 'date') else ad_data.date
                date_str = date_obj.isoformat()

                # 使用数据库字段中的比率（如果为空则计算）
                coverage_rate = ad_data.coverage_rate if ad_data.coverage_rate is not None else round(
                    (ad_data.match_count / ad_data.request_count * 100)
                    if ad_data.request_count > 0 else 0.0,
                    2
                )
                display_rate = ad_data.display_rate if ad_data.display_rate is not None else round(
                    (ad_data.display_count / ad_data.match_count * 100)
                    if ad_data.match_count > 0 else 0.0,
                    2
                )
                click_rate = ad_data.click_rate if ad_data.click_rate is not None else round(
                    (ad_data.click_count / ad_data.display_count * 100)
                    if ad_data.display_count > 0 else 0.0,
                    2
                )

                # 处理国家代码和国家名称
                country_code_str = ad_data.country_code or ""
                
                if country_name_zh:
                    final_country_name = country_name_zh
                elif ad_data.country_code == "AA":
                    final_country_name = "未知区域"
                elif ad_data.country_code == "ZZ":
                    final_country_name = "全部区域"
                else:
                    final_country_name = ""

                # 确保所有数值类型正确
                data_list.append(AdDataItemResponse(
                    date=date_str,
                    product_name=product_name or "",
                    country_code=country_code_str,  # 返回二字国家代码
                    country_name_zh=final_country_name,
                    request_count=int(ad_data.request_count),
                    match_count=int(ad_data.match_count),
                    coverage_rate=float(coverage_rate),
                    display_count=int(ad_data.display_count),
                    display_rate=float(display_rate),
                    click_count=int(ad_data.click_count),
                    click_rate=float(click_rate),
                    pageviews=int(ad_data.pageviews or 0),
                    ecpm=float(round(ad_data.ecpm_after_deduct, 2)),
                    revenue=float(round(ad_data.revenue_after_deduct, 2))
                ))

        logger.info(
            f"客户 {client.id} 查询广告数据（data_type={data_type}, {start_date_obj} 至 {end_date_obj}），"
            f"返回 {len(data_list)} 条记录"
        )

        # 记录API访问日志
        try:
            # 获取客户关联的用户（如果有）- 使用轻量级查询只获取用户名
            user_id = client.user_id
            username = f"CLIENT_{client.id}"
            if client.user_id:
                user_result = await db.execute(
                    select(User.username).where(User.id == client.user_id)
                )
                user_username = user_result.scalar_one_or_none()
                if user_username:
                    username = user_username

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
                    "api_endpoint": "/client_data"
                }
            )
        except Exception as log_error:
            # 日志记录失败不应该影响API响应
            logger.warning(f"记录客户API访问日志失败: {log_error}")

        # 发送 Telegram 通知（仅在成功获取数据时）
        if len(data_list) > 0:
            from app.core.auto_bot import send_telegram_message
            
            # 获取用户全名
            user_full_name = f"CLIENT_{client.id}"
            if client.user_id:
                user_result = await db.execute(
                    select(User.full_name).where(User.id == client.user_id)
                )
                user_full_name_result = user_result.scalar_one_or_none()
                if user_full_name_result:
                    user_full_name = user_full_name_result
                # 如果全名为空，尝试使用用户名
                if not user_full_name or user_full_name == f"CLIENT_{client.id}":
                    user_result = await db.execute(
                        select(User.username).where(User.id == client.user_id)
                    )
                    user_username = user_result.scalar_one_or_none()
                    if user_username:
                        user_full_name = user_username
            
            # 构建通知消息
            telegram_msg = f"📡 API 数据获取成功\n\n"
            telegram_msg += f"客户: {user_full_name}\n"
            telegram_msg += f"数据类型: {data_type}\n"
            telegram_msg += f"✅ 成功获取: {len(data_list)} 条数据"
            
            if start_date_obj and end_date_obj:
                telegram_msg += f"\n日期范围: {start_date_obj.strftime('%Y-%m-%d')} 至 {end_date_obj.strftime('%Y-%m-%d')}"
            
            # 使用 await 发送消息，设置超时避免阻塞太久
            # send_telegram_message 内部已有完整的容错处理
            try:
                await asyncio.wait_for(
                    send_telegram_message(telegram_msg),
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

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"查询广告数据失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"查询广告数据失败：{str(e)}"
        )
