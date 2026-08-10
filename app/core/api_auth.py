"""
下游（客户/渠道）开放 API 认证工具。

职责：校验 client_id + 时间戳 + MD5 签名，防止重放与参数篡改。

在系统中的位置：``app.core.api_auth``，由 ``app.api_v1`` 客户数据导出等开放接口调用。
"""
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import CLIENT_API_TIME_TOLERANCE_SECONDS
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import Client

logger = logging.getLogger(__name__)


def _build_sign_string(
    client_id: int,
    secret_key: str,
    req_time: int,
    data_type: str | None = None,
    dimension: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> str:
    """构建待签名字符串（MD5 与 HMAC-SHA256 共用）。"""
    params = {
        "client_id": str(client_id),
        "req_time": str(req_time),
    }
    if data_type:
        params["data_type"] = str(data_type)
    if dimension:
        params["dimension"] = str(dimension)
    if start_date:
        params["start_date"] = str(start_date)
    if end_date:
        params["end_date"] = str(end_date)
    if page is not None:
        params["page"] = str(page)
    if page_size is not None:
        params["page_size"] = str(page_size)

    sorted_keys = sorted(params.keys())
    temp_str = "&".join([f"{key}={params[key]}" for key in sorted_keys])
    return temp_str + f"&key={secret_key}"


def verify_signature(
    client_id: int, 
    secret_key: str, 
    req_time: int, 
    sign: str,
    data_type: str | None = None,
    dimension: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> bool:
    """
    验证MD5签名
    
    签名算法：
    1. 按字母排序参数：client_id, data_type, dimension, end_date, page, page_size, req_time, start_date（只包含非空参数）
    2. 拼接：client_id=1000&data_type=all&req_time=1745656222&start_date=2024-01-01
    3. 在末尾追加：&key={SECRET_KEY}
    4. 最终字符串：client_id=1000&data_type=all&req_time=1745656222&start_date=2024-01-01&key=3716607b-04cb-4f71-91c0-2dae7a87fa63
    5. MD5 或 HMAC-SHA256 加密并转为小写
    
    注意：
    - secret_key 不通过请求传递，而是从数据库查询客户的 key 字段
    - 只包含非空参数参与签名计算
    - page / page_size 仅在请求体显式传入时参与签名
    
    Args:
        client_id: 客户ID
        secret_key: 客户密钥（从数据库获取）
        req_time: 请求时间戳
        sign: 请求签名
        data_type: 数据类型（可选）
        dimension: 统计维度（可选，country / ad_unit / ad_unit_country / all；country_ad_unit 为兼容别名）
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）
        page: 页码（可选，显式传入时参与签名）
        page_size: 每页条数（可选，显式传入时参与签名）
    
    Returns:
        bool: 签名是否有效
    """
    sign_string = _build_sign_string(
        client_id, secret_key, req_time, data_type, dimension, start_date, end_date,
        page, page_size,
    )

    provided = (sign or "").lower()

    # HMAC-SHA256（推荐）
    hmac_sign = hmac.new(
        secret_key.encode("utf-8"),
        sign_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().lower()
    if hmac.compare_digest(hmac_sign, provided):
        return True

    # MD5（向后兼容；未配置时生产默认关闭，开发默认开启；可用 CLIENT_API_ALLOW_MD5 显式覆盖）
    try:
        from app.core.config import settings
        allow_md5 = bool(getattr(settings, "CLIENT_API_ALLOW_MD5", True))
    except Exception:
        # 配置读取失败时必须拒绝弱签名，避免异常路径重新放开 MD5。
        logger.exception("读取 CLIENT_API_ALLOW_MD5 配置失败，已拒绝 MD5 签名")
        allow_md5 = False
    if not allow_md5:
        return False
    calculated_sign = hashlib.md5(sign_string.encode("utf-8")).hexdigest().lower()
    return hmac.compare_digest(calculated_sign, provided)


async def verify_client_request(
    request: any,  # ClientAPIBaseRequest 类型
    db: AsyncSession,
    data_type: str | None = None,
    dimension: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
    time_tolerance: int = CLIENT_API_TIME_TOLERANCE_SECONDS,
) -> Client:
    """
    验证客户请求
    1. 通过 client_id 查询客户（不暴露 secret_key）
    2. 验证请求时间差异（默认正负 15 秒内）
    3. 使用客户的 key 验证签名
    
    Args:
        request: 客户 API 请求对象（包含 client_id, req_time, sign 等字段）
        db: 数据库会话
        data_type: 数据类型（可选，用于签名验证）
        dimension: 统计维度（可选，用于签名验证）
        start_date: 开始日期（可选，用于签名验证）
        end_date: 结束日期（可选，用于签名验证）
        page: 页码（可选，显式传入时参与签名验证）
        page_size: 每页条数（可选，显式传入时参与签名验证）
        time_tolerance: 时间容差（秒），默认 15 秒
    
    Returns:
        Client: 验证通过的客户对象
    
    Raises:
        HTTPException: 验证失败时抛出异常
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

    # 2. 验证请求时间差异（默认正负 15 秒内）
    current_timestamp = int(datetime.now(timezone.utc).timestamp())
    time_diff = abs(current_timestamp - request.req_time)

    if time_diff > time_tolerance:
        logger.warning(
            f"请求时间验证失败: client_id={request.client_id}, "
            f"req_time={request.req_time}, current_time={current_timestamp}, diff={time_diff}秒"
        )
        raise_api_exception(
            ErrorCode.CLIENT_API_VALIDATION_FAILED,
            detail=f"请求时间差异过大（{time_diff}秒），请检查系统时间"
        )

    # 3. 验证签名
    if not verify_signature(
        client_id=request.client_id,
        secret_key=client.key,
        req_time=request.req_time,
        sign=request.sign,
        data_type=data_type,
        dimension=dimension,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    ):
        logger.warning(
            f"签名验证失败: client_id={request.client_id}"
        )
        raise_api_exception(
            ErrorCode.CLIENT_API_VALIDATION_FAILED,
            detail="签名验证失败，请检查签名参数"
        )

    return client
