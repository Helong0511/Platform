"""
Redis 异步客户端单例模块。

职责：维护全局连接池，供限流、CSRF、缓存、Cap 计数、点击队列等模块复用；不可用时返回 None 触发内存降级。

在系统中的位置：``app.core.redis_client.get_redis_client``，被 core 层绝大多数有状态组件引用。
"""
import asyncio
import logging
import os
import time
from typing import Optional
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    # Redis库未安装，使用内存存储
    REDIS_AVAILABLE = False
    aioredis = None
from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis连接池（全局单例，绑定创建时的事件循环）
_redis_client: Optional[aioredis.Redis] = None
_redis_loop: Optional[asyncio.AbstractEventLoop] = None
# 连接失败后短暂退避，避免每个请求都等待 socket_connect_timeout
_redis_connect_backoff_until: float = 0.0
_REDIS_CONNECT_BACKOFF_SECONDS = 60.0
# 连接池由 redis-py 自身做连接健康检查；应用层最多每 30 秒主动 ping 一次。
_REDIS_EXPLICIT_PING_INTERVAL_SECONDS = 30.0
_redis_last_ping_at: float = 0.0
_redis_dev_no_host_logged = False
_redis_dev_loopback_skip_logged = False
_redis_connect_lock: Optional[asyncio.Lock] = None

_LOOPBACK_REDIS_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _is_loopback_redis_host(host: Optional[str]) -> bool:
    if not host or not str(host).strip():
        return True
    return str(host).strip().lower() in _LOOPBACK_REDIS_HOSTS


def should_skip_redis_connect(
    *,
    is_production: bool,
    redis_host: Optional[str],
    redis_force: bool,
) -> bool:
    """
    非生产且 REDIS_HOST 指向本机 loopback 时跳过连接，直接内存降级。

    生产环境始终尝试连接；本机已装 Redis 时可设置环境变量 REDIS_FORCE=true 强制连接。
    """
    if is_production:
        return False
    if redis_force:
        return False
    return _is_loopback_redis_host(redis_host)


def _redis_force_enabled() -> bool:
    return os.getenv("REDIS_FORCE", "").strip().lower() in ("1", "true", "yes", "on")


def _redis_socket_connect_timeout() -> float:
    """开发环境缩短连接超时，避免本机无 Redis 时每请求阻塞数秒。"""
    return 1.0 if not settings.is_production else 5.0


def _mark_redis_connect_failed() -> None:
    global _redis_connect_backoff_until
    _redis_connect_backoff_until = time.monotonic() + _REDIS_CONNECT_BACKOFF_SECONDS


def _reset_redis_singleton(*, reset_connect_lock: bool = False) -> None:
    """丢弃当前单例引用（不在异构事件循环上 close，避免二次破坏）。"""
    global _redis_client, _redis_loop, _redis_connect_lock, _redis_connect_lock_loop, _redis_last_ping_at
    _redis_client = None
    _redis_loop = None
    _redis_last_ping_at = 0.0
    if reset_connect_lock:
        _redis_connect_lock = None
        _redis_connect_lock_loop = None


