"""
输入验证和清理工具模块

功能说明：
提供安全的输入验证、清理和规范化功能，包括：
- 用户输入验证：用户名、邮箱、手机号（支持多国家格式）、密码强度等
- 安全检测：SQL注入检测、XSS攻击检测
- 文本清理：HTML转义、长度限制、规范化处理
- 特殊格式验证：Cron表达式、Postback URL占位符等

手机号验证特性：
- 支持20+个国家的手机号格式验证
- 根据ISO 3166-1二字母国家代码自动选择验证规则
- 自动清理格式字符（空格、+、-、括号等）
- 未指定国家时使用国际标准格式（8-15位数字）
- 向后兼容：默认使用中国大陆格式（如果未指定国家）

安全特性：
1. SQL注入防护：
   - 检测常见的SQL注入关键字（SELECT, INSERT, UPDATE等）
   - 检测危险字符（引号、分号、注释符号等）
   - 记录可疑的SQL注入尝试

2. XSS攻击防护：
   - 检测脚本标签（<script>, <iframe>等）
   - 检测JavaScript协议（javascript:）
   - 检测事件处理器（onerror=, onclick=等）
   - 自动HTML转义（sanitize_input函数）

3. 输入规范化：
   - 去除前后空格
   - 大小写转换
   - 长度限制
   - 特殊字符处理

使用场景：
- API端点参数验证
- 用户注册/登录表单验证
- 定时任务Cron表达式验证
- Postback URL占位符验证
- 数据导入前的验证

注意事项：
1. 所有用户输入都应该经过验证和清理
2. 密码验证遵循bcrypt限制（最大72字节）
3. SQL注入和XSS检测仅用于警告，实际防护依赖参数化查询和HTML转义
4. Postback URL占位符验证确保只使用系统支持的变量
"""
import re
# Python 3.10+ 使用内置类型注解
from html import escape
import logging

logger = logging.getLogger(__name__)

# ====== 正则表达式模式 ======
# 用户名：字母、数字、下划线，3-20个字符
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{3,20}$')

# 邮箱：标准邮箱格式
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# ====== 手机号格式规则（按国家代码） ======
# 定义不同国家的手机号格式验证规则
# 格式：ISO 3166-1 二字母代码 -> 正则表达式模式
PHONE_PATTERNS = {
    # 中国大陆（CN）：11位数字，1开头，第二位3-9
    'CN': re.compile(r'^1[3-9]\d{9}$'),
    # 美国（US）：10位数字（不含国家代码）
    'US': re.compile(r'^\d{10}$'),
    # 英国（GB）：11位数字，0开头
    'GB': re.compile(r'^0\d{10}$'),
    # 日本（JP）：10-11位数字
    'JP': re.compile(r'^\d{10,11}$'),
    # 韩国（KR）：10-11位数字
    'KR': re.compile(r'^\d{10,11}$'),
    # 印度（IN）：10位数字
    'IN': re.compile(r'^\d{10}$'),
    # 德国（DE）：10-11位数字
    'DE': re.compile(r'^\d{10,11}$'),
    # 法国（FR）：10位数字
    'FR': re.compile(r'^\d{10}$'),
    # 意大利（IT）：10位数字
    'IT': re.compile(r'^\d{10}$'),
    # 西班牙（ES）：9位数字
    'ES': re.compile(r'^\d{9}$'),
    # 加拿大（CA）：10位数字（与美国相同）
    'CA': re.compile(r'^\d{10}$'),
    # 澳大利亚（AU）：10位数字
    'AU': re.compile(r'^\d{10}$'),
    # 巴西（BR）：10-11位数字
    'BR': re.compile(r'^\d{10,11}$'),
    # 俄罗斯（RU）：10位数字
    'RU': re.compile(r'^\d{10}$'),
    # 墨西哥（MX）：10位数字
    'MX': re.compile(r'^\d{10}$'),
    # 印度尼西亚（ID）：10-12位数字
    'ID': re.compile(r'^\d{10,12}$'),
    # 泰国（TH）：9-10位数字
    'TH': re.compile(r'^\d{9,10}$'),
    # 越南（VN）：9-10位数字
    'VN': re.compile(r'^\d{9,10}$'),
    # 菲律宾（PH）：10-11位数字
    'PH': re.compile(r'^\d{10,11}$'),
    # 马来西亚（MY）：10-11位数字
    'MY': re.compile(r'^\d{10,11}$'),
    # 新加坡（SG）：8位数字
    'SG': re.compile(r'^\d{8}$'),
    # 中国香港（HK）：8位数字
    'HK': re.compile(r'^\d{8}$'),
    # 中国台湾（TW）：9-10位数字
    'TW': re.compile(r'^\d{9,10}$'),
}

