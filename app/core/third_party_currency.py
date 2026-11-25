"""第三方 Purchase 金额与币种的统一校验。"""
import re
from decimal import Decimal, InvalidOperation

MAX_PURCHASE_AMOUNT = Decimal("99999999.9999")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def normalize_currency(value):
    """规范化三位大写币种代码；ISO 4217 成员资格须由业务白名单确认。"""
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def validate_purchase_payload(amount, currency):
    """校验 Purchase 金额可安全存入 Numeric(12,4)，币种代码格式明确。"""
    if amount is None:
        raise ValueError("Purchase 金额不能为空")
    try:
        value = amount if isinstance(amount, Decimal) else Decimal(str(amount).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Purchase 金额不是有效十进制数")
    if not value.is_finite() or value <= 0:
        raise ValueError("Purchase 金额必须为有限正数")
    if value > MAX_PURCHASE_AMOUNT:
        raise ValueError("Purchase 金额超出 Numeric(12,4) 上限")
    if value.as_tuple().exponent < -4:
        raise ValueError("Purchase 金额最多允许四位小数")
    code = normalize_currency(currency)
    if not code or not _CURRENCY_RE.fullmatch(code):
        raise ValueError("Purchase 币种必须是三位字母代码，禁止静默默认 USD")
    return value, code
