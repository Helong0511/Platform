"""
Redis 异步客户端单例模块。

职责：维护全局连接池，供限流、CSRF、缓存、Cap 计数、点击队列等模块复用；不可用时返回 None 触发内存降级。

在系统中的位置：``app.core.redis_client.get_redis_client``，被 core 层绝大多数有状态组件引用。
"""
import asyncio
import logging
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


def _reset_redis_singleton() -> None:
    """丢弃当前单例引用（不在异构事件循环上 close，避免二次破坏）。"""
    global _redis_client, _redis_loop
    _redis_client = None
    _redis_loop = None


async def get_redis_client() -> Optional[aioredis.Redis]:
    """
    获取Redis客户端
    如果Redis未配置或连接失败，返回None（使用内存存储）
    """
    global _redis_client, _redis_loop

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        return None

    # 事件循环切换或已关闭时（如 Telegram 线程 asyncio.run）不复用旧客户端
    if _redis_client is not None:
        if _redis_loop is not current_loop or _redis_loop.is_closed():
            logger.debug("Redis 客户端与当前事件循环不匹配，将重新连接")
            _reset_redis_singleton()
        else:
            try:
                await _redis_client.ping()
                return _redis_client
            except Exception as e:
                logger.warning(f"Redis连接测试失败: {e}，尝试重新连接")
                _reset_redis_singleton()
    
    # 从配置中读取Redis连接信息
    redis_host = getattr(settings, 'REDIS_HOST', None) or None
    redis_port = getattr(settings, 'REDIS_PORT', None) or 6379
    redis_db = getattr(settings, 'REDIS_DB', None) or 0
    redis_password = getattr(settings, 'REDIS_PASSWORD', None) or None
    
    # 检查Redis库是否可用
    if not REDIS_AVAILABLE:
        logger.warning("Redis库未安装，将使用内存存储。安装命令: pip install redis>=5.0.0")
        return None
    
    # 如果未配置Redis，返回None（使用内存存储）
    if not redis_host:
        if settings.is_production:
            logger.warning(
                f"生产环境未配置Redis，将使用内存存储（多进程环境下可能不一致）。"
                f"请检查 .env 文件中的 REDIS_HOST 配置（当前值: {redis_host}）"
            )
        else:
            logger.info(f"开发环境未配置Redis，使用内存存储（REDIS_HOST={redis_host}）")
        return None
    
    # 记录尝试连接的配置信息（不记录密码）
    logger.debug(f"尝试连接Redis: {redis_host}:{redis_port}/{redis_db} (密码: {'已设置' if redis_password else '未设置'})")
    
    try:
        # 创建Redis连接池（高并发优化）
        # 使用连接池提高并发性能，避免连接竞争
        max_connections = getattr(settings, 'REDIS_MAX_CONNECTIONS', 10)
        _redis_client = aioredis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,  # 自动解码响应为字符串
            socket_connect_timeout=5,  # 连接超时5秒
            socket_timeout=5,  # 操作超时5秒
            retry_on_timeout=True,  # 超时重试
            health_check_interval=30,  # 健康检查间隔30秒
            max_connections=max_connections,  # 连接池最大连接数
            socket_keepalive=True,  # 启用TCP keepalive
            socket_keepalive_options={},  # TCP keepalive选项
        )
        
        # 测试连接
        await _redis_client.ping()
        logger.info(f"Redis连接成功: {redis_host}:{redis_port}/{redis_db}")
        
        # 测试设置和获取操作
        test_key = "test:redis:connection"
        test_value = "ok"
        await _redis_client.setex(test_key, 60, test_value)
        retrieved_value = await _redis_client.get(test_key)
        if retrieved_value == test_value:
            logger.info("Redis读写操作测试成功")
        else:
            logger.warning("Redis读写操作测试失败")

        _redis_loop = current_loop
        return _redis_client
    except Exception as e:
        error_msg = str(e)
        logger.error(
            f"Redis连接失败: {error_msg}，将使用内存存储。"
            f"连接配置: {redis_host}:{redis_port}/{redis_db}。"
            f"请检查：1) Redis服务是否运行 2) 端口是否正确 3) 密码是否正确 4) 防火墙是否阻止连接"
        )
        _reset_redis_singleton()
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
        return

    try:
        await _redis_client.close()
    except Exception as e:
        logger.debug(f"重置Redis连接时关闭失败: {e}")
    finally:
        _reset_redis_singleton()

    if reason:
        logger.warning(f"Redis连接已重置，原因: {reason}")

