"""
工具函数模块

提供应用通用的工具函数，包括：
- 时间处理：时区转换、日期格式化、获取当前时间等
- 请求处理：获取客户端IP、设备类型检测、分页优化等
- 数据格式化：数字格式化、百分比计算、日期范围计算等
- 业务逻辑辅助：数据验证、计算辅助等

注意事项：
1. 所有时间相关函数都使用应用配置的时区（默认Asia/Shanghai）
2. 业务日期字段使用naive datetime（不带时区信息）
3. 时间戳字段使用带时区的datetime
4. 所有函数都包含完整的类型注解和文档字符串

模块级常量：
- APP_TIMEZONE: 应用时区对象（从settings.TIMEZONE读取）
- PERCENTAGE_MULTIPLIER: 百分比乘数常量（从constants模块导入）
"""
import ipaddress
import math
import uuid
import pytz
from datetime import date, datetime
from typing import Any, Optional
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.core.constants import PERCENTAGE_MULTIPLIER

# 应用时区配置（从统一配置读取）
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)


def get_device_type(request: Request) -> str:
    """
    获取设备类型
    返回: 'mobile', 'tablet', 'desktop'
    """
    user_agent = request.headers.get("User-Agent", "").lower()

    # 平板设备
    tablet_keywords = ['ipad', 'tablet', 'playbook', 'kindle']
    if any(keyword in user_agent for keyword in tablet_keywords):
        return 'tablet'

    # 移动设备
    mobile_keywords = [
        'mobile', 'android', 'iphone', 'ipod',
        'blackberry', 'windows phone', 'opera mini',
        'iemobile', 'palm', 'smartphone'
    ]
    if any(keyword in user_agent for keyword in mobile_keywords):
        return 'mobile'

    # 默认桌面设备
    return 'desktop'


