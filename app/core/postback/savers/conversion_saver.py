"""
转化记录保存器

负责保存转化记录到数据库
"""
import logging
import json
import re
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime
from urllib.parse import unquote
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import PostbackConversion, Click, Product
from app.core.utils import get_app_now_naive

logger = logging.getLogger(__name__)


# Postback 原始请求可能包含上游用户标识、认证凭据和联系信息。
# 这些字段不参与归因快照，禁止原样写入长期业务记录。
_SENSITIVE_RAW_KEY = re.compile(
    r"(?:^|[_-])(authorization|auth|token|secret|password|passwd|api[_-]?key|"
    r"access[_-]?key|cookie|set-cookie|session|email|e-mail|phone|mobile|"
    r"address|street|ssn|social[_-]?security|card[_-]?number|cvv|bank[_-]?account|"
    r"ip|ip[_-]?address|idfa|gaid|devad[_-]?id|advertising[_-]?id|device[_-]?id|"
    r"user[_-]?agent|ua)(?:$|[_-])",
    re.IGNORECASE,
)
_MAX_RAW_DATA_BYTES = 32 * 1024
_MAX_RAW_DATA_DEPTH = 8
_MAX_RAW_DATA_ITEMS = 500
_MAX_RAW_STRING_LENGTH = 4096
_MAX_RAW_URL_DECODE_PASSES = 3
_PERCENT_ENCODED_BYTE = re.compile(r"%[0-9a-fA-F]{2}")


def _decode_percent_encoded_text(value: str) -> str:
    """有界解码 URL 编码文本，供敏感字段识别使用。"""
    decoded = value
    for _ in range(_MAX_RAW_URL_DECODE_PASSES):
        if not _PERCENT_ENCODED_BYTE.search(decoded):
            break
        candidate = unquote(decoded, errors="replace")
        if candidate == decoded:
            break
        decoded = candidate
    return decoded
# 支持 user_email、client_ip、phone_number 等复合参数名，避免 URL/form 文本绕过结构化字段脱敏。
_SENSITIVE_INLINE_KEY = (
    r"(?:[A-Za-z0-9.-]+[_-])*(?:authorization|proxy[_-]?authorization|auth|"
    r"access[_-]?token|refresh[_-]?token|token|secret|password|passwd|"
    r"api[_-]?key|email|e-mail|phone|mobile|ip(?:[_-]?address)?|"
    r"session(?:[_-]?id)?|cookie|set-cookie|idfa|gaid|devad[_-]?id|"
    r"user[_-]?agent|ua|advertising[_-]?id|device[_-]?id)(?:[_-]?[A-Za-z0-9.-]*)"
)
_SENSITIVE_INLINE_VALUE = re.compile(
    rf"""(?i)(?P<prefix>(?:[?&;]|\b)["']?(?:{_SENSITIVE_INLINE_KEY})["']?\s*[=:]\s*["']?)(?P<value>[^&;\s,"']+)"""
)
_SENSITIVE_HEADER_LINE = re.compile(
    r"""(?im)^(\s*(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*:\s*)[^\r\n]*"""
)
_BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[^\s,;]+")


