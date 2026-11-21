"""非白名单 Postback 的安全待审批入队服务。"""
import hashlib
import ipaddress
import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postback.handlers import get_handler
from app.core.postback.savers.conversion_saver import sanitize_postback_raw_data
from app.core.postback.transformers.normalizer import DataNormalizer
from app.core.postback.validators.data_validator import DataValidator, validate_payout_value
from app.core.redis_client import get_redis_client
from app.core.utils import get_app_now_naive
from app.models.models import PendingPostbackConversion

logger = logging.getLogger(__name__)

# 单个来源 IP 的入队上限；Redis 不可用时 fail-closed，不能退化成进程内计数。
_PENDING_RATE_LIMIT_PER_HOUR = 20
_PENDING_RATE_LIMIT_PER_DAY = 100
_PENDING_RAW_DATA_MAX_BYTES = 32 * 1024
_PLATFORM_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$")
_RATE_LIMIT_SCRIPT = """
local hourly = redis.call('INCR', KEYS[1])
if hourly == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local daily = redis.call('INCR', KEYS[2])
if daily == 1 then redis.call('EXPIRE', KEYS[2], ARGV[2]) end
if hourly > tonumber(ARGV[3]) or daily > tonumber(ARGV[4]) then
    return 0
end
return 1
"""


class PendingPostbackQueueError(RuntimeError):
    """待审批队列暂不可用；调用方应返回可重试错误。"""


class PendingPostbackIngestService:
    """验证、限流、脱敏并幂等保存非白名单 Postback。"""

    @staticmethod
    async def _allow_enqueue(request_ip: str) -> bool:
        """使用 Redis 原子计数限流；Redis 故障时拒绝入队。"""
        redis = await get_redis_client()
        if redis is None:
            raise PendingPostbackQueueError("rate limiter unavailable")

        ip_digest = hashlib.sha256(request_ip.encode("utf-8")).hexdigest()
        base = f"postback:pending:rate:{ip_digest}"
        try:
            allowed = await redis.eval(
                _RATE_LIMIT_SCRIPT,
                2,
                f"{base}:hour",
                f"{base}:day",
                3600,
                86400,
                _PENDING_RATE_LIMIT_PER_HOUR,
                _PENDING_RATE_LIMIT_PER_DAY,
            )
        except Exception as exc:
            logger.warning(
                "待审批 Postback 限流服务异常：error_type=%s",
                type(exc).__name__,
            )
            raise PendingPostbackQueueError("rate limiter unavailable") from exc
        return bool(allowed)

    @staticmethod
    async def enqueue(
        *,
        platform: str,
        raw_data: Dict[str, Any],
        request_ip: Optional[str],
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """将校验通过的未授权来源请求保存为待审批记录。

        不执行正式转化、Cap 预留、下游转发或第三方上报。
        """
        if not request_ip or not str(request_ip).strip():
            return {"queued": False, "reason": "missing_source_ip"}

        try:
            source_ip = str(ipaddress.ip_address(str(request_ip).strip()))
        except ValueError:
            return {"queued": False, "reason": "invalid_source_ip"}

        platform = str(platform or "").strip()
        if not _PLATFORM_PATTERN.fullmatch(platform):
            return {"queued": False, "reason": "invalid_platform"}
        if not isinstance(raw_data, dict):
            return {"queued": False, "reason": "invalid_payload"}

        try:
            encoded_input = json.dumps(
                raw_data, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError, RecursionError):
            return {"queued": False, "reason": "invalid_payload"}
        if len(encoded_input) > _PENDING_RAW_DATA_MAX_BYTES:
            return {"queued": False, "reason": "payload_too_large"}

        # 先限流，再执行平台验证和标准化，降低无白名单来源的资源消耗。
        if not await PendingPostbackIngestService._allow_enqueue(source_ip):
            return {"queued": False, "reason": "rate_limited"}

        handler = get_handler(platform)
        if handler:
            valid, _error = await handler.validate(raw_data)
            if not valid:
                return {"queued": False, "reason": "invalid_fields"}
            normalized = await handler.normalize(raw_data)
        else:
            valid, _errors = DataValidator.validate(raw_data, platform)
            if not valid:
                return {"queued": False, "reason": "invalid_fields"}
            normalized = DataNormalizer.normalize(raw_data, platform)

        conversion_id = str(normalized.get("conversion_id") or "").strip()
        event_name = str(normalized.get("event_name") or "default").strip() or "default"
        if not conversion_id or len(conversion_id) > 200 or len(event_name) > 100:
            return {"queued": False, "reason": "invalid_fields"}

        payout_raw = normalized.get("payout")
        payout_error = validate_payout_value(payout_raw)
        if payout_error:
            return {"queued": False, "reason": "invalid_fields"}
        try:
            payout = Decimal(str(payout_raw))
            if not payout.is_finite():
                return {"queued": False, "reason": "invalid_fields"}
        except (InvalidOperation, ValueError, TypeError):
            return {"queued": False, "reason": "invalid_fields"}

        event_value = normalized.get("event_value")
        if event_value is not None:
            try:
                event_value = Decimal(str(event_value))
                if not event_value.is_finite():
                    event_value = None
            except (InvalidOperation, ValueError, TypeError):
                event_value = None

        dedupe_source = "\x1f".join((platform.lower(), conversion_id, event_name))
        dedupe_key = hashlib.sha256(dedupe_source.encode("utf-8")).hexdigest()

        existing = await db.execute(
            select(PendingPostbackConversion.id).where(
                PendingPostbackConversion.dedupe_key == dedupe_key
            ).limit(1)
        )
        existing_id = existing.scalar_one_or_none()
        if existing_id is not None:
            return {"queued": False, "reason": "duplicate", "pending_id": existing_id}

        sanitized = sanitize_postback_raw_data(raw_data)
        raw_json = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
        if len(raw_json.encode("utf-8")) > _PENDING_RAW_DATA_MAX_BYTES:
            return {"queued": False, "reason": "payload_too_large"}

        pending = PendingPostbackConversion(
            platform=platform,
            conversion_id=conversion_id,
            event_name=event_name,
            event_value=event_value,
            original_payout=payout,
            payout=payout,
            devad_id=None,
            os=normalized.get("os"),
            carrier=normalized.get("carrier"),
            # 来源 IP 以服务端可信连接信息为准，不采信请求体自报 IP。
            ip=source_ip,
            gid=normalized.get("gid"),
            product_id=None,
            client_id=None,
            click_id=normalized.get("click_id"),
            click_time=None,
            raw_data=raw_json,
            request_ip=source_ip,
            status="pending",
            dedupe_key=dedupe_key,
            created_at=get_app_now_naive(),
            updated_at=get_app_now_naive(),
        )
        db.add(pending)
        try:
            await db.flush()
        except IntegrityError:
            # 唯一键是并发请求的最终幂等栅栏；不将并发重复误报为新入队。
            await db.rollback()
            duplicate = await db.execute(
                select(PendingPostbackConversion.id).where(
                    PendingPostbackConversion.dedupe_key == dedupe_key
                ).limit(1)
            )
            duplicate_id = duplicate.scalar_one_or_none()
            if duplicate_id is not None:
                return {
                    "queued": False,
                    "reason": "duplicate",
                    "pending_id": duplicate_id,
                }
            raise

        logger.info(
            "非白名单 Postback 已进入待审批队列：platform=%s pending_id=%s",
            platform,
            pending.id,
        )
        return {"queued": True, "pending_id": pending.id}


pending_postback_ingest_service = PendingPostbackIngestService()