# 默认手机号格式（如果国家代码未指定或不支持）：允许8-15位数字（国际标准）
DEFAULT_PHONE_PATTERN = re.compile(r'^\d{8,15}$')

# 向后兼容：保留原有的中国大陆手机号模式
PHONE_PATTERN = PHONE_PATTERNS['CN']

# SQL注入危险字符模式（用于检测）
SQL_INJECTION_PATTERNS = [
    re.compile(r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|SCRIPT)\b)', re.IGNORECASE),
    re.compile(r'(\'|"|;|--|/\*|\*/)', re.IGNORECASE),
]

# XSS危险字符模式（用于检测）
XSS_PATTERNS = [
    re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<iframe[^>]*>.*?</iframe>', re.IGNORECASE | re.DOTALL),
    re.compile(r'javascript:', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),  # onerror=, onclick= 等
]


def validate_username(username: str) -> tuple[bool, str | None]:
    """
    验证用户名格式
    
    参数:
        username: 用户名字符串
    
    返回:
        (是否有效, 错误信息)
    """
    if not username:
        return False, "用户名不能为空"

    if len(username) < 2:
        return False, "用户名至少需要3个字符"

    if len(username) > 20:
        return False, "用户名不能超过20个字符"

    if not USERNAME_PATTERN.match(username):
        return False, "用户名只能包含字母、数字和下划线"

    return True, None


def validate_email(email: str) -> tuple[bool, str | None]:
    """
    验证邮箱格式
    
    参数:
        email: 邮箱地址
    
    返回:
        (是否有效, 错误信息)
    """
    if not email:
        return False, "邮箱不能为空"

    if len(email) > 100:
        return False, "邮箱地址过长"

    if not EMAIL_PATTERN.match(email):
        return False, "邮箱格式不正确"

    return True, None


def validate_phone(phone: str, country_code: str | None = None) -> tuple[bool, str | None]:
    """
    验证手机号格式（支持多国家）
    
    根据国家代码验证对应国家的手机号格式。如果未指定国家代码，使用默认格式（8-15位数字）。
    
    支持的国家：
    - CN（中国大陆）：11位数字，1开头，第二位3-9
    - US（美国）：10位数字
    - GB（英国）：11位数字，0开头
    - JP（日本）：10-11位数字
    - KR（韩国）：10-11位数字
    - IN（印度）：10位数字
    - 其他：8-15位数字（国际标准）
    
    参数:
        phone: 手机号字符串
        country_code: 国家代码（ISO 3166-1 二字母代码，如 "CN", "US"），可选
                     如果为None，使用默认格式验证
    
    返回:
        tuple[bool, str | None]: (是否有效, 错误信息)
        - 如果手机号为空，返回 (True, None)（手机号是可选的）
        - 如果格式正确，返回 (True, None)
        - 如果格式错误，返回 (False, 错误信息)
    
    示例:
        # 验证中国大陆手机号
        is_valid, error = validate_phone("13800138000", "CN")  # True, None
        
        # 验证美国手机号
        is_valid, error = validate_phone("1234567890", "US")  # True, None
        
        # 使用默认格式（未指定国家）
        is_valid, error = validate_phone("1234567890")  # True, None
        
        # 格式错误
        is_valid, error = validate_phone("123", "CN")  # False, "手机号格式不正确..."
    """
    if not phone:
        return True, None  # 手机号是可选的
    
    # 去除空格和常见格式字符（如 +、-、空格等）
    phone_cleaned = re.sub(r'[\s+\-()]', '', phone)
    
    # 如果清理后为空，返回错误
    if not phone_cleaned:
        return False, "手机号不能只包含格式字符"
    
    # 根据国家代码选择验证规则
    if country_code:
        country_code = country_code.upper().strip()
        pattern = PHONE_PATTERNS.get(country_code)
        
        if pattern:
            # 使用对应国家的格式规则
            if pattern.match(phone_cleaned):
                return True, None
            else:
                # 生成友好的错误信息
                country_names = {
                    'CN': '中国大陆',
                    'US': '美国',
                    'GB': '英国',
                    'JP': '日本',
                    'KR': '韩国',
                    'IN': '印度',
                    'DE': '德国',
                    'FR': '法国',
                    'IT': '意大利',
                    'ES': '西班牙',
                    'CA': '加拿大',
                    'AU': '澳大利亚',
                    'BR': '巴西',
                    'RU': '俄罗斯',
                    'MX': '墨西哥',
                    'ID': '印度尼西亚',
                    'TH': '泰国',
                    'VN': '越南',
                    'PH': '菲律宾',
                    'MY': '马来西亚',
                    'SG': '新加坡',
                    'HK': '中国香港',
                    'TW': '中国台湾',
                }
                country_name = country_names.get(country_code, country_code)
                return False, f"手机号格式不正确（{country_name}格式）"
        else:
            # 国家代码不支持，使用默认格式
            logger.warning(f"未找到国家代码 {country_code} 的手机号格式规则，使用默认格式验证")
            if DEFAULT_PHONE_PATTERN.match(phone_cleaned):
                return True, None
            else:
                return False, f"手机号格式不正确（应为8-15位数字）"
    else:
        # 未指定国家代码，使用默认格式（8-15位数字）
        if DEFAULT_PHONE_PATTERN.match(phone_cleaned):
            return True, None
        else:
            return False, "手机号格式不正确（应为8-15位数字）"