def sanitize_postback_raw_data(value: Any) -> Any:
    """递归清理 Postback 原始数据中的敏感字段并限制持久化体积。

    仅用于数据库诊断快照，不改变实际业务解析使用的原始请求。
    超限时保存明确的省略标记，避免截断 JSON 或意外持久化超大请求。
    """
    remaining = [_MAX_RAW_DATA_ITEMS]

    def clean(item: Any, depth: int) -> Any:
        remaining[0] -= 1
        if remaining[0] < 0 or depth > _MAX_RAW_DATA_DEPTH:
            return "[omitted]"
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                key_text = str(key)
                # JSON 键名也可能被 URL 编码；先有界解码，再做驼峰/缩写归一化。
                decoded_key = _decode_percent_encoded_text(key_text)
                # 先拆分连续大写缩写与普通驼峰，避免 clientIP 被错误拆成 client_i_p。
                normalized_key = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", decoded_key)
                normalized_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized_key).lower()
                if _SENSITIVE_RAW_KEY.search(normalized_key):
                    continue
                result[key_text[:128]] = clean(child, depth + 1)
                if remaining[0] <= 0:
                    break
            return result
        if isinstance(item, (list, tuple)):
            return [clean(child, depth + 1) for child in item[:_MAX_RAW_DATA_ITEMS]]
        if isinstance(item, str):
            # 原始请求可能以 JSON 字符串、URL 或 HTTP header 文本传入；
            # 不能只检查 dict 键名，否则字符串载荷会绕过字段脱敏。
            if len(item.encode("utf-8", errors="replace")) > _MAX_RAW_DATA_BYTES:
                return "[oversized raw string omitted]"
            original_text = item
            # 上游可能把 JSON/query/header 再做一到多层 percent-encoding；
            # 先在内存中最多解码 3 次，仅用于识别与脱敏，不改变业务解析输入。
            text = _decode_percent_encoded_text(original_text)
            stripped = text.lstrip()
            if stripped.startswith(("{", "[")):
                try:
                    parsed = json.loads(text)
                except (json.JSONDecodeError, RecursionError):
                    parsed = None
                if isinstance(parsed, (dict, list)):
                    nested = clean(parsed, depth + 1)
                    if nested != parsed:
                        encoded_nested = json.dumps(
                            nested, ensure_ascii=False, separators=(",", ":")
                        )
                        if len(encoded_nested.encode("utf-8")) > _MAX_RAW_STRING_LENGTH:
                            return "[structured payload omitted: exceeds string limit]"
                        return encoded_nested
                    if len(original_text.encode("utf-8", errors="replace")) > _MAX_RAW_STRING_LENGTH:
                        return "[structured payload omitted: exceeds string limit]"
                    # 没有发现敏感字段时保留原始编码形式，避免改变 click_id 等业务快照值。
                    return original_text

            sanitized_text = _SENSITIVE_HEADER_LINE.sub(r"\1[redacted]", text)
            sanitized_text = _SENSITIVE_INLINE_VALUE.sub(r"\1[redacted]", sanitized_text)
            sanitized_text = _BEARER_VALUE.sub("Bearer [redacted]", sanitized_text)
            if sanitized_text != text:
                return sanitized_text[:_MAX_RAW_STRING_LENGTH]
            return original_text[:_MAX_RAW_STRING_LENGTH]
        if item is None or isinstance(item, (bool, int, float)):
            return item
        # JSON 请求通常不会包含自定义对象；未知对象不应通过 repr 泄漏信息。
        return "[unsupported value omitted]"

    sanitized = clean(value, 0)
    encoded = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > _MAX_RAW_DATA_BYTES:
        return {
            "_redaction": "payload_exceeds_storage_limit",
            "_sanitized_size_bytes": len(encoded.encode("utf-8")),
        }
    return sanitized