async def get_redis_client() -> Optional[aioredis.Redis]:
    """
    获取Redis客户端
    如果Redis未配置或连接失败，返回None（使用内存存储）
    """
    global _redis_client, _redis_loop, _redis_dev_no_host_logged, _redis_dev_loopback_skip_logged
    global _redis_connect_backoff_until, _redis_connect_lock, _redis_connect_lock_loop, _redis_last_ping_at

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        return None

    now = time.monotonic()
    if now < _redis_connect_backoff_until:
        return None

    # 热路径不再逐请求获取全局锁并 ping；redis-py 的连接池健康检查负责连接复用。
    if (
        _redis_client is not None
        and _redis_loop is current_loop
        and not current_loop.is_closed()
        and now - _redis_last_ping_at < _REDIS_EXPLICIT_PING_INTERVAL_SECONDS
    ):
        return _redis_client

    # 无论客户端是否已成功创建，都按事件循环隔离连接锁；
    # 首次连接失败时 _redis_loop 仍为 None，不能只依赖 _redis_loop 判断锁是否跨 loop。
    if _redis_loop is not None and (_redis_loop is not current_loop or _redis_loop.is_closed()):
        _reset_redis_singleton(reset_connect_lock=True)

    if (
        _redis_connect_lock is None
        or _redis_connect_lock_loop is not current_loop
        or (_redis_connect_lock_loop is not None and _redis_connect_lock_loop.is_closed())
    ):
        _redis_connect_lock = asyncio.Lock()
        _redis_connect_lock_loop = current_loop

    async with _redis_connect_lock:
        now = time.monotonic()
        if now < _redis_connect_backoff_until:
            return None

        # 双重检查：等待锁期间可能已有其他请求完成 ping 或连接初始化。
        if _redis_client is not None:
            if _redis_loop is not current_loop or _redis_loop.is_closed():
                logger.debug("Redis 客户端与当前事件循环不匹配，将重新连接")
                _reset_redis_singleton()
            elif now - _redis_last_ping_at < _REDIS_EXPLICIT_PING_INTERVAL_SECONDS:
                return _redis_client
            else:
                try:
                    await _redis_client.ping()
                    _redis_last_ping_at = time.monotonic()
                    return _redis_client
                except Exception as e:
                    logger.warning(f"Redis 低频健康检查失败: {e}，重置连接并退避")
                    _reset_redis_singleton()
                    _mark_redis_connect_failed()

        # 从配置中读取Redis连接信息
        redis_host = getattr(settings, 'REDIS_HOST', None) or None
        redis_port = getattr(settings, 'REDIS_PORT', None) or 6379
        redis_db = getattr(settings, 'REDIS_DB', None) or 0
        redis_password = getattr(settings, 'REDIS_PASSWORD', None) or None

        # 检查Redis库是否可用
        if not REDIS_AVAILABLE:
            logger.warning("Redis库未安装，将使用内存存储。安装命令: pip install redis>=6.0.0")
            return None

        # 如果未配置Redis，返回None（使用内存存储）
        if not redis_host:
            if settings.is_production:
                logger.warning(
                    "生产环境未配置Redis，将使用内存存储（多进程环境下可能不一致）。"
                    "请检查 .env 文件中的 REDIS_HOST 配置"
                )
            elif not _redis_dev_no_host_logged:
                logger.info("开发环境未配置 Redis，使用内存存储（限流/CSRF/缓存均为进程内）")
                _redis_dev_no_host_logged = True
            return None

        # 非生产 + 本机 loopback：无需改 .env，直接内存降级（生产环境不受影响）
        if should_skip_redis_connect(
            is_production=settings.is_production,
            redis_host=redis_host,
            redis_force=_redis_force_enabled(),
        ):
            if not _redis_dev_loopback_skip_logged:
                logger.info(
                    "开发环境 REDIS_HOST=%s 指向本机且未设置 REDIS_FORCE，"
                    "跳过 Redis 连接并使用内存存储（限流/CSRF/缓存均为进程内）",
                    redis_host,
                )
                _redis_dev_loopback_skip_logged = True
            return None

        connect_timeout = _redis_socket_connect_timeout()
        logger.debug(
            f"尝试连接Redis: {redis_host}:{redis_port}/{redis_db} "
            f"(密码: {'已设置' if redis_password else '未设置'}, 超时: {connect_timeout}s)"
        )

        try:
            max_connections = getattr(settings, 'REDIS_MAX_CONNECTIONS', 10)
            _redis_client = aioredis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,
                socket_connect_timeout=connect_timeout,
                socket_timeout=connect_timeout,
                health_check_interval=30,
                max_connections=max_connections,
                socket_keepalive=True,
                socket_keepalive_options={},
            )

            await _redis_client.ping()
            logger.info(f"Redis连接成功: {redis_host}:{redis_port}/{redis_db}")

            # 启动阶段只做 PING，不向共享 Redis 写入通用测试 key。
            _redis_loop = current_loop
            _redis_last_ping_at = time.monotonic()
            _redis_connect_backoff_until = 0.0
            return _redis_client
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Redis连接失败: {error_msg}，将使用内存存储。"
                f"连接配置: {redis_host}:{redis_port}/{redis_db}。"
                f"开发环境本机无 Redis 时无需改 REDIS_HOST；"
                f"若已安装本机 Redis 可设置 REDIS_FORCE=true；"
                f"{_REDIS_CONNECT_BACKOFF_SECONDS:.0f}s 内不再重试连接"
            )
            _reset_redis_singleton()
            _mark_redis_connect_failed()
            return None


async def close_redis_client():
    """
    关闭Redis连接
    """
    global _redis_client
    
    if _redis_client is not None:
        try:
            await _redis_client.close()
            logger.info("Redis连接已关闭")
        except Exception as e:
            logger.error(f"关闭Redis连接时出错: {e}")
        finally:
            _reset_redis_singleton()


async def reset_redis_client(reason: str = ""):
    """
    重置Redis连接（用于连接异常后的快速自愈）
    """
    global _redis_client
    if _redis_client is None:
        _mark_redis_connect_failed()
        return

    try:
        await _redis_client.close()
    except Exception as e:
        logger.debug(f"重置Redis连接时关闭失败: {e}")
    finally:
        _reset_redis_singleton()
        _mark_redis_connect_failed()

    if reason:
        logger.warning(f"Redis连接已重置，原因: {reason}")