def validate_password_strength(password: str) -> tuple[bool, str | None]:
    """
    验证密码强度
    
    要求:
        - 至少6个字符
        - 至少包含一个字母和一个数字
        - 建议包含大小写字母、数字和特殊字符
    
    参数:
        password: 密码字符串
    
    返回:
        (是否有效, 错误信息)
    """
    if not password:
        return False, "密码不能为空"

    if len(password) < 6:
        return False, "密码至少需要6个字符"

    if len(password) > 72:
        return False, "密码不能超过72个字符（bcrypt限制）"

    # 检查是否包含字母和数字
    has_letter = re.search(r'[a-zA-Z]', password)
    has_digit = re.search(r'\d', password)

    if not has_letter:
        return False, "密码必须包含至少一个字母"

    if not has_digit:
        return False, "密码必须包含至少一个数字"

    # 警告：密码强度较弱（可选）
    has_upper = re.search(r'[A-Z]', password)
    has_lower = re.search(r'[a-z]', password)
    has_special = re.search(r'[!@#$%^&*(),.?":{}|<>]', password)

    if not (has_upper and has_lower and has_special):
        logger.warning("密码强度较弱，建议包含大小写字母和特殊字符")

    return True, None


def sanitize_input(text: str, max_length: int | None = None) -> str:
    """
    清理输入文本，防止XSS攻击
    
    参数:
        text: 输入文本
        max_length: 最大长度限制
    
    返回:
        清理后的文本
    """
    if not text:
        return ""

    # HTML转义，防止XSS
    sanitized = escape(text)

    # 长度限制
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
        logger.warning(f"输入文本被截断: 原长度={len(text)}, 限制={max_length}")

    return sanitized


def normalize_string(text: str | None, strip: bool = True, lower: bool = False) -> str | None:
    """
    规范化字符串（去除空格、转换为小写等）
    
    参数:
        text: 输入文本（可以是None）
        strip: 是否去除前后空格（默认：True）
        lower: 是否转换为小写（默认：False）
    
    返回:
        规范化后的文本，如果输入为None则返回None
    
    示例:
        normalize_string("  Hello World  ", strip=True, lower=True) -> "hello world"
        normalize_string(None) -> None
    """
    if text is None:
        return None
    
    result = text
    if strip:
        result = result.strip()
    if lower:
        result = result.lower()
    
    return result if result else None


def safe_strip(text: str | None) -> str | None:
    """
    安全地去除字符串前后空格
    
    参数:
        text: 输入文本（可以是None）
    
    返回:
        去除空格后的文本，如果输入为None或空字符串则返回None
    
    示例:
        safe_strip("  hello  ") -> "hello"
        safe_strip(None) -> None
        safe_strip("") -> None
    """
    if not text:
        return None
    stripped = text.strip()
    return stripped if stripped else None


