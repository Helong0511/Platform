"""
CSRF防护模块
提供CSRF令牌生成、验证和中间件
"""
import secrets
import logging
import hashlib
from typing import Optional, Dict
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from app.core.config import settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# CSRF令牌存储（内存存储，Redis不可用时使用）
_csrf_tokens: Dict[str, str] = {}


def extract_user_id_from_token(request: Request) -> Optional[str]:
    """
    从请求的JWT token中提取用户ID（如果存在）
    用于生成更精确的CSRF session_id，支持同一用户多设备登录
    
    参数:
        request: FastAPI请求对象
    
    返回:
        用户ID字符串，如果无法提取则返回None
    """
    try:
        # 1. 优先从 Authorization 头获取 token
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "").strip()
        
        # 2. 如果头中没有，从 Cookie 中获取 (支持安全增强模式)
        if not token:
            token = request.cookies.get("access_token")
            
        if not token:
            return None
        
        # 尝试解码JWT token（不验证签名，只提取用户ID）
        # 注意：这里只提取payload，不进行完整验证（因为可能在CSRF中间件之前执行）
        from jose import jwt
        from jose.exceptions import JWTError
        
        try:
            # 不验证签名，只解码payload（用于获取用户ID）
            # 注意：某些版本的python-jose需要密钥参数，即使verify_signature=False
            payload = jwt.decode(
                token,
                "",  # 空字符串作为密钥（因为不验证签名）
                options={"verify_signature": False, "verify_exp": False}
            )
            user_id = payload.get("sub")
            if user_id:
                return str(user_id)
        except JWTError:
            # token格式错误，无法提取用户ID
            pass
    except Exception as e:
        # 提取失败不影响CSRF功能，静默处理
        logger.debug(f"提取用户ID失败: {e}")
    
    return None


def generate_csrf_token() -> str:
    """
    生成CSRF令牌
    
    使用密码学安全的随机数生成器生成32字符的URL安全随机字符串。
    令牌提供足够的熵（约256位），确保安全性。
    
    返回:
        32字符的URL安全随机字符串
    """
    return secrets.token_urlsafe(32)


def get_csrf_token_from_request(request: Request) -> Optional[str]:
    """
    从请求中获取CSRF令牌
    支持从以下位置获取：
    1. 请求头：X-CSRF-Token
    2. 表单数据：csrf_token
    3. 查询参数：csrf_token（仅用于GET请求）
    """
    # 1. 从请求头获取
    token = request.headers.get("X-CSRF-Token")
    if token:
        return token
    
    # 2. 从表单数据获取（POST/PUT/PATCH/DELETE）
    # 注意：FastAPI的request.form()是异步的，需要在中间件中特殊处理
    # 这里主要从请求头获取，表单数据在端点中处理
    
    # 3. 从查询参数获取（仅用于GET请求）
    if request.method == "GET":
        token = request.query_params.get("csrf_token")
        if token:
            return token
    
    return None


def is_safe_method(method: str) -> bool:
    """
    判断HTTP方法是否安全（不需要CSRF保护）
    安全方法：GET, HEAD, OPTIONS, TRACE
    """
    return method.upper() in ["GET", "HEAD", "OPTIONS", "TRACE"]


