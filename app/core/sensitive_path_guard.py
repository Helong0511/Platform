"""
敏感路径防护执行：计数、自动封禁、Telegram 预警。

由 middleware 在请求进入业务路由前调用；规则定义见 sensitive_path_rules。
命中后按等级累计滑动窗口次数，达阈值写入 SensitiveBlockedIP 并可选推送 Telegram。
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis_client
from app.core.sensitive_path_rules import (
    SensitivePathLevel,
    SensitivePathMatch,
    level_label,
)
from app.core.utils import get_app_now_naive
from app.models.models import SensitiveBlockedIP

logger = logging.getLogger(__name__)

# 内存降级：ip -> {level_value: (count, expire_ts)}
# 使用 OrderedDict 保证 LRU 淘汰顺序
_mem_hit_store: OrderedDict[str, dict[int, tuple[int, float]]] = OrderedDict()
_mem_alert_ts: OrderedDict[str, float] = OrderedDict()
_blocked_ip_cache_bust_callbacks: list = []

# 内存存储最大IP数量限制
_MEM_STORE_MAX_IP = 5000
# 内存存储清理阈值（达到最大数量的80%时触发清理）
_MEM_STORE_CLEANUP_THRESHOLD = int(_MEM_STORE_MAX_IP * 0.8)


def _cleanup_memory_store() -> None:
    """清理内存存储，淘汰最久未使用的IP记录。"""
    global _mem_hit_store, _mem_alert_ts

    if len(_mem_hit_store) >= _MEM_STORE_CLEANUP_THRESHOLD:
        # 清理到总大小的50%
        entries_to_clean = len(_mem_hit_store) - int(_MEM_STORE_MAX_IP * 0.5)
        cleaned = 0
        while cleaned < entries_to_clean and _mem_hit_store:
            oldest_ip, _ = _mem_hit_store.popitem(last=False)
            _mem_alert_ts.pop(oldest_ip, None)
            cleaned += 1
        if cleaned:
            logger.debug(f"清理了 {cleaned} 个旧的敏感路径探测记录，当前内存存储IP数: {len(_mem_hit_store)}")


def register_blocked_ip_cache_bust(callback) -> None:
    """中间件注册：自动封禁后立即使黑名单缓存失效。"""
    _blocked_ip_cache_bust_callbacks.append(callback)


def bust_sensitive_blocked_ip_cache() -> None:
    """封禁/解封后刷新中间件黑名单缓存。"""
    _bust_blocked_ip_cache()


def _bust_blocked_ip_cache() -> None:
    """遍历已注册的回调，使中间件侧 IP 黑名单缓存立即失效。"""
    for cb in _blocked_ip_cache_bust_callbacks:
        try:
            cb()
        except Exception as exc:
            logger.debug("刷新敏感路径黑名单缓存失败: %s", exc)


class SensitivePathHitTracker:
    """滑动窗口内按等级累计探测次数（Redis 优先）。"""

    def __init__(self) -> None:
        """从配置读取滑动窗口秒数，默认 1800 秒（30 分钟）。"""
        self._window = int(getattr(settings, "SENSITIVE_PATH_HIT_WINDOW_SECONDS", 1800))

    def _redis_key(self, ip: str, level: SensitivePathLevel) -> str:
        """构造滑动窗口计数用的 Redis 键：sensitive_probe:{ip}:L{等级}。"""
        return f"sensitive_probe:{ip}:L{int(level)}"

    async def increment(self, ip: str, level: SensitivePathLevel) -> int:
        """
        在滑动窗口内将指定 IP、等级的探测次数 +1。

        Args:
            ip: 客户端 IP
            level: 敏感路径等级

        Returns:
            窗口内累计次数；无效 IP 或 Redis/内存均失败时返回 0
        """
        if not ip or ip == "unknown":
            return 0
        redis = await get_redis_client()
        if redis:
            try:
                key = self._redis_key(ip, level)
                count = await redis.incr(key)
                if count == 1:
                    await redis.expire(key, self._window)
                return int(count)
            except Exception as exc:
                logger.debug("敏感路径 Redis 计数失败，降级内存: %s", exc)
        return self._mem_increment(ip, level)

    def _mem_increment(self, ip: str, level: SensitivePathLevel) -> int:
        """Redis 不可用时的进程内滑动窗口计数降级实现。"""
        _cleanup_memory_store()
        now = time.time()
        expire = now + self._window
        if ip in _mem_hit_store:
            _mem_hit_store.move_to_end(ip)
        bucket = _mem_hit_store.setdefault(ip, {})
        lv = int(level)
        cnt, exp = bucket.get(lv, (0, 0.0))
        if now > exp:
            cnt = 0
        cnt += 1
        bucket[lv] = (cnt, expire)
        return cnt


_hit_tracker = SensitivePathHitTracker()

# 本机回环地址：开发/健康检查探测不应写入黑名单，否则本地联调会被自己锁死
_LOOPBACK_IPS = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0"})


def _is_loopback_ip(ip: str) -> bool:
    """判断是否为本机回环地址（含 IPv4/IPv6 常见写法）。"""
    value = (ip or "").strip().lower()
    if not value:
        return False
    if value in _LOOPBACK_IPS or value.startswith("127."):
        return True
    return value.startswith("::ffff:127.")


async def _upsert_blocked_ip(ip: str, reason: str) -> bool:
    """写入或激活 IP 黑名单，返回是否新封禁。"""
    for attempt in range(3):
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(SensitiveBlockedIP).where(SensitiveBlockedIP.blocked_ip == ip)
                )
                row = result.scalars().first()
                if row:
                    if row.is_active:
                        return False
                    row.is_active = True
                    row.reason = reason[:255]
                    row.updated_at = get_app_now_naive()
                else:
                    db.add(
                        SensitiveBlockedIP(
                            blocked_ip=ip,
                            reason=reason[:255],
                            is_active=True,
                        )
                    )
                await db.commit()
            _bust_blocked_ip_cache()
            return True
        except (IntegrityError, StaleDataError):
            if attempt == 2:
                logger.warning("自动封禁 IP 冲突重试耗尽: %s", ip)
                return False
            await asyncio.sleep(0.05)
        except Exception as exc:
            logger.warning("自动封禁 IP 失败: ip=%s err=%s", ip, exc)
            return False
    return False


async def _should_send_telegram_alert(ip: str) -> bool:
    """
    判断当前 IP 是否允许发送 Telegram 预警（防抖窗口内仅一次）。

    Redis 可用时用 SET NX EX；否则降级进程内时间戳记录。
    """
    debounce = int(getattr(settings, "SENSITIVE_PATH_ALERT_DEBOUNCE_SECONDS", 300))
    redis = await get_redis_client()
    key = f"sensitive_probe:alert:{ip}"
    if redis:
        try:
            ok = await redis.set(key, "1", nx=True, ex=debounce)
            return bool(ok)
        except Exception:
            pass
    now = time.time()
    last = _mem_alert_ts.get(ip, 0.0)
    if now - last < debounce:
        return False
    _mem_alert_ts[ip] = now
    return True


async def _send_critical_alert(
    *,
    client_ip: str,
    path: str,
    matched_rule: str,
    level: SensitivePathLevel,
    hit_count: int,
    auto_blocked: bool,
) -> None:
    """向管理员 Telegram 推送危急等级敏感路径探测预警（受全局开关与防抖约束）。"""
    if not getattr(settings, "TELEGRAM_ENABLE", True):
        return
    if not getattr(settings, "SENSITIVE_PATH_ALERT_CRITICAL", True):
        return
    if not await _should_send_telegram_alert(client_ip):
        return
    try:
        from app.services.telegram_notification_service import TelegramNotificationService

        desc = (
            f"敏感路径【{level_label(int(level))}】探测\n"
            f"IP: {client_ip}\n"
            f"路径: {path}\n"
            f"规则: {matched_rule}\n"
            f"窗口内累计(L{int(level)}): {hit_count}\n"
            f"自动封禁: {'是' if auto_blocked else '否'}"
        )
        await TelegramNotificationService.send_system_alert(
            alert_type="敏感路径防护",
            description=desc,
            location={"module": "SensitivePathGuard", "function": "dispatch"},
            db=None,
        )
    except Exception as exc:
        logger.warning("敏感路径 Telegram 预警发送失败: %s", exc)


@dataclass
class HandleResult:
    """敏感路径命中后的处置结果，供中间件记录审计日志。"""

    action_taken: str  # 如 blocked_404、auto_blocked_ip
    auto_blocked: bool  # 是否本次新写入 IP 黑名单
    hit_count: int  # 滑动窗口内该等级累计命中次数


async def handle_probe_hit(
    *,
    client_ip: str,
    path: str,
    match: SensitivePathMatch,
) -> HandleResult:
    """
    记录命中次数，按等级策略执行自动封禁与预警。
    """
    policy = match.policy
    hit_count = await _hit_tracker.increment(client_ip, match.level)
    auto_blocked = False
    action_taken = "blocked_404"

    threshold = policy.auto_block_threshold
    if (
        threshold > 0
        and hit_count >= threshold
        and client_ip
        and client_ip != "unknown"
        and not _is_loopback_ip(client_ip)
    ):
        reason = (
            f"自动封禁：{level_label(int(match.level))}探测"
            f" {hit_count} 次/{_hit_tracker._window}s，规则 {match.matched_rule}"
        )
        auto_blocked = await _upsert_blocked_ip(client_ip, reason)
        if auto_blocked:
            action_taken = "auto_blocked_ip"
            logger.error(
                "敏感路径自动封禁IP: ip=%s level=%s hits=%s rule=%s",
                client_ip,
                level_label(int(match.level)),
                hit_count,
                match.matched_rule,
            )
    elif threshold > 0 and hit_count >= threshold and _is_loopback_ip(client_ip):
        logger.info(
            "敏感路径命中达阈值但跳过封禁本机回环: ip=%s hits=%s rule=%s",
            client_ip,
            hit_count,
            match.matched_rule,
        )

    if policy.telegram_alert:
        await _send_critical_alert(
            client_ip=client_ip,
            path=path,
            matched_rule=match.matched_rule,
            level=match.level,
            hit_count=hit_count,
            auto_blocked=auto_blocked,
        )

    return HandleResult(
        action_taken=action_taken,
        auto_blocked=auto_blocked,
        hit_count=hit_count,
    )