def detect_sql_injection(text: str) -> bool:
    """
    检测可能的SQL注入攻击
    
    参数:
        text: 输入文本
    
    返回:
        是否检测到SQL注入模式（True表示检测到，False表示未检测到）
    """
    if not text:
        return False

    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning(f"检测到可能的SQL注入尝试: {text[:100]}")
            return True

    return False


def detect_xss(text: str) -> bool:
    """
    检测可能的XSS攻击
    
    参数:
        text: 输入文本
    
    返回:
        是否检测到XSS模式
    """
    if not text:
        return False

    for pattern in XSS_PATTERNS:
        if pattern.search(text):
            logger.warning(f"检测到可能的XSS尝试: {text[:100]}")
            return True

    return False


def validate_cron_expression(cron_expression: str) -> tuple[bool, str | None]:
    """
    验证 Cron 表达式格式（APScheduler 5字段格式：分 时 日 月 星期）
    
    参数:
        cron_expression: Cron 表达式字符串
    
    返回:
        (是否有效, 错误信息)
    """
    if not cron_expression:
        return False, "Cron表达式不能为空"

    cron_expression = cron_expression.strip()

    # 基本格式检查：应该是5个字段，用空格分隔
    parts = cron_expression.split()
    if len(parts) != 5:
        return False, "Cron表达式格式错误：应为5个字段（分 时 日 月 星期），用空格分隔"

        # 尝试使用 APScheduler 的 CronTrigger 验证
    try:
        from apscheduler.triggers.cron import CronTrigger
        from app.core.config import settings

        # 尝试创建 CronTrigger 来验证表达式
        # 这会抛出 ValueError 如果表达式无效
        CronTrigger.from_crontab(cron_expression, timezone=settings.TIMEZONE)
        return True, None
    except ValueError as e:
        # CronTrigger 会抛出 ValueError 如果表达式无效
        error_msg = str(e)
        # 提取更友好的错误信息，不泄露内部实现细节
        if "Invalid" in error_msg or "invalid" in error_msg.lower():
            # 简化错误信息，避免泄露内部实现
            return False, "Cron表达式格式无效，请检查表达式是否正确"
        # 提取关键错误信息
        if "field" in error_msg.lower() or "value" in error_msg.lower():
            return False, f"Cron表达式格式错误: {error_msg}"
        return False, "Cron表达式格式错误，请检查表达式是否正确"
    except ImportError as e:
        # 导入错误（依赖缺失）
        logger.error(f"Cron表达式验证依赖缺失: {e}", exc_info=True)
        # 如果无法使用 CronTrigger 验证，至少检查基本格式
        return False, "Cron表达式验证功能不可用，请检查系统配置"
    except Exception as e:
        # 其他异常
        logger.error(f"Cron表达式验证时发生异常: {e}", exc_info=True)
        # 如果无法使用 CronTrigger 验证，至少检查基本格式
        return False, "Cron表达式验证失败，请检查表达式格式"


def validate_and_sanitize(text: str, field_name: str, max_length: int | None = None,
                          allow_html: bool = False) -> tuple[bool, str | None, str]:
    """
    验证并清理输入文本
    
    参数:
        text: 输入文本
        field_name: 字段名称（用于错误信息）
        max_length: 最大长度
        allow_html: 是否允许HTML（如果为False，会进行转义）
    
    返回:
        (是否有效, 错误信息, 清理后的文本)
    """
    # 检查空值
    if not text or not text.strip():
        return False, f"{field_name}不能为空", ""

    # 检测SQL注入
    if detect_sql_injection(text):
        return False, f"{field_name}包含非法字符", ""

    # 检测XSS（如果允许HTML，则跳过）
    if not allow_html and detect_xss(text):
        return False, f"{field_name}包含非法字符", ""

    # 清理文本
    if allow_html:
        sanitized = text.strip()
    else:
        sanitized = sanitize_input(text.strip(), max_length)

    # 长度验证
    if max_length and len(sanitized) > max_length:
        return False, f"{field_name}长度不能超过{max_length}个字符", sanitized[:max_length]

    return True, None, sanitized