class ConversionSaver:
    """转化记录保存器"""

    @staticmethod
    async def resolve_trusted_attribution(
        normalized_data: Dict[str, Any],
        click_association: Optional[Dict[str, Any]],
        db: AsyncSession,
    ) -> tuple[Optional[int], Optional[int]]:
        """仅从服务器侧点击/渠道关系确定客户，并验证产品属于该客户。"""
        trusted_client_id = (
            click_association.get('client_id') if click_association else None
        )
        if trusted_client_id is None and click_association:
            trusted_publisher = click_association.get('publisher')
            trusted_client_id = getattr(trusted_publisher, 'client_id', None)

        supplied_client_id = normalized_data.get('client_id')
        if supplied_client_id is not None:
            try:
                client_id_mismatch = (
                    trusted_client_id is None
                    or int(supplied_client_id) != int(trusted_client_id)
                )
            except (TypeError, ValueError):
                client_id_mismatch = True
            if client_id_mismatch:
                logger.warning(
                    "忽略回调中不可信或与点击归属不一致的 client_id：supplied=%s trusted=%s",
                    supplied_client_id,
                    trusted_client_id,
                )

        product_id_candidate = (
            click_association.get('product_id') if click_association else None
        ) or normalized_data.get('product_id')
        trusted_product_id = None
        if trusted_client_id is not None and product_id_candidate is not None:
            product_result = await db.execute(
                select(Product.id)
                .where(
                    Product.id == product_id_candidate,
                    Product.client_id == trusted_client_id,
                )
                .limit(1)
            )
            trusted_product_id = product_result.scalar_one_or_none()
            if trusted_product_id is None:
                logger.warning(
                    "忽略不属于当前点击客户的 product_id：product_id=%s client_id=%s",
                    product_id_candidate,
                    trusted_client_id,
                )
        elif product_id_candidate is not None:
            logger.warning(
                "缺少可信点击客户归属，忽略回调中的 product_id：product_id=%s",
                product_id_candidate,
            )

        return trusted_client_id, trusted_product_id

    @staticmethod
    async def save(
        normalized_data: Dict[str, Any],
        click_association: Optional[Dict[str, Any]],
        final_payout: Decimal | float | int | str,
        conversion_status: str,
        db: AsyncSession,
        trusted_client_id: Optional[int] = None,
        trusted_product_id: Optional[int] = None,
        trusted_attribution_resolved: bool = False,
    ) -> PostbackConversion:
        """
        保存转化记录
        
        Args:
            normalized_data: 标准化后的数据
            click_association: Click 关联信息
            final_payout: 最终金额
            conversion_status: 转化状态
            db: 数据库会话
        
        Returns:
            PostbackConversion: 保存的转化记录
        """
        # 归因快照在可信租户/产品归属核验后生成，避免把请求体字段当成可信归属。
        raw_in = normalized_data.get('raw_data')
        raw_payload = sanitize_postback_raw_data(raw_in) if raw_in is not None else None
        snapshot = None

        click_time = None
        if click_association:
            click_time = click_association.get('click_time')

        snap_offer = click_association.get('offer_id') if click_association else None
        snap_pub = click_association.get('publisher_id') if click_association else None
        snap_adv = click_association.get('advertiser_id') if click_association else None

        if not trusted_attribution_resolved:
            trusted_client_id, trusted_product_id = (
                await ConversionSaver.resolve_trusted_attribution(
                    normalized_data=normalized_data,
                    click_association=click_association,
                    db=db,
                )
            )

        if click_association:
            snapshot = {
                key: click_association[key]
                for key in ('offer_id', 'publisher_id', 'advertiser_id', 'click_id')
                if click_association.get(key) is not None
            }
            if trusted_client_id is not None:
                snapshot['client_id'] = trusted_client_id
            if trusted_product_id is not None:
                snapshot['product_id'] = trusted_product_id
            snapshot = snapshot or None

        if raw_payload is not None:
            if snapshot:
                if isinstance(raw_payload, dict):
                    raw_payload['_attribution'] = snapshot
                else:
                    raw_payload = {'_payload': raw_payload, '_attribution': snapshot}
            raw_data_json = json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":"))
        elif raw_in is not None:
            raw_data_json = json.dumps(sanitize_postback_raw_data(raw_in), ensure_ascii=False, separators=(",", ":"))
        elif snapshot:
            raw_data_json = json.dumps({'_attribution': snapshot}, ensure_ascii=False, separators=(",", ":"))
        else:
            raw_data_json = None

        conversion = PostbackConversion(
            platform=normalized_data['platform'],
            conversion_id=normalized_data['conversion_id'],
            click_id=normalized_data.get('click_id') or (click_association.get('click_id') if click_association else None),
            click_time=click_time,
            offer_id=snap_offer,
            publisher_id=snap_pub,
            advertiser_id=snap_adv,
            event_name=normalized_data['event_name'],
            event_value=normalized_data['event_value'],
            original_payout=normalized_data['payout'],
            payout=final_payout,
            devad_id=normalized_data['devad_id'],
            os=normalized_data['os'],
            carrier=normalized_data['carrier'],
            ip=normalized_data['ip'] or (click_association.get('ip') if click_association else None),
            gid=normalized_data['gid'],
            product_id=trusted_product_id,
            client_id=trusted_client_id,
            conversion_status=conversion_status,
            raw_data=raw_data_json,
            created_at=get_app_now_naive()
        )
        
        db.add(conversion)
        await db.flush()  # 获取 ID
        await db.refresh(conversion)
        
        logger.info(
            f"转化记录已保存：id={conversion.id}, "
            f"platform={conversion.platform}, conversion_id={conversion.conversion_id}"
        )
        
        return conversion
    
    @staticmethod
    async def update_click_conversion(
        click_association: Optional[Dict[str, Any]],
        conversion_id: int,
        db: AsyncSession
    ) -> bool:
        """
        更新 Click 表的 conversion_id
        
        Args:
            click_association: Click 关联信息
            conversion_id: 转化 ID
            db: 数据库会话
        
        Returns:
            bool: 是否成功更新
        """
        if not click_association:
            return False
        
        try:
            # 查询并更新 Click 记录
            click_id = click_association['click_id']
            
            # 查询 Click 记录
            result = await db.execute(
                select(Click).where(Click.click_id == click_id)
            )
            click = result.scalars().first()
            
            if not click:
                logger.warning(
                    f"未找到 Click 记录，无法更新 conversion_id：click_id={click_id}, "
                    f"conversion_id={conversion_id}"
                )
                return False
            
            # 更新 conversion_id
            click.conversion_id = conversion_id
            await db.flush()
            
            logger.info(
                f"Click 表 conversion_id 已更新：click_id={click_id}, "
                f"conversion_id={conversion_id}"
            )
            
            return True
            
        except Exception as e:
            logger.error("更新 Click 表 conversion_id 失败：%s", type(e).__name__)
            raise
