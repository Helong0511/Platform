"""非白名单 Postback 的安全待审批入队服务。"""
import hashlib
import ipaddress
import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis_client
from app.core.utils import get_app_now_naive
from app.models.models import PendingPostbackConversion, PendingPostbackQueueGuard
from app.core.postback_event_name import normalize_event_name

logger = logging.getLogger(__name__)

# 单个来源 IP 的入队上限；Redis 不可用时 fail-closed，不能退化成进程内计数。
_PENDING_RATE_LIMIT_PER_HOUR = 20
_PENDING_RATE_LIMIT_PER_DAY = 100
_PENDING_GLOBAL_RATE_LIMIT_PER_HOUR = 500
_PENDING_GLOBAL_RATE_LIMIT_PER_DAY = 5000
_PENDING_MAX_OPEN_RECORDS = 10000
_PENDING_RAW_DATA_MAX_BYTES = 32 * 1024
_PLATFORM_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$")
_RATE_LIMIT_SCRIPT = """
local ip_hourly = redis.call('INCR', KEYS[1])
if ip_hourly == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ip_daily = redis.call('INCR', KEYS[2])
if ip_daily == 1 then redis.call('EXPIRE', KEYS[2], ARGV[2]) end
-- 已超过单 IP 上限时立即拒绝，不让单一来源消耗全局配额。
if ip_hourly > tonumber(ARGV[3]) or ip_daily > tonumber(ARGV[4]) then
    return 0
end
local global_hourly = redis.call('INCR', KEYS[3])
if global_hourly == 1 then redis.call('EXPIRE', KEYS[3], ARGV[1]) end
local global_daily = redis.call('INCR', KEYS[4])
if global_daily == 1 then redis.call('EXPIRE', KEYS[4], ARGV[2]) end
if global_hourly > tonumber(ARGV[5]) or global_daily > tonumber(ARGV[6]) then
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
                4,
                f"{base}:hour",
                f"{base}:day",
                "postback:pending:rate:global:hour",
                "postback:pending:rate:global:day",
                3600,
                86400,
                _PENDING_RATE_LIMIT_PER_HOUR,
                _PENDING_RATE_LIMIT_PER_DAY,
                _PENDING_GLOBAL_RATE_LIMIT_PER_HOUR,
                _PENDING_GLOBAL_RATE_LIMIT_PER_DAY,
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

        # 延迟导入 Postback 子模块，避免与 app.core.postback.__init__ 的处理器注册发生循环导入。
        from app.core.postback.handlers import get_handler
        from app.core.postback.savers.conversion_saver import sanitize_postback_raw_data
        from app.core.postback.transformers.normalizer import DataNormalizer
        from app.core.postback.validators.data_validator import (
            DataValidator,
            validate_payout_value,
        )

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

        if not isinstance(normalized, dict):
            return {"queued": False, "reason": "invalid_fields"}
        conversion_value = normalized.get("conversion_id")
        event_value_raw = normalized.get("event_name")
        if isinstance(conversion_value, (dict, list, tuple, set, bytes, bytearray)):
            return {"queued": False, "reason": "invalid_fields"}
        if isinstance(event_value_raw, (dict, list, tuple, set, bytes, bytearray)):
            return {"queued": False, "reason": "invalid_fields"}
        conversion_id = str(conversion_value or "").strip()
        event_name = normalize_event_name(event_value_raw)
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

        # 对应数据库 VARCHAR/Numeric 列做显式边界校验，避免恶意长字段或溢出值触发 DB 错误。
        bounded_fields = (
            ("os", 20),
            ("carrier", 50),
            ("gid", 100),
            ("click_id", 255),
            ("devad_id", 255),
            ("ip", 50),
        )
        for field_name, max_length in bounded_fields:
            field_value = normalized.get(field_name)
            if field_value is None:
                continue
            if isinstance(field_value, (dict, list, tuple, set, bytes, bytearray)):
                return {"queued": False, "reason": "invalid_fields"}
            normalized[field_name] = str(field_value).strip()
            if len(normalized[field_name]) > max_length:
                return {"queued": False, "reason": "invalid_fields"}

        # 用户/设备 IP 与请求来源 IP 是不同语义：前者来自回调字段，仅作业务快照；
        # 后者来自服务端连接上下文，独立用于白名单与限流。
        user_ip = normalized.get("ip")
        if user_ip:
            try:
                user_ip = str(ipaddress.ip_address(str(user_ip).strip()))
            except ValueError:
                user_ip = None
        else:
            user_ip = None

        event_value = normalized.get("event_value")
        if event_value is not None:
            try:
                event_value = Decimal(str(event_value))
                if (
                    not event_value.is_finite()
                    or abs(event_value) > Decimal("99999999.9999")
                    or event_value != event_value.quantize(Decimal("0.0001"))
                ):
                    return {"queued": False, "reason": "invalid_fields"}
            except (InvalidOperation, ValueError, TypeError):
                return {"queued": False, "reason": "invalid_fields"}

        dedupe_source = "\x1f".join((platform.casefold(), conversion_id.casefold(), event_name.casefold()))
        dedupe_key = hashlib.sha256(dedupe_source.encode("utf-8")).hexdigest()

        # 必须先获取 guard 行锁，再执行任何普通 SELECT。
        # MySQL REPEATABLE READ 会在首次一致性读时建立快照；先锁后读可避免等待 guard 期间
        # 已提交的新入队记录落在旧快照之外，造成 COUNT 低估并突破容量上限。
        guard_result = await db.execute(
            select(PendingPostbackQueueGuard.id)
            .where(PendingPostbackQueueGuard.id == 1)
            .with_for_update()
        )
        if guard_result.scalar_one_or_none() is None:
            raise PendingPostbackQueueError("pending queue capacity guard unavailable")

        existing = await db.execute(
            select(PendingPostbackConversion.id).where(
                or_(
                    PendingPostbackConversion.dedupe_key == dedupe_key,
                    and_(
                        PendingPostbackConversion.platform == platform,
                        PendingPostbackConversion.conversion_id == conversion_id,
                        PendingPostbackConversion.event_name == event_name,
                    ),
                )
            ).limit(1)
        )
        existing_id = existing.scalar_one_or_none()
        if existing_id is not None:
            return {"queued": False, "reason": "duplicate", "pending_id": existing_id}

        # guard 锁已持有；并发 enqueue 无法在此事务提交前插入另一条 pending 记录。
        # 此时一致性读快照建立在获取 guard 之后，不会漏掉此前等待期间已提交的入队。
        pending_count = await db.scalar(
            select(func.count())
            .select_from(PendingPostbackConversion)
            .where(PendingPostbackConversion.status == "pending")
        )
        if int(pending_count or 0) >= _PENDING_MAX_OPEN_RECORDS:
            return {"queued": False, "reason": "queue_backlog_full"}

        sanitized = sanitize_postback_raw_data(raw_data)
        raw_json = json.dumps(
            sanitized, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        if len(raw_json.encode("utf-8")) > _PENDING_RAW_DATA_MAX_BYTES:
            return {"queued": False, "reason": "payload_too_large"}

        pending = PendingPostbackConversion(
            platform=platform,
            conversion_id=conversion_id,
            event_name=event_name,
            event_value=event_value,
            original_payout=payout,
            payout=payout,
            devad_id=normalized.get("devad_id"),
            os=normalized.get("os"),
            carrier=normalized.get("carrier"),
            # 来源 IP 以服务端可信连接信息为准，不采信请求体自报 IP。
            ip=user_ip,
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
                    or_(
                        PendingPostbackConversion.dedupe_key == dedupe_key,
                        and_(
                            PendingPostbackConversion.platform == platform,
                            PendingPostbackConversion.conversion_id == conversion_id,
                            PendingPostbackConversion.event_name == event_name,
                        ),
                    )
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