# ====== Postback URL 占位符验证 ======
# CPL 系统支持的占位符变量列表（基于 app/core/postback/forwarder.py）
# 这些变量在 Postback URL 替换时会被实际值替换
SUPPORTED_PLACEHOLDERS = {
    # PostbackConversion 直接字段
    'conversion_id', 'platform', 'event_name', 'event_value', 'payout',
    'devad_id', 'os', 'carrier', 'ip', 'gid', 'product_id', 'client_id',
    'click_id', 'click_time', 'conversion_status', 'timestamp', 'created_at',
    # Click 关联字段
    'click_offer_id', 'click_publisher_id', 'click_advertiser_id', 'click_ip',
    'click_device', 'click_country', 'click_user_agent', 'click_referer',
    # Offer 关联字段
    'offer_id', 'offer_name', 'advertiser_offer_id', 'offer_advertiser_id',
    'offer_payout', 'affiliate_payout', 'offer_country', 'offer_category',
    'offer_type', 'offer_status',
    # Publisher 关联字段
    'publisher_id', 'channel_id', 'publisher_name', 'publisher_email',
    # Advertiser 关联字段
    'advertiser_id', 'advertiser_name', 'advertiser_email',
    # 支持的别名（转换为标准格式后验证）
    'clickid', 'clickId', 'clk_id', 'cid',
    'conversionId', 'conv_id',
    'publisherId', 'channelId', 'offerId',
    'eventName', 'eventId', 'event_id',
}

# 别名映射（用于规范化占位符名称）
PLACEHOLDER_ALIAS_MAP = {
    'clickid': 'click_id',
    'clickId': 'click_id',
    'clk_id': 'click_id',
    'cid': 'click_id',
    'conversionId': 'conversion_id',
    'conv_id': 'conversion_id',
    'publisherId': 'publisher_id',
    'channelId': 'channel_id',
    'offerId': 'offer_id',
    'eventName': 'event_name',
    'eventId': 'event_name',
    'event_id': 'event_name',
}


def normalize_placeholder(placeholder: str) -> str:
    """
    规范化占位符名称（处理别名和大小写）
    
    参数:
        placeholder: 占位符名称（不含花括号）
    
    返回:
        规范化后的占位符名称
    """
    # 转换为小写
    normalized = placeholder.lower()
    
    # 检查别名映射
    if normalized in PLACEHOLDER_ALIAS_MAP:
        return PLACEHOLDER_ALIAS_MAP[normalized]
    
    # 将驼峰命名转换为下划线命名
    # 例如：clickId -> click_id
    normalized = re.sub(r'(?<!^)(?=[A-Z])', '_', placeholder).lower()
    
    return normalized


def validate_postback_url_placeholders(postback_url: str | None) -> tuple[bool, str | None]:
    """
    验证 Postback URL 中的占位符是否都在 CPL 系统支持的变量列表中
    
    参数:
        postback_url: Postback URL 字符串（可以为 None）
    
    返回:
        (是否有效, 错误信息)
        如果 URL 为空或 None，返回 (True, None)
        如果所有占位符都有效，返回 (True, None)
        如果有无效占位符，返回 (False, 错误信息)
    """
    # 如果 URL 为空，直接返回有效
    if not postback_url or not postback_url.strip():
        return True, None
    
    # 使用正则表达式查找所有占位符 {变量名}
    pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    placeholders = re.findall(pattern, postback_url)
    
    # 如果没有占位符，直接返回有效
    if not placeholders:
        return True, None
    
    # 检查每个占位符是否在支持的列表中
    invalid_placeholders = []
    for placeholder in placeholders:
        # 规范化占位符名称
        normalized = normalize_placeholder(placeholder)
        
        # 检查规范化后的名称是否在支持的列表中
        # 同时也要检查原始占位符（支持别名）
        if normalized not in SUPPORTED_PLACEHOLDERS and placeholder not in SUPPORTED_PLACEHOLDERS:
            invalid_placeholders.append(placeholder)
    
    # 如果有无效占位符，返回错误信息
    if invalid_placeholders:
        invalid_list = ', '.join([f'{{{p}}}' for p in invalid_placeholders])
        return False, f"Postback URL 中包含不支持的占位符: {invalid_list}。请使用 CPL 系统支持的变量。"
    
    return True, None