def should_skip_csrf_check(request: Request) -> bool:
    """
    判断是否应该跳过CSRF检查
    跳过条件：
    1. 安全方法（GET, HEAD, OPTIONS, TRACE）
    2. 登录接口（使用JWT，不需要CSRF）
    3. 客户API接口（使用签名验证，不需要CSRF）
    4. Macan S2S PostBack接口（外部回调接口，使用参数验证，不需要CSRF）
    5. 静态资源
    """
    path = request.url.path
    method = request.method
    
    # 安全方法不需要CSRF保护
    if is_safe_method(method):
        return True
    
    # 登录接口使用JWT，不需要CSRF
    # 精确匹配 /api/v1/auth/login 和 /api/v1/auth/logout
    if path == "/api/v1/auth/login" or path == "/api/v1/auth/logout":
        logger.debug(f"跳过CSRF检查（登录接口）: {method} {path}")
        return True
    
    # 客户API接口使用签名验证，不需要CSRF
    # 精确匹配客户API接口
    if path == "/api/v1/client_products" or path == "/api/v1/client_data":
        return True
    
    # Macan S2S PostBack接口（外部回调接口，使用参数验证，不需要CSRF）
    if path == "/api/v1/macan/postback":
        logger.debug(f"跳过CSRF检查（Macan PostBack接口）: {method} {path}")
        return True
    
    # 客户端错误记录接口（用于记录前端错误，即使失败也不应影响用户体验，跳过CSRF检查）
    if path == "/api/v1/audit-logs/client-error":
        logger.debug(f"跳过CSRF检查（客户端错误记录接口）: {method} {path}")
        return True
    
    # 静态资源不需要CSRF
    if path.startswith("/static/") or path.startswith("/assets/"):
        return True
    
    # API文档不需要CSRF（开发环境）
    if path.startswith("/api/v1/docs") or path.startswith("/api/v1/redoc") or path.startswith("/api/v1/openapi.json"):
        return True
    
    # 短链接重定向路由（公开访问，无需认证）
    if path.startswith("/s/"):
        return True
    
    return False


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF防护中间件
    为所有需要CSRF保护的请求生成和验证CSRF令牌
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.app = app
    
    async def dispatch(self, request: Request, call_next):
        # 快速检查：登录接口和定时任务接口直接跳过（最优先）
        path = request.url.path
        method = request.method.upper()
        
        # 短链接重定向路由（公开访问，无需认证）- 最优先检查
        # 检查路径是否以 /s/ 开头（支持 /s/xxx 格式）
        if path and path.startswith("/s/"):
            logger.info(f"跳过CSRF检查（短链接重定向）: {method} {path}")
            return await call_next(request)
        
        # 精确匹配登录/登出接口
        if path == "/api/v1/auth/login" or path == "/api/v1/auth/logout":
            logger.debug(f"跳过CSRF检查（登录接口）: {method} {path}")
            return await call_next(request)
        
        # Macan S2S PostBack接口（外部回调接口，不需要CSRF）
        if path == "/api/v1/macan/postback":
            logger.debug(f"跳过CSRF检查（Macan PostBack接口）: {method} {path}")
            return await call_next(request)
        
        # 客户端错误记录接口（用于记录前端错误，即使失败也不应影响用户体验，跳过CSRF检查）
        if path == "/api/v1/audit-logs/client-error":
            logger.debug(f"跳过CSRF检查（客户端错误记录接口）: {method} {path}")
            return await call_next(request)
        
        # 定时任务接口已有JWT认证和管理员权限检查，跳过CSRF
        # 精确匹配触发和重载接口
        if path.startswith("/api/v1/scheduled-tasks/"):
            if path.endswith("/trigger") or path.endswith("/reload") or path == "/api/v1/scheduled-tasks/reload-all":
                logger.debug(f"跳过CSRF检查（定时任务接口）: {request.method} {path}")
                return await call_next(request)
        
        # 如果应该跳过CSRF检查，但仍然需要为GET请求返回CSRF令牌
        if should_skip_csrf_check(request):
            # 对于GET请求，即使跳过检查，也要生成并返回CSRF令牌
            if request.method == "GET":
                # 生成新的CSRF令牌
                csrf_token = generate_csrf_token()
                
                # 获取客户端标识（用于存储CSRF令牌）
                from app.core.utils import get_client_ip
                client_ip = get_client_ip(request)
                
                # 尝试从JWT token中提取用户ID（如果存在）
                # 这样可以支持同一用户多设备登录，每个设备有独立的CSRF令牌
                user_id = extract_user_id_from_token(request)
                
                # 获取或生成会话标识
                # 如果能够获取用户ID，使用 user_id:IP:hash(User-Agent)
                # 否则回退到 IP:hash(User-Agent)（向后兼容）
                # 使用hashlib.sha256生成稳定的hash值，避免Python hash()在不同进程中的随机化问题
                user_agent = request.headers.get("User-Agent", "")[:100]  # 限制长度
                user_agent_hash = hashlib.sha256(user_agent.encode('utf-8')).hexdigest()[:16]  # 使用SHA256前16位
                if user_id:
                    session_id = f"{user_id}:{client_ip}:{user_agent_hash}"
                else:
                    session_id = f"{client_ip}:{user_agent_hash}"
                
                # 尝试使用Redis存储CSRF令牌
                redis_client = await get_redis_client()
                csrf_key = f"csrf_token:{session_id}"
                
                # 存储令牌（优先使用Redis）
                if redis_client:
                    try:
                        await redis_client.setex(
                            csrf_key,
                            settings.CSRF_TOKEN_EXPIRE_SECONDS,
                            csrf_token
                        )
                        # 同时更新内存存储（作为备份）
                        _csrf_tokens[session_id] = csrf_token
                    except Exception as e:
                        error_msg = str(e) or repr(e) or "未知错误"
                        logger.warning(f"Redis CSRF令牌存储失败: {error_msg}，使用内存存储")
                        _csrf_tokens[session_id] = csrf_token
                else:
                    _csrf_tokens[session_id] = csrf_token
                
                # 处理请求并添加CSRF令牌
                response = await call_next(request)
                response.headers["X-CSRF-Token"] = csrf_token
                logger.debug(f"跳过CSRF检查但返回CSRF令牌: {request.method} {path}")
                return response
            else:
                logger.debug(f"跳过CSRF检查: {request.method} {path}")
                return await call_next(request)
        
        logger.debug(f"执行CSRF检查: {request.method} {path}")
        
        # 获取客户端标识（用于存储CSRF令牌）
        from app.core.utils import get_client_ip
        client_ip = get_client_ip(request)
        
        # 尝试从JWT token中提取用户ID（如果存在）
        # 这样可以支持同一用户多设备登录，每个设备有独立的CSRF令牌
        user_id = extract_user_id_from_token(request)
        
        # 获取或生成会话标识
        # 如果能够获取用户ID，使用 user_id:IP:hash(User-Agent)
        # 否则回退到 IP:hash(User-Agent)（向后兼容）
        # 使用hashlib.sha256生成稳定的hash值，避免Python hash()在不同进程中的随机化问题
        # 注意：必须与GET请求中的hash算法保持一致，否则会导致session_id不匹配
        user_agent = request.headers.get("User-Agent", "")[:100]  # 限制长度
        user_agent_hash = hashlib.sha256(user_agent.encode('utf-8')).hexdigest()[:16]  # 使用SHA256前16位
        if user_id:
            session_id = f"{user_id}:{client_ip}:{user_agent_hash}"
        else:
            session_id = f"{client_ip}:{user_agent_hash}"
        
        # 尝试使用Redis存储CSRF令牌
        redis_client = await get_redis_client()
        csrf_key = f"csrf_token:{session_id}"
        
        # 如果是GET请求，生成并返回CSRF令牌
        if request.method == "GET":
            # 先检查Redis中是否已存在令牌（多进程环境下，避免重复生成）
            csrf_token = None
            if redis_client:
                try:
                    existing_token = await redis_client.get(csrf_key)
                    if existing_token:
                        csrf_token = existing_token.decode('utf-8') if isinstance(existing_token, bytes) else existing_token
                        # 更新内存存储（作为备份）
                        _csrf_tokens[session_id] = csrf_token
                        user_agent = request.headers.get("User-Agent", "")
                        user_agent_hash = hashlib.sha256(user_agent.encode('utf-8')).hexdigest()[:16]
                        logger.debug(
                            f"从Redis获取现有CSRF令牌: {request.method} {path}\n"
                            f"  IP: {client_ip}\n"
                            f"  Session ID: {session_id}\n"
                            f"  User ID: {user_id}\n"
                            f"  CSRF Key: {csrf_key}\n"
                            f"  令牌: {csrf_token[:10]}..."
                        )
                except Exception as e:
                    error_msg = str(e) or repr(e) or "未知错误"
                    logger.warning(f"Redis CSRF令牌获取失败: {error_msg}，将生成新令牌")
            
            # 如果Redis中没有，检查内存存储
            if not csrf_token:
                csrf_token = _csrf_tokens.get(session_id)
                if csrf_token:
                    user_agent = request.headers.get("User-Agent", "")
                    user_agent_hash = hashlib.sha256(user_agent.encode('utf-8')).hexdigest()[:16]
                    logger.debug(
                        f"从内存存储获取现有CSRF令牌: {request.method} {path}\n"
                        f"  IP: {client_ip}\n"
                        f"  Session ID: {session_id}\n"
                        f"  User ID: {user_id}\n"
                        f"  CSRF Key: {csrf_key}\n"
                        f"  令牌: {csrf_token[:10]}..."
                    )
                    # 如果Redis可用，同步到Redis
                    if redis_client:
                        try:
                            await redis_client.setex(
                                csrf_key,
                                settings.CSRF_TOKEN_EXPIRE_SECONDS,
                                csrf_token
                            )
                            logger.debug(f"已将内存中的CSRF令牌同步到Redis: {csrf_key}")
                        except Exception as e:
                            logger.warning(f"同步CSRF令牌到Redis失败: {str(e)}")
            
            # 如果都没有，生成新的CSRF令牌
            if not csrf_token:
                csrf_token = generate_csrf_token()
                user_agent = request.headers.get("User-Agent", "")
                user_agent_hash = hashlib.sha256(user_agent.encode('utf-8')).hexdigest()[:16]
                logger.info(
                    f"生成新的CSRF令牌: {request.method} {path}\n"
                    f"  IP: {client_ip}\n"
                    f"  User-Agent: {user_agent[:100]}\n"
                    f"  User-Agent Hash: {user_agent_hash}\n"
                    f"  Session ID: {session_id}\n"
                    f"  User ID: {user_id}\n"
                    f"  CSRF Key: {csrf_key}\n"
                    f"  令牌: {csrf_token[:10]}..."
                )
            
            # 存储令牌（优先使用Redis）
            if redis_client:
                try:
                    await redis_client.setex(
                        csrf_key,
                        settings.CSRF_TOKEN_EXPIRE_SECONDS,
                        csrf_token
                    )
                    # 同时更新内存存储（作为备份）
                    _csrf_tokens[session_id] = csrf_token
                    logger.debug(
                        f"已存储CSRF令牌到Redis和内存: {request.method} {path}\n"
                        f"  CSRF Key: {csrf_key}\n"
                        f"  Session ID: {session_id}\n"
                        f"  过期时间: {settings.CSRF_TOKEN_EXPIRE_SECONDS}秒\n"
                        f"  令牌: {csrf_token[:10]}..."
                    )
                except Exception as e:
                    error_msg = str(e) or repr(e) or "未知错误"
                    logger.warning(f"Redis CSRF令牌存储失败: {error_msg}，使用内存存储")
                    _csrf_tokens[session_id] = csrf_token
            else:
                _csrf_tokens[session_id] = csrf_token
                logger.debug(
                    f"已存储CSRF令牌到内存: {request.method} {path}\n"
                    f"  Session ID: {session_id}\n"
                    f"  令牌: {csrf_token[:10]}..."
                )
            
            # 处理请求
            try:
                response = await call_next(request)
                # 在响应头中添加CSRF令牌（即使请求失败，也添加CSRF令牌）
                try:
                    response.headers["X-CSRF-Token"] = csrf_token
                    logger.debug(f"已添加CSRF令牌到响应头: {request.method} {path}")
                except (ConnectionError, OSError, RuntimeError) as e:
                    # 如果连接已关闭，无法修改响应头，直接重新抛出流异常
                    error_type_name = type(e).__name__
                    error_module = type(e).__module__
                    if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
                        "anyio" in error_module):
                        logger.debug(f"响应流已关闭，无法添加CSRF令牌: {request.method} {path}, IP: {client_ip}")
                        raise
                    # 其他连接错误也重新抛出
                    raise
                return response
            except (ConnectionError, OSError, RuntimeError) as e:
                # 处理连接中断或流关闭的情况
                error_type_name = type(e).__name__
                error_module = type(e).__module__
                if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
                    "anyio" in error_module):
                    logger.debug(f"请求流已关闭: {request.method} {path}, IP: {client_ip}")
                    raise
                # 其他连接错误也重新抛出
                raise
            except Exception as e:
                # 如果请求处理失败，仍然需要返回CSRF令牌
                # 这样前端可以在错误响应中获取CSRF令牌
                # 注意：这里不能直接修改异常响应，需要通过异常处理器处理
                # 但CSRF令牌已经存储，前端可以通过下一个GET请求获取
                raise
        
        # 对于非安全方法（POST, PUT, PATCH, DELETE），验证CSRF令牌
        try:
            csrf_token = get_csrf_token_from_request(request)
            
            if not csrf_token:
                logger.warning(f"CSRF令牌缺失: {request.method} {request.url.path}, IP: {client_ip}, session_id: {session_id}")
                # 检查连接是否仍然有效（避免在客户端断开连接后抛出异常）
                try:
                    if hasattr(request, '_is_disconnected') and request._is_disconnected:
                        logger.debug("客户端已断开连接，跳过CSRF验证")
                        return await call_next(request)
                except Exception:
                    pass
                
                # 使用安全的异常抛出机制
                from app.core.csrf_utils import safe_raise_csrf_exception
                try:
                    safe_raise_csrf_exception(
                        request,
                        "CSRF令牌缺失，请刷新页面后重试",
                        status.HTTP_403_FORBIDDEN
                    )
                except Exception as e:
                    # 如果连接已断开，直接重新抛出流异常，不调用 call_next
                    error_type = type(e).__name__
                    error_module = type(e).__module__
                    if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                        "anyio" in error_module or "Connection disconnected" in str(e)):
                        logger.debug("客户端已断开连接，跳过CSRF验证")
                        # 不调用 call_next，因为连接已断开，直接抛出流异常
                        from anyio import EndOfStream
                        raise EndOfStream("客户端已断开连接")
                    raise
            
            # 验证CSRF令牌（优先从Redis获取）
            stored_token = None
            redis_available = False
            if redis_client:
                try:
                    stored_token = await redis_client.get(csrf_key)
                    if stored_token:
                        stored_token = stored_token.decode('utf-8') if isinstance(stored_token, bytes) else stored_token
                        # 从Redis获取到令牌后，同步更新内存存储（确保多进程一致性）
                        _csrf_tokens[session_id] = stored_token
                        redis_available = True
                        logger.debug(f"从Redis获取CSRF令牌并同步到内存: {csrf_key}, 令牌: {stored_token[:10]}...")
                except Exception as e:
                    error_msg = str(e) or repr(e) or "未知错误"
                    logger.warning(f"Redis CSRF令牌获取失败: {error_msg}，尝试使用内存存储")
            
            # 如果Redis中没有找到令牌，尝试从内存存储获取（仅当Redis不可用或Redis中没有时）
            if not stored_token:
                stored_token = _csrf_tokens.get(session_id)
                if stored_token:
                    logger.debug(f"从内存存储获取CSRF令牌: {session_id}, 令牌: {stored_token[:10]}...")
                    # 如果Redis可用，尝试将内存中的令牌同步到Redis（可能内存中的令牌是最新的）
                    if redis_client and not redis_available:
                        try:
                            await redis_client.setex(
                                csrf_key,
                                settings.CSRF_TOKEN_EXPIRE_SECONDS,
                                stored_token
                            )
                            logger.debug(f"已将内存中的CSRF令牌同步到Redis: {csrf_key}")
                        except Exception as e:
                            logger.warning(f"同步内存令牌到Redis失败: {str(e)}")
                # 如果仍然找不到，且使用了user_id，尝试不带user_id的session_id
                if not stored_token and user_id:
                    fallback_session_id = f"{client_ip}:{user_agent_hash}"
                    fallback_csrf_key = f"csrf_token:{fallback_session_id}"
                    # 尝试从Redis获取
                    if redis_client:
                        try:
                            stored_token = await redis_client.get(fallback_csrf_key)
                            if stored_token:
                                stored_token = stored_token.decode('utf-8') if isinstance(stored_token, bytes) else stored_token
                        except Exception:
                            pass
                    # 如果Redis也没有，尝试从内存存储获取
                    if not stored_token:
                        stored_token = _csrf_tokens.get(fallback_session_id)
                        # 如果找到了，更新到正确的session_id（使用user_id的）
                        if stored_token:
                            logger.debug(
                                f"使用回退session_id找到CSRF令牌，更新到正确session_id\n"
                                f"  回退session_id: {fallback_session_id}\n"
                                f"  正确session_id: {session_id}\n"
                                f"  令牌: {stored_token[:10]}..."
                            )
                            if redis_client:
                                try:
                                    await redis_client.setex(
                                        csrf_key,
                                        settings.CSRF_TOKEN_EXPIRE_SECONDS,
                                        stored_token
                                    )
                                    logger.debug(f"已将回退令牌同步到Redis: {csrf_key}")
                                except Exception as e:
                                    logger.warning(f"同步回退令牌到Redis失败: {str(e)}")
                            _csrf_tokens[session_id] = stored_token
            
            if not stored_token:
                # CSRF令牌不存在（可能是服务器重启导致内存存储丢失）
                # 对于非GET请求，如果是第一次请求（可能是服务器重启后的第一个请求），
                # 可以考虑生成新token并允许请求通过（但这样会降低安全性）
                # 为了安全，我们仍然拒绝请求，但会在响应头中返回新的CSRF token
                logger.warning(f"CSRF令牌不存在: {request.method} {request.url.path}, IP: {client_ip}, session_id: {session_id}, user_id: {user_id}")
                
                # 检查连接是否仍然有效（避免在客户端断开连接后抛出异常）
                try:
                    if hasattr(request, '_is_disconnected') and request._is_disconnected:
                        logger.debug("客户端已断开连接，跳过CSRF验证")
                        return await call_next(request)
                except Exception:
                    pass
                
                # 生成新的CSRF token并存储（即使验证失败，也提供新token给前端）
                new_csrf_token = generate_csrf_token()
                if redis_client:
                    try:
                        await redis_client.setex(
                            csrf_key,
                            settings.CSRF_TOKEN_EXPIRE_SECONDS,
                            new_csrf_token
                        )
                        _csrf_tokens[session_id] = new_csrf_token
                    except Exception:
                        _csrf_tokens[session_id] = new_csrf_token
                else:
                    _csrf_tokens[session_id] = new_csrf_token
                
                # 使用安全的异常抛出机制，但会在异常响应中包含新的CSRF token
                from app.core.csrf_utils import safe_raise_csrf_exception
                try:
                    safe_raise_csrf_exception(
                        request,
                        "CSRF令牌无效或已过期，请刷新页面后重试",
                        status.HTTP_403_FORBIDDEN
                    )
                except Exception as e:
                    # 如果连接已断开，直接重新抛出流异常，不调用 call_next
                    error_type = type(e).__name__
                    error_module = type(e).__module__
                    if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                        "anyio" in error_module or "Connection disconnected" in str(e)):
                        logger.debug("客户端已断开连接，跳过CSRF验证")
                        # 不调用 call_next，因为连接已断开，直接抛出流异常
                        from anyio import EndOfStream
                        raise EndOfStream("客户端已断开连接")
                    raise
                except HTTPException as http_exc:
                    # 在异常响应中添加新的CSRF token（通过响应头）
                    # 注意：这里不能直接修改响应，需要通过异常处理器处理
                    # 但我们可以通过设置一个标记，让异常处理器知道需要添加CSRF token
                    http_exc._csrf_token = new_csrf_token
                    raise http_exc
            
            # 使用安全的字符串比较（防止时序攻击）
            if not secrets.compare_digest(csrf_token, stored_token):
                # 检查连接是否仍然有效
                try:
                    if hasattr(request, '_is_disconnected') and request._is_disconnected:
                        logger.debug("客户端已断开连接，跳过CSRF验证")
                        return await call_next(request)
                except Exception:
                    pass
                
                # 安全地显示令牌前缀（避免空字符串或None导致的错误）
                stored_prefix = stored_token[:10] if stored_token and len(stored_token) > 10 else (stored_token or "None")
                csrf_prefix = csrf_token[:10] if csrf_token and len(csrf_token) > 10 else (csrf_token or "None")
                
                # 记录详细的调试信息
                user_agent = request.headers.get("User-Agent", "")
                user_agent_hash = hashlib.sha256(user_agent.encode('utf-8')).hexdigest()[:16]
                
                # 检查Redis和内存存储中的令牌
                redis_token_info = "未检查"
                memory_token_info = "未检查"
                if redis_client:
                    try:
                        redis_token = await redis_client.get(csrf_key)
                        if redis_token:
                            redis_token = redis_token.decode('utf-8') if isinstance(redis_token, bytes) else redis_token
                            redis_token_info = f"存在: {redis_token[:10]}..." if len(redis_token) > 10 else f"存在: {redis_token}"
                        else:
                            redis_token_info = "不存在"
                    except Exception as e:
                        redis_token_info = f"检查失败: {str(e)}"
                
                memory_token = _csrf_tokens.get(session_id)
                if memory_token:
                    memory_token_info = f"存在: {memory_token[:10]}..." if len(memory_token) > 10 else f"存在: {memory_token}"
                else:
                    memory_token_info = "不存在"
                
                # 记录完整的调试信息
                logger.warning(
                    f"CSRF令牌不匹配: {request.method} {request.url.path}\n"
                    f"  IP: {client_ip}\n"
                    f"  User-Agent: {user_agent[:100]}\n"
                    f"  User-Agent Hash: {user_agent_hash}\n"
                    f"  Session ID: {session_id}\n"
                    f"  User ID: {user_id}\n"
                    f"  CSRF Key: {csrf_key}\n"
                    f"  Redis中的令牌: {redis_token_info}\n"
                    f"  内存中的令牌: {memory_token_info}\n"
                    f"  期望的令牌: {stored_prefix}...\n"
                    f"  实际的令牌: {csrf_prefix}..."
                )
                
                # 检查是否是服务器重启后的情况（内存中没有该session的token）
                # 如果是，生成新token并在响应头返回，方便前端自动重试
                memory_token = _csrf_tokens.get(session_id)
                is_server_restart = (memory_token is None) and (stored_token is not None)
                
                if is_server_restart:
                    logger.info(
                        f"检测到可能是服务器重启后的CSRF令牌不匹配，生成新token: {request.method} {request.url.path}, "
                        f"IP: {client_ip}, session_id: {session_id}"
                    )
                    # 生成新的CSRF token并存储
                    new_csrf_token = generate_csrf_token()
                    if redis_client:
                        try:
                            await redis_client.setex(
                                csrf_key,
                                settings.CSRF_TOKEN_EXPIRE_SECONDS,
                                new_csrf_token
                            )
                            _csrf_tokens[session_id] = new_csrf_token
                        except Exception:
                            _csrf_tokens[session_id] = new_csrf_token
                    else:
                        _csrf_tokens[session_id] = new_csrf_token
                
                # 检查连接是否仍然有效（在抛出异常前）
                try:
                    if hasattr(request, '_is_disconnected') and request._is_disconnected:
                        logger.debug("客户端已断开连接，跳过CSRF验证")
                        # 连接已断开，直接抛出流异常，不调用 call_next
                        from anyio import EndOfStream
                        raise EndOfStream("客户端已断开连接")
                except EndOfStream:
                    # 如果已经是流异常，直接重新抛出
                    raise
                except Exception:
                    pass
                
                # 使用安全的异常抛出机制
                from app.core.csrf_utils import safe_raise_csrf_exception
                try:
                    # 如果是服务器重启后的情况，在异常中附加新token，让异常处理器在响应头返回
                    http_exc = None
                    if is_server_restart:
                        try:
                            safe_raise_csrf_exception(
                                request,
                                "CSRF令牌验证失败（可能是服务器重启导致），请刷新页面后重试",
                                status.HTTP_403_FORBIDDEN
                            )
                        except HTTPException as exc:
                            # 在异常中附加新token，让异常处理器在响应头返回
                            exc._csrf_token = new_csrf_token
                            http_exc = exc
                            raise exc
                    else:
                        safe_raise_csrf_exception(
                            request,
                            "CSRF令牌验证失败，请刷新页面后重试",
                            status.HTTP_403_FORBIDDEN
                        )
                except Exception as e:
                    # 如果连接已断开，直接重新抛出流异常
                    error_type = type(e).__name__
                    error_module = type(e).__module__
                    if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                        "anyio" in error_module or "Connection disconnected" in str(e)):
                        logger.debug("客户端已断开连接，跳过CSRF验证")
                        # 不调用 call_next，因为连接已断开，直接抛出流异常
                        from anyio import EndOfStream
                        raise EndOfStream("客户端已断开连接")
                    raise
            
            # 验证通过，继续处理请求
            response = await call_next(request)
            
            # 在响应头中添加CSRF令牌（确保前端可以更新令牌）
            # 使用存储的令牌（如果存在），否则使用请求中的令牌
            token_to_return = stored_token or csrf_token
            if token_to_return:
                try:
                    response.headers["X-CSRF-Token"] = token_to_return
                    logger.debug(f"已添加CSRF令牌到响应头: {request.method} {path}")
                except (ConnectionError, OSError, RuntimeError) as e:
                    # 如果连接已关闭，无法修改响应头，记录日志但不抛出异常
                    error_type_name = type(e).__name__
                    error_module = type(e).__module__
                    if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
                        "anyio" in error_module):
                        logger.debug(f"响应流已关闭，无法添加CSRF令牌: {request.method} {path}, IP: {client_ip}")
                    else:
                        logger.warning(f"无法添加CSRF令牌到响应头: {request.method} {path}, IP: {client_ip}, 错误: {e}")
                except Exception as e:
                    # 其他异常，记录日志但不影响响应
                    logger.warning(f"添加CSRF令牌到响应头时出错: {request.method} {path}, IP: {client_ip}, 错误: {e}")
        except HTTPException as http_exc:
            # 检查连接是否仍然有效
            # 如果连接已断开，不抛出异常，避免EndOfStream错误
            try:
                if hasattr(request, '_is_disconnected') and request._is_disconnected:
                    # 客户端已断开连接，不抛出异常，直接重新抛出流异常
                    logger.debug("客户端已断开连接，跳过CSRF异常处理")
                    from anyio import EndOfStream
                    raise EndOfStream("客户端已断开连接")
            except Exception as e:
                # 如果已经是 EndOfStream，直接重新抛出
                error_type = type(e).__name__
                error_module = type(e).__module__
                if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                    "anyio" in error_module):
                    raise
            
            # 检查 scope 中是否有连接断开标记
            try:
                if hasattr(request, 'scope') and isinstance(request.scope, dict):
                    if request.scope.get('_disconnected', False):
                        logger.debug("从 scope 检测到连接已断开，跳过CSRF异常处理")
                        from anyio import EndOfStream
                        raise EndOfStream("客户端已断开连接")
            except Exception as e:
                # 如果已经是 EndOfStream，直接重新抛出
                error_type = type(e).__name__
                error_module = type(e).__module__
                if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                    "anyio" in error_module):
                    raise
            
            # 重新抛出HTTPException，让异常处理器处理
            # 注意：如果连接已断开，异常处理器会在尝试发送响应时捕获EndOfStream异常
            raise http_exc
        except Exception as stream_exc:
            # 捕获 safe_raise_csrf_exception 抛出的连接断开异常
            error_type = type(stream_exc).__name__
            error_module = type(stream_exc).__module__
            if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                "anyio" in error_module or "Connection disconnected" in str(stream_exc)):
                logger.debug("客户端已断开连接，跳过CSRF异常处理")
                # 直接重新抛出原始的流异常，而不是创建新的
                raise stream_exc
            # 其他异常，重新抛出
            raise
        except (ConnectionError, OSError, RuntimeError) as e:
            # 处理连接中断或流关闭的情况
            # 这些异常通常表示客户端提前关闭了连接
            error_type_name = type(e).__name__
            error_module = type(e).__module__
            # 检查是否是 anyio 的流异常
            if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
                "anyio" in error_module):
                logger.debug(f"请求流已关闭: {request.method} {request.url.path}, IP: {client_ip}")
                # 对于流关闭的情况，直接重新抛出，让上层处理
                # 不要尝试抛出 HTTPException，因为流已经关闭
                raise
            else:
                logger.warning(f"CSRF验证过程中连接错误: {request.method} {request.url.path}, IP: {client_ip}, 错误: {str(e)}")
                raise
        except Exception as e:
            # 其他未预期的异常
            error_type_name = type(e).__name__
            error_module = type(e).__module__
            # 如果是流相关的异常，直接重新抛出
            if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
                "anyio" in error_module):
                logger.debug(f"请求流异常: {request.method} {request.url.path}, IP: {client_ip}")
                raise
            logger.error(f"CSRF验证过程中发生未预期的错误: {request.method} {request.url.path}, IP: {client_ip}, 错误: {str(e)}", exc_info=True)
            raise
        
        # 注意：不再在每次请求后都更新CSRF令牌，避免并发请求时的竞态条件
        # 只在以下情况更新令牌：
        # 1. 首次生成令牌（GET请求）
        # 2. 令牌过期需要刷新
        # 这样前端可以安全地使用同一个令牌发送多个请求，避免令牌不匹配的问题
        
        # 检查令牌是否即将过期（剩余时间少于总时间的20%），如果是则刷新
        should_refresh = False
        if redis_client:
            try:
                ttl = await redis_client.ttl(csrf_key)
                # 如果TTL小于总过期时间的20%，则刷新令牌
                if ttl > 0 and ttl < (settings.CSRF_TOKEN_EXPIRE_SECONDS * 0.2):
                    should_refresh = True
                    logger.debug(f"CSRF令牌即将过期（剩余{ttl}秒），刷新令牌: {request.method} {request.url.path}, IP: {client_ip}")
            except Exception:
                # Redis操作失败，不刷新令牌
                pass
        
        # 如果不需要刷新，直接返回当前令牌到响应头
        if not should_refresh:
            try:
                # 返回当前已验证的令牌（不生成新令牌）
                response.headers["X-CSRF-Token"] = stored_token
            except (ConnectionError, OSError, RuntimeError) as e:
                error_type_name = type(e).__name__
                error_module = type(e).__module__
                if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
                    "anyio" in error_module):
                    logger.debug(f"响应流已关闭，无法添加CSRF令牌: {request.method} {request.url.path}, IP: {client_ip}")
                    raise
                raise
            return response
        
        # 只有在需要刷新时才生成新令牌
        new_csrf_token = generate_csrf_token()
        
        # 存储新令牌（优先使用Redis）
        if redis_client:
            try:
                await redis_client.setex(
                    csrf_key,
                    settings.CSRF_TOKEN_EXPIRE_SECONDS,
                    new_csrf_token
                )
                # 同时更新内存存储（作为备份）
                _csrf_tokens[session_id] = new_csrf_token
            except Exception as e:
                error_msg = str(e) or repr(e) or "未知错误"
                logger.warning(f"Redis CSRF令牌更新失败: {error_msg}，使用内存存储")
                _csrf_tokens[session_id] = new_csrf_token
        else:
            _csrf_tokens[session_id] = new_csrf_token
        
        # 尝试添加CSRF令牌到响应头，如果连接已关闭则忽略
        try:
            response.headers["X-CSRF-Token"] = new_csrf_token
        except (ConnectionError, OSError, RuntimeError) as e:
            # 如果连接已关闭，无法修改响应头，直接重新抛出流异常
            error_type_name = type(e).__name__
            error_module = type(e).__module__
            if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
                "anyio" in error_module):
                logger.debug(f"响应流已关闭，无法添加CSRF令牌: {request.method} {request.url.path}, IP: {client_ip}")
                raise
            # 其他连接错误也重新抛出
            raise
        
        return response

