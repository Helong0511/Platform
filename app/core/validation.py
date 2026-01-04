"""
输入验证和清理工具模块
提供安全的输入验证、清理和规范化功能
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

# 手机号：中国大陆手机号（11位数字）
PHONE_PATTERN = re.compile(r'^1[3-9]\d{9}$')

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

    if len(username) < 3:
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


def validate_phone(phone: str) -> tuple[bool, str | None]:
    """
    验证手机号格式（中国大陆）
    
    参数:
        phone: 手机号
    
    返回:
        (是否有效, 错误信息)
    """
    if not phone:
        return True, None  # 手机号是可选的

    if not PHONE_PATTERN.match(phone):
        return False, "手机号格式不正确（应为11位数字）"

    return True, None


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