def get_client_ip(request: Request) -> str:
    """
    从请求中获取客户端IP地址
    支持代理情况（X-Forwarded-For、X-Real-IP头）
    
    优先级：
    1. 可信代理覆盖写入的 X-Real-IP
    2. 可信代理覆盖写入的 X-Forwarded-For
    3. request.client.host（直接连接）
    
    Args:
        request: FastAPI请求对象
        
    Returns:
        客户端IP地址字符串，如果无法获取则返回"unknown"
    """
    try:
        from app.core.config import settings

        peer_ip = request.client.host if request.client else ""

        # ASGI Server 必须关闭自身 proxy_headers 解析，保留真实直连对端。
        # 仅当直连对端在可信代理白名单时，读取由 Nginx 覆盖写入的真实 IP 头。
        get_ips = getattr(settings, "get_trusted_proxy_ips", None)
        trusted_proxies = set(get_ips() if callable(get_ips) else [])
        if settings.TRUST_PROXY_HEADERS and peer_ip in trusted_proxies:
            candidates = [
                request.headers.get("CF-Connecting-IP"),
                request.headers.get("X-Real-IP"),
                # Nginx 已配置为覆盖而非追加；仍只接受首个合法值。
                (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip(),
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                try:
                    return str(ipaddress.ip_address(candidate.strip()))
                except ValueError:
                    continue

        if peer_ip:
            return peer_ip
        
        return "unknown"
    except (AttributeError, Exception):
        # 处理request.client为None或其他异常情况
        return "unknown"


def optimize_page_size_for_device(request: Request, page_size: int, default_page_size: int = 10) -> int:
    """
    根据设备类型优化分页大小
    桌面端：使用原始分页大小或默认值
    平板端：适当减小分页大小，限制最大值
    手机端：使用较小的分页大小，限制最大值
    
    Args:
        request: FastAPI请求对象
        page_size: 请求的分页大小
        default_page_size: 默认分页大小
        
    Returns:
        优化后的分页大小
    """
    device_type = get_device_type(request)

    # 如果使用默认值，根据设备类型调整
    if page_size == default_page_size:
        if device_type == 'desktop':
            # 桌面端保持默认值
            return default_page_size
        elif device_type == 'tablet':
            # 平板端：使用稍大的默认值
            return 15
        else:  # mobile
            # 手机端：使用较小的默认值
            return 10

    # 如果用户指定了分页大小，根据设备类型限制最大值
    if device_type == 'desktop':
        # 桌面端：允许较大的分页大小
        return min(page_size, 100)
    elif device_type == 'tablet':
        # 平板端：限制最大值为25
        return min(page_size, 25)
    else:  # mobile
        # 手机端：限制最大值为15
        return min(page_size, 15)


def truncate_to_2_decimal(value: float) -> float:
    """
    截断浮点数到两位小数（砍掉第三位及之后的所有数字）
    不使用四舍五入，直接向下截断
    
    Args:
        value: 要截断的浮点数
    
    Returns:
        截断到两位小数的浮点数
    """
    return math.floor(value * 100) / 100


def apply_deduct_ratio(amount: float, deduct_ratio: float) -> float:
    """
    按产品扣减比例计算扣后金额。

    扣减比例为 0 时保留原始金额的全部小数位；有扣减时截断到两位小数（不四舍五入）。
    """
    value = float(amount or 0)
    ratio = float(deduct_ratio or 0)
    if ratio <= 0:
        return value
    return truncate_to_2_decimal(value * (1 - ratio))


def get_date_range(date_obj: datetime | Any) -> tuple[datetime, datetime]:
    """
    获取日期范围（当天的开始和结束时间）。

    .. deprecated::
        AdData.date / TBSearchData.date 已改为 DATE 列，请改用 ``normalize_date_for_ad_data``。
    
    Args:
        date_obj: 日期对象（datetime 或 date 类型）
    
    Returns:
        (date_start, date_end): 当天的开始和结束时间
    """
    if isinstance(date_obj, datetime):
        date_start = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_obj.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        date_start = datetime.combine(date_obj, datetime.min.time())
        date_end = datetime.combine(date_obj, datetime.max.time())
    return date_start, date_end


def normalize_date_for_ad_data(date_obj: datetime | Any):
    """
    规范化日期对象用于 AdData（DATE 列，返回 date 类型）

    Args:
        date_obj: 日期对象（datetime 或 date 类型）

    Returns:
        date: 日历日期
    """
    from datetime import date as date_type

    if isinstance(date_obj, datetime):
        return date_obj.date()
    if isinstance(date_obj, date_type):
        return date_obj
    if hasattr(date_obj, "date"):
        return date_obj.date()
    return date_obj


def get_app_now() -> datetime:
    """
    获取应用时区的当前时间
    
    无论系统使用什么时区（UTC 或本地时间），都返回应用配置时区（默认北京时间）的当前时间
    
    Returns:
        datetime: 应用时区的当前时间（带时区信息）
    """
    return datetime.now(APP_TIMEZONE)


def get_app_now_naive() -> datetime:
    """
    获取应用时区的当前时间（naive datetime，不带时区信息）
    
    用于业务日期字段，与数据库存储格式一致
    
    Returns:
        datetime: 应用时区的当前时间（naive，不带时区信息）
    """
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


def parse_date_to_app_timezone(date_str: str, is_end_date: bool = False) -> datetime:
    """
    将日期字符串解析为应用时区的datetime（naive）
    
    用于日期范围查询，确保与数据库中的时间（北京时间naive）一致
    
    Args:
        date_str: 日期字符串（YYYY-MM-DD格式）
        is_end_date: 是否为结束日期（如果是，设置为23:59:59，否则为00:00:00）
    
    Returns:
        datetime: 应用时区的datetime（naive，不带时区信息）
    
    Example:
        parse_date_to_app_timezone("2024-01-01", False) -> 2024-01-01 00:00:00
        parse_date_to_app_timezone("2024-01-01", True) -> 2024-01-01 23:59:59
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if is_end_date:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt


def get_product_name(product: Optional[Any], product_id: Optional[int] = None, default: str = "未知产品") -> str:
    """
    获取产品名称，处理 None 情况
    
    Args:
        product: 产品对象（可能为 None）
        product_id: 产品ID（用于构建 fallback 名称）
        default: 默认名称（默认为 "未知产品"）
    
    Returns:
        产品名称字符串
    
    Example:
        product_name = get_product_name(product, tb_data.product_id)
        # -> product.name if product else "未知产品(ID:123)"
    """
    if product and hasattr(product, 'name') and product.name:
        return product.name
    elif product_id:
        return f"{default}(ID:{product_id})"
    else:
        return default


def normalize_ad_unit(value: Any = None) -> str:
    """将广告单元规范为空字符串或去首尾空格后的文本（空值统一为 ''）。"""
    if value is None:
        return ''
    text = str(value).strip()
    return text


def get_client_name(client: Optional[Any], default: str = "未知客户") -> str:
    """
    获取客户名称，处理 None 情况
    
    Args:
        client: 客户对象（可能为 None）
        default: 默认名称（默认为 "未知客户"）
    
    Returns:
        客户名称字符串
    
    Example:
        client_name = get_client_name(client)
        # -> client.company_name if client else "未知客户"
    """
    if client and hasattr(client, 'company_name') and client.company_name:
        return client.company_name
    else:
        return default


def get_user_name(user: Optional[Any], default: str = "未知用户") -> str:
    """
    获取用户名称，优先使用 full_name，否则使用 username
    
    Args:
        user: 用户对象（可能为 None）
        default: 默认名称（默认为 "未知用户"）
    
    Returns:
        用户名称字符串
    
    Example:
        user_name = get_user_name(user)
        # -> user.full_name or user.username if user else "未知用户"
    """
    if user:
        if hasattr(user, 'full_name') and user.full_name:
            return user.full_name
        elif hasattr(user, 'username') and user.username:
            return user.username
    return default


async def get_user_name_by_id(
    db: AsyncSession,
    user_id: int | None,
    default_prefix: str = "CLIENT",
    prefer_full_name: bool = True
) -> str:
    """
    根据用户ID异步获取用户名称（优先使用 full_name，否则使用 username）
    
    用于需要从数据库查询用户信息的场景（如日志记录、通知等）
    
    Args:
        db: 数据库会话
        user_id: 用户ID（可能为 None）
        default_prefix: 默认名称前缀（默认为 "CLIENT"），如果用户ID为None，返回 f"{default_prefix}_None"
        prefer_full_name: 是否优先使用 full_name（默认True），如果为False，只查询 username
    
    Returns:
        用户名称字符串
    
    Example:
        username = await get_user_name_by_id(db, client.user_id, "CLIENT")
        # -> 如果 user_id 为 None，返回 "CLIENT_None"
        # -> 如果查询到用户，返回 full_name 或 username
    """
    if not user_id:
        return f"{default_prefix}_None"
    
    from sqlalchemy.future import select
    from app.models.models import User
    
    try:
        if prefer_full_name:
            # 优先查询 full_name
            result = await db.execute(
                select(User.full_name).where(User.id == user_id)
            )
            full_name = result.scalar_one_or_none()
            if full_name:
                return full_name
        
        # 如果 prefer_full_name 为 False 或 full_name 为空，查询 username
        result = await db.execute(
            select(User.username).where(User.id == user_id)
        )
        username = result.scalar_one_or_none()
        if username:
            return username
        
        # 如果都查询不到，返回默认值
        return f"{default_prefix}_{user_id}"
    except Exception:
        # 查询失败时返回默认值
        return f"{default_prefix}_{user_id}"


def format_error_details(errors: list[Any], row_prefix: str = "第", row_suffix: str = "行") -> list[str]:
    """
    格式化错误详情列表
    
    Args:
        errors: 错误列表，每个错误可以是字典或字符串
        row_prefix: 行号前缀（默认为 "第"）
        row_suffix: 行号后缀（默认为 "行"）
    
    Returns:
        格式化后的错误详情列表
    
    Example:
        errors = [{"row": 5, "error": "产品不存在"}, "其他错误"]
        error_details = format_error_details(errors)
        # -> ["第5行: 产品不存在", "其他错误"]
    """
    error_details = []
    for error in errors:
        if isinstance(error, dict):
            row = error.get('row', '?')
            error_msg = error.get('error', '未知错误')
            error_details.append(f"{row_prefix}{row}{row_suffix}: {error_msg}")
        else:
            error_details.append(str(error))
    return error_details


async def find_or_create_default_client(
    db: AsyncSession,
    user_id: int,
    default_name: str = "临时挂靠"
) -> Any:
    """
    查找或创建「临时挂靠」客户（用于导入/删除产品时挂靠未归属数据）
    
    查找逻辑：
    1. 首先在数据库中查找
    2. 如果数据库中没有，检查会话中是否有待提交的对象
    3. 如果都没有，创建新的临时挂靠客户
    
    Args:
        db: 数据库会话
        user_id: 用户ID（用于创建新客户时关联）
        default_name: 临时挂靠客户名称（默认为 "临时挂靠"）
    
    Returns:
        客户对象（Client）
    
    Example:
        >>> from app.models.models import Client
        default_client = await find_or_create_default_client(db, current_user.id)
    """
    # 延迟导入，避免循环导入
    from app.models.models import Client
    
    # 步骤1: 先查找数据库中的临时挂靠客户
    client_query = select(Client).where(Client.company_name == default_name).limit(1)
    client_result = await db.execute(client_query)
    default_client = client_result.scalars().first()
    
    if default_client:
        return default_client
    
    # 步骤2: 检查会话中是否已经有待提交的临时挂靠客户对象
    pending_default_client = None
    try:
        # 检查会话中的新对象（待提交的对象）
        for obj in db.new:
            if isinstance(obj, Client) and obj.company_name == default_name:
                pending_default_client = obj
                break
    except AttributeError:
        # 如果 db.new 不可用，尝试使用 identity_map
        try:
            for obj in db.identity_map.values():
                if isinstance(obj, Client) and obj.company_name == default_name:
                    pending_default_client = obj
                    break
        except AttributeError:
            pass
    
    if pending_default_client:
        return pending_default_client
    
    # 步骤3: 如果确实没有找到，创建新的临时挂靠客户
    client_key = str(uuid.uuid4())
    default_client = Client(
        user_id=user_id,
        key=client_key,  # 必需字段：客户唯一标识UUID
        company_name=default_name,
        is_active=True
    )
    db.add(default_client)
    await db.flush()  # 刷新以获取客户ID
    await db.refresh(default_client)
    
    return default_client


def unpack_ad_data_query_result(
    row: tuple,
    use_assignment_table: bool
) -> tuple[Any, Any, Any, Any, Any | None, Any | None]:
    """
    解包广告数据查询结果，统一处理不同查询结构
    
    Args:
        row: 查询结果行（tuple）
        use_assignment_table: 是否使用 ProductAssignment 表
    
    Returns:
        (ad_data, product, client, user, assignment_or_none, country_info_or_none)
        - assignment_or_none: 如果使用 ProductAssignment 表，返回 assignment，否则为 None
        - country_info_or_none: CountryInfo 对象，如果不存在则为 None
    
    Example:
        ad_data, product, client, user, assignment, country_info = unpack_ad_data_query_result(row, use_assignment_table)
    """
    if use_assignment_table:
        # 使用ProductAssignment表时，返回6个对象（包含CountryInfo）
        if len(row) >= 6:
            return row[0], row[1], row[2], row[3], row[4], row[5]
        elif len(row) >= 5:
            # 兼容旧数据（没有CountryInfo）
            return row[0], row[1], row[2], row[3], row[4], None
        else:
            # 数据不完整
            raise ValueError(f"数据不完整，期望至少5个对象，实际得到{len(row)}个")
    else:
        # 不使用ProductAssignment表时，返回5个对象（包含CountryInfo）
        if len(row) >= 5:
            return row[0], row[1], row[2], row[3], None, row[4]
        elif len(row) >= 4:
            # 兼容旧数据（没有CountryInfo）
            return row[0], row[1], row[2], row[3], None, None
        else:
            # 数据不完整
            raise ValueError(f"数据不完整，期望至少4个对象，实际得到{len(row)}个")


def calculate_coverage_rate(
    match_count: int | float,
    request_count: int | float,
    stored_rate: float | None = None,
    decimals: int = 2
) -> float:
    """
    计算覆盖率（匹配率）= 匹配数/请求数 * 100
    
    Args:
        match_count: 匹配数
        request_count: 请求数
        stored_rate: 存储的比率值（如果存在则优先使用）
        decimals: 小数位数（默认为2）
    
    Returns:
        覆盖率（百分比）
    """
    if stored_rate is not None:
        return round(float(stored_rate), decimals)
    if request_count > 0:
        return round((match_count / request_count * PERCENTAGE_MULTIPLIER), decimals)
    return 0.0


def calculate_display_rate(
    display_count: int | float,
    match_count: int | float,
    stored_rate: float | None = None,
    decimals: int = 2
) -> float:
    """
    计算展示率 = 展示数/匹配数 * 100
    
    Args:
        display_count: 展示数
        match_count: 匹配数
        stored_rate: 存储的比率值（如果存在则优先使用）
        decimals: 小数位数（默认为2）
    
    Returns:
        展示率（百分比）
    """
    if stored_rate is not None:
        return round(float(stored_rate), decimals)
    if match_count > 0:
        return round((display_count / match_count * PERCENTAGE_MULTIPLIER), decimals)
    return 0.0


def calculate_click_rate(
    click_count: int | float,
    display_count: int | float,
    stored_rate: float | None = None,
    decimals: int = 2
) -> float:
    """
    计算点击率 = 点击数/展示数 * 100
    
    Args:
        click_count: 点击数
        display_count: 展示数
        stored_rate: 存储的比率值（如果存在则优先使用）
        decimals: 小数位数（默认为2）
    
    Returns:
        点击率（百分比）
    """
    if stored_rate is not None:
        return round(float(stored_rate), decimals)
    if display_count > 0:
        return round((click_count / display_count * PERCENTAGE_MULTIPLIER), decimals)
    return 0.0


def build_import_message(
    imported_rows: int = 0,
    failed_rows: int = 0,
    new_rows: int = 0,
    updated_rows: int = 0,
    duplicate_rows: int = 0,
    separator: str = "，",
    default_message: str = "导入完成"
) -> str:
    """
    构建导入操作的消息字符串
    
    Args:
        imported_rows: 成功导入的行数
        failed_rows: 失败的行数
        new_rows: 新增的行数
        updated_rows: 更新的行数
        duplicate_rows: 重复的行数
        separator: 消息部分之间的分隔符（默认为"，"）
        default_message: 如果没有统计信息时的默认消息
    
    Returns:
        构建好的消息字符串
    
    Example:
        build_import_message(imported_rows=10, new_rows=8, updated_rows=2)
        # -> "导入完成: 成功 10 条，新增 8 条，更新 2 条"
    """
    message_parts = []
    
    if imported_rows > 0:
        message_parts.append(f"导入完成: 成功 {imported_rows} 条")
    if new_rows > 0:
        message_parts.append(f"新增 {new_rows} 条")
    if updated_rows > 0:
        message_parts.append(f"更新 {updated_rows} 条")
    if duplicate_rows > 0:
        message_parts.append(f"Excel内部重复 {duplicate_rows} 条")
    if failed_rows > 0:
        message_parts.append(f"失败 {failed_rows} 条")
    
    return separator.join(message_parts) if message_parts else default_message