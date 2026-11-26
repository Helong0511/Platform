"""第三方 Purchase 金额与 ISO 4217 币种校验及来源归因。"""
from decimal import Decimal, InvalidOperation

import pycountry

MAX_PURCHASE_AMOUNT = Decimal("99999999.9999")
DEFAULT_CURRENCY = "USD"

# ISO 4217 特殊用途代码，不代表可用于 Purchase 结算的实际货币。
_NON_SETTLEMENT_CODES = {
    "XTS",  # 测试代码
    "XXX",  # 无货币
    "XAU", "XAG", "XPD", "XPT",  # 贵金属
    "XBA", "XBB", "XBC", "XBD",  # 债券市场单位
    "XDR", "XSU", "XUA",          # 特殊记账单位
}


def resolve_currency(value, *, source=None, default=DEFAULT_CURRENCY):
    """解析币种并返回来源；空值使用明确默认值，错误代码绝不静默回退。

    source 应描述真实来源，例如 upstream_field:currency_code、
    cloak_config:postback 或 manual_override。调用方未提供来源时，
    非空值标记为 caller_supplied；缺失值标记为 system_fallback_usd。
    """
    raw = value
    normalized = str(value).strip().upper() if value is not None else ""
    if not normalized:
        fallback = str(default or DEFAULT_CURRENCY).strip().upper()
        validate_iso_currency(fallback)
        return fallback, "system_fallback_usd" if fallback == "USD" else "system_fallback"
    validate_iso_currency(normalized)
    return normalized, source or "caller_supplied"


def validate_iso_currency(value):
    """验证当前有效的 ISO 4217 结算货币代码。"""
    code = str(value or "").strip().upper()
    if len(code) != 3 or code in _NON_SETTLEMENT_CODES:
        raise ValueError("币种必须是当前有效的 ISO 4217 结算货币代码")
    currency = pycountry.currencies.get(alpha_3=code)
    if currency is None or getattr(currency, "withdrawal_date", None):
        raise ValueError(f"币种不是当前有效的 ISO 4217 代码：{code or '<empty>'}")
    return code


def normalize_currency(value):
    """规范化币种；缺失时按业务规则返回 USD。"""
    return resolve_currency(value)[0]


def validate_purchase_payload(amount, currency, *, currency_source=None):
    """校验 Purchase 金额与 ISO 4217 币种；缺失币种明确回退 USD。"""
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
    code, _source = resolve_currency(currency, source=currency_source)
    return value, code
