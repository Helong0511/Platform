"""
CSRF防护模块
提供CSRF令牌生成、验证和中间件
"""
import secrets
import logging
import hashlib
import time
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from starlette.responses import Response
from jose import jwt
from jose.exceptions import JWTError
from anyio import EndOfStream
from app.core.config import settings
from app.core.redis_client import get_redis_client
from app.core.utils import get_client_ip
from app.core.csrf_utils import safe_raise_csrf_exception
from app.core.audit_log import log_user_action
from app.db.database import get_db

logger = logging.getLogger(__name__)

# CSRF令牌存储（内存存储，Redis不可用时使用）
_csrf_tokens: Dict[str, str] = {}
# Redis客户端缓存
_redis_client_cache: Optional[Any] = None
# Redis客户端缓存过期时间（秒）
_REDIS_CLIENT_CACHE_TTL = 300
# 内存令牌存储最大大小
_MEMORY_TOKEN_STORE_MAX_SIZE = 10000
# 内存令牌清理阈值（当达到最大大小的80%时触发清理）
_MEMORY_TOKEN_CLEANUP_THRESHOLD = int(_MEMORY_TOKEN_STORE_MAX_SIZE * 0.8)
# 令牌刷新的最小间隔（秒），防止频繁刷新
_MIN_TOKEN_REFRESH_INTERVAL = 300  # 5分钟
def validate_referer(request: Request) -> bool:
    """
    验证请求的Referer头，防止跨域CSRF攻击
    
    参数:
        request: FastAPI请求对象
    
    返回:
        如果Referer有效返回True，否则返回False
    """
    referer = request.headers.get("Referer")
    if not referer:
        # 没有Referer头，记录警告但不直接拒绝（兼容性考虑）
        logger.debug("CSRF检查：缺少Referer头")
        return True
    
    try:
        from urllib.parse import urlparse
        parsed_referer = urlparse(referer)
        referer_domain = parsed_referer.netloc.lower()
        
        # 获取允许的域名列表
        allowed_origins = getattr(settings, 'BACKEND_CORS_ORIGINS', [])
        if not allowed_origins:
            # 如果没有配置CORS域名，默认允许当前域名
            host = request.headers.get("Host", "").split(":")[0].lower()
            allowed_domains = [host] if host else []
        else:
            allowed_domains = [str(origin).lower().replace("https://", "").replace("http://", "") for origin in allowed_origins]
        
        # 检查Referer域名是否在允许列表中
        for allowed_domain in allowed_domains:
            if referer_domain == allowed_domain or referer_domain.endswith("." + allowed_domain):
                return True
        
        logger.warning(f"CSRF检查：Referer域名 {referer_domain} 不在允许列表中")
        return False
        
    except Exception as e:
        logger.warning(f"CSRF检查：Referer验证失败: {e}")
        return False


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
        
        try:
            # 不验证签名，只解码payload（用于获取用户ID）
            # 注意：某些版本的python-jose需要密钥参数，即使verify_signature=False
            # 使用None作为密钥，避免空字符串可能导致的问题
            payload = jwt.decode(
                token,
                None,  # 使用None作为密钥
                options={"verify_signature": False, "verify_exp": False}
            )
            user_id = payload.get("sub")
            if user_id:
                user_id_str = str(user_id)
                logger.debug(f"成功提取用户ID: {user_id_str}")
                return user_id_str
        except JWTError as e:
            # token格式错误，无法提取用户ID
            logger.debug(f"JWT解码失败: {e}")
            pass
    except Exception as e:
        # 提取失败不影响CSRF功能，静默处理
        logger.debug(f"提取用户ID失败: {e}")
    
    logger.debug("无法提取用户ID，返回None")
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
    支持双重提交Cookie模式和传统头模式：
    1. 请求头：X-CSRF-Token
    2. Cookie：csrf_token（双重提交模式）
    3. 表单数据：csrf_token（POST/PUT/PATCH/DELETE）
    4. 查询参数：csrf_token（仅用于GET请求）
    """
    # 1. 从请求头获取（传统模式）
    token = request.headers.get("X-CSRF-Token")
    if token:
        return token
    
    # 2. 从Cookie获取（双重提交模式）
    token = request.cookies.get("csrf_token")
    if token:
        return token
    
    # 3. 从表单数据获取（POST/PUT/PATCH/DELETE）
    # 注意：FastAPI的request.form()是异步的，需要在中间件中特殊处理
    # 这里主要从请求头和Cookie获取，表单数据在端点中处理
    
    # 4. 从查询参数获取（仅用于GET请求）
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
    4. BFT S2S PostBack接口（外部回调接口，使用参数验证，不需要CSRF）
    5. 静态资源
    """
    path = request.url.path
    method = request.method
    
    # 安全方法不需要CSRF保护
    if is_safe_method(method):
        return True
    
    # 登录接口使用JWT，不需要CSRF
    # 精确匹配 /api/v1/auth/login、/api/v1/auth/logout 和 /api/v1/auth/refresh
    if path == "/api/v1/auth/login" or path == "/api/v1/auth/logout" or path == "/api/v1/auth/refresh":
        logger.debug(f"跳过CSRF检查（登录接口）: {method} {path}")
        return True
    
    # 客户API接口使用签名验证，不需要CSRF
    # 精确匹配客户API接口
    if path == "/api/v1/client_products" or path == "/api/v1/client_data":
        return True
    
    # BFT S2S PostBack接口（外部回调接口，使用参数验证，不需要CSRF）
    if path == "/api/v1/bft/postback" or path.startswith("/api/v1/postback/"):
        logger.debug(f"跳过CSRF检查（BFT PostBack接口）: {method} {path}")
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
    
    async def _get_redis_client(self) -> Optional[Any]:
        """
        获取Redis客户端（带缓存）
        缓存Redis客户端连接，减少连接开销
        实现更可靠的连接管理和错误处理
        """
        global _redis_client_cache
        
        # 检查缓存是否有效
        if _redis_client_cache:
            try:
                # 测试Redis连接是否仍然有效
                await _redis_client_cache.ping()
                return _redis_client_cache
            except Exception as e:
                logger.warning(f"Redis连接已失效: {str(e)}，将重新获取连接")
                _redis_client_cache = None
        
        # 缓存无效，获取新的Redis客户端
        try:
            redis_client = await get_redis_client()
            if redis_client:
                try:
                    # 验证新连接是否有效
                    await redis_client.ping()
                    _redis_client_cache = redis_client
                    logger.debug("成功获取并验证Redis客户端连接")
                except Exception as e:
                    logger.warning(f"Redis连接验证失败: {str(e)}，将使用内存存储")
                    redis_client = None
            else:
                logger.debug("无法获取Redis客户端，将使用内存存储")
            return redis_client
        except Exception as e:
            logger.warning(f"获取Redis客户端失败: {str(e)}，将使用内存存储")
            return None
    
    async def _generate_session_id(self, request: Request) -> str:
        """
        生成会话标识
        使用 IP:hash(User-Agent) 或 user_id:IP:hash(User-Agent)
        """
        client_ip = get_client_ip(request)
        user_id = extract_user_id_from_token(request)
        user_agent = request.headers.get("User-Agent", "")[:100]  # 限制长度
        user_agent_hash = hashlib.sha256(user_agent.encode('utf-8')).hexdigest()[:16]  # 使用SHA256前16位
        
        # 确保user_id为字符串类型
        if user_id:
            session_id = f"{user_id}:{client_ip}:{user_agent_hash}"
        else:
            session_id = f"{client_ip}:{user_agent_hash}"
        
        # 记录会话ID生成信息
        logger.debug(f"生成会话ID: {session_id}, IP: {client_ip}, User-Agent: {user_agent[:50]}...")
        return session_id
    
    async def _retrieve_csrf_token(self, session_id: str, request: Request) -> Optional[str]:
        """
        从存储中检索CSRF令牌
        优先从Redis获取，然后从内存存储获取
        """
        redis_client = await self._get_redis_client()
        csrf_key = f"csrf_token:{session_id}"
        
        # 尝试从Redis获取
        if redis_client:
            try:
                stored_token = await redis_client.get(csrf_key)
                if stored_token:
                    stored_token = stored_token.decode('utf-8') if isinstance(stored_token, bytes) else stored_token
                    # 更新内存存储（作为备份）
                    _csrf_tokens[session_id] = stored_token
                    return stored_token
            except Exception as e:
                logger.warning(f"Redis CSRF令牌获取失败: {str(e)}，将检查内存存储")
        
        # 尝试从内存存储获取
        return _csrf_tokens.get(session_id)
    
    async def _store_csrf_token(self, session_id: str, csrf_token: str, request: Request) -> None:
        """
        存储CSRF令牌
        优先使用Redis，Redis不可用时使用内存存储
        实现内存令牌存储的大小限制和自动清理
        """
        redis_client = await self._get_redis_client()
        csrf_key = f"csrf_token:{session_id}"
        
        if redis_client:
            try:
                await redis_client.setex(
                    csrf_key,
                    settings.CSRF_TOKEN_EXPIRE_SECONDS,
                    csrf_token
                )
                # 同时更新内存存储（作为备份）
                self._cleanup_memory_tokens_if_needed()
                _csrf_tokens[session_id] = csrf_token
            except Exception as e:
                logger.warning(f"Redis CSRF令牌存储失败: {str(e)}，使用内存存储")
                self._cleanup_memory_tokens_if_needed()
                _csrf_tokens[session_id] = csrf_token
        else:
            self._cleanup_memory_tokens_if_needed()
            _csrf_tokens[session_id] = csrf_token
    
    def _cleanup_memory_tokens_if_needed(self) -> None:
        """
        检查并清理内存令牌存储
        当存储大小达到清理阈值时，清理最旧的令牌
        """
        global _csrf_tokens
        
        if len(_csrf_tokens) >= _MEMORY_TOKEN_CLEANUP_THRESHOLD:
            # 计算需要清理的令牌数量（清理到总大小的50%）
            tokens_to_clean = len(_csrf_tokens) - int(_MEMORY_TOKEN_STORE_MAX_SIZE * 0.5)
            if tokens_to_clean > 0:
                # 获取所有令牌的键（这里假设字典的插入顺序是最近添加的在后面）
                # 在Python 3.7+中，字典保持插入顺序
                oldest_tokens = list(_csrf_tokens.keys())[:tokens_to_clean]
                for token_key in oldest_tokens:
                    _csrf_tokens.pop(token_key, None)
                logger.debug(f"清理了 {len(oldest_tokens)} 个旧的CSRF令牌，当前内存存储大小: {len(_csrf_tokens)}")
    
    async def _add_csrf_token_to_response(self, response: Response, csrf_token: str, request: Request) -> None:
        """
        向响应添加CSRF令牌
        使用双重提交Cookie模式：同时设置HttpOnly Cookie和响应头
        
        参数:
            response: 响应对象
            csrf_token: CSRF令牌
            request: 请求对象
        """
        try:
            # 设置HttpOnly Cookie（双重提交模式）
            response.set_cookie(
                key="csrf_token",
                value=csrf_token,
                httponly=True,  # 防止JavaScript访问
                secure=getattr(settings, 'is_production', False),  # 生产环境启用HTTPS
                samesite="strict",  # 严格SameSite，防止CSRF
                max_age=settings.CSRF_TOKEN_EXPIRE_SECONDS,
                path="/"  # 全局路径
            )
            
            # 设置响应头（向后兼容）
            response.headers["X-CSRF-Token"] = csrf_token
            logger.debug(f"已添加CSRF令牌到Cookie和响应头: {request.method} {request.url.path}")
        except (ConnectionError, OSError, RuntimeError) as e:
            # 如果连接已关闭，无法修改响应头，记录日志但不抛出异常
            error_type_name = type(e).__name__
            error_module = type(e).__module__
            if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
                "anyio" in error_module):
                logger.debug(f"响应流已关闭，无法添加CSRF令牌: {request.method} {request.url.path}")
            else:
                logger.warning(f"无法添加CSRF令牌到响应头: {request.method} {request.url.path}，错误: {e}")
    
    async def _handle_csrf_validation_error(self, request: Request, message: str, token_to_return: Optional[str] = None) -> None:
        """
        处理CSRF验证错误
        检查连接状态，使用安全的异常抛出机制
        支持双重提交Cookie模式
        """
        # 检查连接状态
        if not await self._check_connection_status(request):
            raise EndOfStream("客户端已断开连接")
        
        # 创建HTTPException
        http_exc = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message
        )
        
        # 确保headers属性存在且是字典
        if not hasattr(http_exc, "headers"):
            http_exc.headers = {}
        
        # 如果提供了令牌，将其添加到异常的headers中
        # 这样FastAPI会将这些headers添加到响应中
        if token_to_return:
            http_exc.headers["X-CSRF-Token"] = token_to_return
            
            # 同时设置Cookie（双重提交模式）
            # 注意：HTTPException的headers会被FastAPI自动添加到响应中
            # 但Cookie需要特殊处理，这里通过headers传递信息给异常处理器
            http_exc.headers["Set-Cookie"] = f"csrf_token={token_to_return}; HttpOnly; SameSite=Strict; Max-Age={settings.CSRF_TOKEN_EXPIRE_SECONDS}; Path=/"
            
            logger.debug(f"在CSRF错误响应中添加新令牌: {token_to_return[:10]}...")
        
        raise http_exc
    
    async def _check_connection_status(self, request: Request) -> bool:
        """
        检查连接状态
        返回True表示连接正常，False表示连接已断开
        """
        try:
            if hasattr(request, '_is_disconnected') and request._is_disconnected:
                logger.debug("客户端已断开连接")
                return False
            if hasattr(request, 'scope') and isinstance(request.scope, dict):
                if request.scope.get('_disconnected', False):
                    logger.debug("从scope检测到连接已断开")
                    return False
            return True
        except Exception:
            # 检查失败时默认认为连接正常
            return True
    
    async def _get_or_create_csrf_token(self, session_id: str, request: Request) -> str:
        """
        获取或创建CSRF令牌
        优先使用Redis中已存在的令牌，不存在则生成新的
        """
        # 尝试获取现有令牌
        csrf_token = await self._retrieve_csrf_token(session_id, request)
        
        # 如果没有现有令牌，生成新的
        if not csrf_token:
            csrf_token = generate_csrf_token()
            # 存储新令牌
            await self._store_csrf_token(session_id, csrf_token, request)
            
            # 记录详细信息
            client_ip = get_client_ip(request)
            user_id = extract_user_id_from_token(request)
            user_agent = request.headers.get("User-Agent", "")[:100]
            user_agent_hash = hashlib.sha256(user_agent.encode('utf-8')).hexdigest()[:16]
            csrf_key = f"csrf_token:{session_id}"
            
            logger.info(
                f"生成新的CSRF令牌: {request.method} {request.url.path}\n"
                f"  IP: {client_ip}\n"
                f"  User-Agent: {user_agent}\n"
                f"  User-Agent Hash: {user_agent_hash}\n"
                f"  Session ID: {session_id}\n"
                f"  User ID: {user_id}\n"
                f"  CSRF Key: {csrf_key}\n"
                f"  令牌: {csrf_token[:10]}..."
            )
        
        return csrf_token
    
    async def _handle_get_request(self, request: Request, call_next, session_id: str) -> Response:
        """
        处理GET请求
        生成并返回CSRF令牌
        """
        # 获取或创建CSRF令牌
        csrf_token = await self._get_or_create_csrf_token(session_id, request)
        
        # 处理请求
        try:
            response = await call_next(request)
            # 在响应头中添加CSRF令牌
            await self._add_csrf_token_to_response(response, csrf_token, request)
            return response
        except (ConnectionError, OSError, RuntimeError) as e:
            # 处理连接中断或流关闭的情况
            error_type_name = type(e).__name__
            error_module = type(e).__module__
            if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
                "anyio" in error_module):
                logger.debug(f"请求流已关闭: {request.method} {request.url.path}")
                raise
            raise
    
    async def _handle_non_get_request(self, request: Request, call_next, session_id: str) -> Response:
        """
        处理非GET请求
        验证CSRF令牌和Referer
        """
        # 检查连接状态
        if not await self._check_connection_status(request):
            raise EndOfStream("客户端已断开连接")
        
        # 验证Referer（额外的安全层）
        if not validate_referer(request):
            logger.warning(f"CSRF检查失败：Referer验证失败: {request.method} {request.url.path}")
            await self._handle_csrf_validation_error(request, "请求来源验证失败")
        
        # 获取请求中的CSRF令牌
        csrf_token = get_csrf_token_from_request(request)
        
        if not csrf_token:
            logger.warning(f"CSRF令牌缺失: {request.method} {request.url.path}, session_id: {session_id}")
            # 记录审计日志
            try:
                from app.db.database import get_db
                async for db in get_db():
                    await log_user_action(
                        db=db,
                        action_type="CSRF_VIOLATION",
                        user_id=extract_user_id_from_token(request),
                        request=request,
                        ip_address=get_client_ip(request),
                        success=False,
                        error_message="CSRF令牌缺失",
                        details={
                            "violation_type": "missing_token",
                            "session_id": session_id,
                            "path": request.url.path,
                            "method": request.method
                        }
                    )
                    break
            except Exception as e:
                logger.error(f"记录CSRF审计日志失败: {e}")
            await self._handle_csrf_validation_error(request, "CSRF令牌缺失，请刷新页面后重试")
        
        # 获取存储的CSRF令牌
        stored_token = await self._retrieve_csrf_token(session_id, request)
        
        if not stored_token:
            # 令牌不存在，生成新令牌并返回错误
            logger.warning(f"CSRF令牌不存在: {request.method} {request.url.path}, session_id: {session_id}")
            new_csrf_token = generate_csrf_token()
            await self._store_csrf_token(session_id, new_csrf_token, request)
            logger.info(f"CSRF令牌不存在，生成新令牌: {new_csrf_token[:10]}...")
            # 记录审计日志
            try:
                async for db in get_db():
                    await log_user_action(
                        db=db,
                        action_type="CSRF_VIOLATION",
                        user_id=extract_user_id_from_token(request),
                        request=request,
                        ip_address=get_client_ip(request),
                        success=False,
                        error_message="CSRF令牌不存在",
                        details={
                            "violation_type": "token_not_found",
                            "session_id": session_id,
                            "path": request.url.path,
                            "method": request.method
                        }
                    )
                    break
            except Exception as e:
                logger.error(f"记录CSRF审计日志失败: {e}")
            await self._handle_csrf_validation_error(request, "CSRF令牌无效或已过期，请刷新页面后重试", new_csrf_token)
        
        # 使用安全的字符串比较（防止时序攻击）
        if not secrets.compare_digest(csrf_token, stored_token):
            # 记录详细的调试信息
            client_ip = get_client_ip(request)
            user_id = extract_user_id_from_token(request)
            user_agent = request.headers.get("User-Agent", "")[:100]
            user_agent_hash = hashlib.sha256(user_agent.encode('utf-8')).hexdigest()[:16]
            csrf_key = f"csrf_token:{session_id}"
            
            logger.warning(
                f"CSRF令牌不匹配: {request.method} {request.url.path}\n"
                f"  IP: {client_ip}\n"
                f"  User-Agent: {user_agent}\n"
                f"  User-Agent Hash: {user_agent_hash}\n"
                f"  Session ID: {session_id}\n"
                f"  User ID: {user_id}\n"
                f"  CSRF Key: {csrf_key}\n"
                f"  期望的令牌: {stored_token[:10]}...\n"
                f"  实际的令牌: {csrf_token[:10]}..."
            )
            
            # 记录审计日志
            try:
                async for db in get_db():
                    await log_user_action(
                        db=db,
                        action_type="CSRF_VIOLATION",
                        user_id=user_id,
                        request=request,
                        ip_address=client_ip,
                        success=False,
                        error_message="CSRF令牌不匹配",
                        details={
                            "violation_type": "token_mismatch",
                            "session_id": session_id,
                            "path": request.url.path,
                            "method": request.method,
                            "user_agent": user_agent,
                            "expected_token_prefix": stored_token[:10],
                            "received_token_prefix": csrf_token[:10]
                        }
                    )
                    break
            except Exception as e:
                logger.error(f"记录CSRF审计日志失败: {e}")
            
            # 检查是否是服务器重启后的情况
            memory_token = _csrf_tokens.get(session_id)
            is_server_restart = (memory_token is None) and (stored_token is not None)
            
            if is_server_restart:
                # 服务器重启，生成新令牌
                new_csrf_token = generate_csrf_token()
                await self._store_csrf_token(session_id, new_csrf_token, request)
                logger.info(f"服务器重启导致CSRF令牌不匹配，生成新令牌: {new_csrf_token[:10]}...")
                await self._handle_csrf_validation_error(request, "CSRF令牌验证失败（可能是服务器重启导致），请刷新页面后重试", new_csrf_token)
            else:
                # 令牌不同步，返回存储的正确令牌
                logger.info(f"CSRF令牌不匹配，返回正确的存储令牌: {stored_token[:10]}...")
                await self._handle_csrf_validation_error(request, "CSRF令牌验证失败，请刷新页面后重试", stored_token)
        
        # 验证通过，处理请求
        response = await call_next(request)
        
        # 检查令牌是否即将过期，需要刷新
        should_refresh = False
        redis_client = await self._get_redis_client()
        csrf_key = f"csrf_token:{session_id}"
        last_refresh_key = f"csrf_token_last_refresh:{session_id}"
        
        if redis_client:
            try:
                # 获取令牌的剩余时间
                ttl = await redis_client.ttl(csrf_key)
                
                # 检查最后刷新时间，防止频繁刷新
                last_refresh = await redis_client.get(last_refresh_key)
                last_refresh_time = int(last_refresh) if last_refresh else 0
                current_time = int(time.time())
                time_since_last_refresh = current_time - last_refresh_time
                
                # 只有在以下情况下才刷新令牌：
                # 1. 令牌剩余时间小于阈值（10%）
                # 2. 距离上次刷新超过最小间隔（5分钟）
                if ttl > 0 and ttl < (settings.CSRF_TOKEN_EXPIRE_SECONDS * _TOKEN_REFRESH_THRESHOLD):
                    if time_since_last_refresh >= _MIN_TOKEN_REFRESH_INTERVAL:
                        should_refresh = True
                        logger.debug(f"CSRF令牌即将过期（剩余{ttl}秒），距离上次刷新{time_since_last_refresh}秒，刷新令牌: {request.method} {request.url.path}")
                    else:
                        logger.debug(f"CSRF令牌即将过期（剩余{ttl}秒），但距离上次刷新仅{time_since_last_refresh}秒，跳过刷新: {request.method} {request.url.path}")
            except Exception:
                pass
        
        if should_refresh:
            # 刷新令牌
            new_csrf_token = generate_csrf_token()
            await self._store_csrf_token(session_id, new_csrf_token, request)
            
            # 记录刷新时间
            if redis_client:
                try:
                    await redis_client.setex(
                        last_refresh_key,
                        settings.CSRF_TOKEN_EXPIRE_SECONDS,
                        str(int(time.time()))
                    )
                except Exception:
                    pass
            
            await self._add_csrf_token_to_response(response, new_csrf_token, request)
        else:
            # 返回当前令牌
            await self._add_csrf_token_to_response(response, stored_token, request)
        
        return response
    
    async def dispatch(self, request: Request, call_next):
        """
        处理请求
        1. 检查是否应该跳过CSRF检查
        2. 对于GET请求，生成并返回CSRF令牌
        3. 对于非GET请求，验证CSRF令牌
        """
        # 获取路径和方法
        path = request.url.path
        method = request.method.upper()
        
        # 快速检查：跳过CSRF检查的路径
        if path.startswith("/s/"):
            logger.info(f"跳过CSRF检查（短链接重定向）: {method} {path}")
            return await call_next(request)
        
        if path == "/api/v1/auth/login" or path == "/api/v1/auth/logout" or path == "/api/v1/auth/refresh":
            logger.info(f"跳过CSRF检查（登录接口）: {method} {path}")
            return await call_next(request)
        
        if path == "/api/v1/bft/postback" or path.startswith("/api/v1/postback/"):
            logger.debug(f"跳过CSRF检查（BFT PostBack接口）: {method} {path}")
            return await call_next(request)
        
        if path == "/api/v1/audit-logs/client-error":
            logger.debug(f"跳过CSRF检查（客户端错误记录接口）: {method} {path}")
            return await call_next(request)
        
        if path.startswith("/api/v1/scheduled-tasks/"):
            if path.endswith("/trigger") or path.endswith("/reload") or path == "/api/v1/scheduled-tasks/reload-all":
                logger.debug(f"跳过CSRF检查（定时任务接口）: {method} {path}")
                return await call_next(request)
        
        # 检查是否应该跳过CSRF检查
        if should_skip_csrf_check(request):
            # 对于GET请求，即使跳过检查，也要生成并返回CSRF令牌
            if request.method == "GET":
                session_id = await self._generate_session_id(request)
                return await self._handle_get_request(request, call_next, session_id)
            else:
                logger.debug(f"跳过CSRF检查: {method} {path}")
                return await call_next(request)
        
        logger.debug(f"执行CSRF检查: {method} {path}")
        
        # 生成会话标识
        session_id = await self._generate_session_id(request)
        
        try:
            # 根据请求方法处理
            if request.method == "GET":
                return await self._handle_get_request(request, call_next, session_id)
            else:
                return await self._handle_non_get_request(request, call_next, session_id)
        except Exception as e:
            # 处理流相关的异常
            error_type_name = type(e).__name__
            error_module = type(e).__module__
            if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
                "anyio" in error_module):
                logger.debug(f"请求流异常: {method} {path}")
                raise
            # 检查是否是HTTPException，如果是则直接抛出，不记录为错误
            from fastapi.exceptions import HTTPException
            if isinstance(e, HTTPException):
                raise
            # 其他异常，记录日志并重新抛出
            logger.error(f"CSRF验证过程中发生未预期的错误: {method} {path}，错误: {str(e)}", exc_info=True)
            raise