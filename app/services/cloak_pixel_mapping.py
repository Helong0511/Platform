"""
斗篷与 Facebook 像素配置映射服务

提供斗篷名称与 Facebook 像素配置的一对一映射关系
支持高效查询、参数验证和详细的日志记录
"""
import logging
import re
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ShortLink
from app.core.config import settings

logger = logging.getLogger(__name__)


class CloakPixelMappingService:
    """
    斗篷像素配置映射服务
    
    功能：
    1. 建立斗篷名称与 Facebook 像素配置的一一对应关系
    2. 根据斗篷名称高效查询像素配置
    3. 参数验证与错误处理
    4. 详细的日志记录
    5. 缓存机制提高查询效率
    """
    
    def __init__(self):
        # 内存缓存：{short_code: pixel_config}
        self._cache: Dict[str, Dict[str, Any]] = {}
        # 缓存过期时间（秒）
        self._cache_ttl = 3600  # 1 小时
        # 缓存时间戳：{short_code: timestamp}
        self._cache_timestamps: Dict[str, float] = {}
    
    async def get_pixel_config_by_dp_param(
        self, 
        db: AsyncSession,
        dp: str,
        short_code: str,
        use_cache: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        根据 dp 参数（HTML 名称）获取 Facebook 像素配置
        
        参数：
        - db: 数据库会话
        - dp: 斗篷 HTML 名称（如 master, test 等）
        - short_code: 短链接代码（用于数据库查询）
        - use_cache: 是否使用缓存（默认 True）
        
        返回：
        - 成功：包含像素配置的字典
        - 失败：None
        
        配置字典结构：
        {
            "facebook_pixel_id": str,
            "facebook_access_token": str,
            "facebook_api_version": str,
            "dp_name": str,
            "short_code": str,
            "original_url": str,
            "is_active": bool
        }
        """
        # 参数验证
        if not dp:
            logger.error("[斗篷像素映射] dp 参数不能为空")
            return None
        
        # 验证 dp 参数格式（只允许字母、数字、连字符和下划线）
        if not re.match(r'^[a-zA-Z0-9_-]+$', dp):
            logger.error(f"[斗篷像素映射] dp 参数格式无效：{dp}")
            return None
        
        # 检查缓存（使用 dp 作为缓存键）
        cache_key = f"{short_code}:{dp}"
        if use_cache:
            cached_config = self._get_from_cache(cache_key)
            if cached_config:
                logger.info(f"[斗篷像素映射] 缓存命中：dp={dp}, short_code={short_code}")
                return cached_config
        
        try:
            # 从数据库查询短链接信息
            logger.info(f"[斗篷像素映射] 查询数据库：dp={dp}, short_code={short_code}")
            result = await db.execute(
                select(ShortLink).where(ShortLink.short_code == short_code)
            )
            short_link = result.scalars().first()
            
            if not short_link:
                logger.warning(f"[斗篷像素映射] 斗篷不存在：short_code={short_code}")
                return None
            
            if not short_link.is_active:
                logger.warning(f"[斗篷像素映射] 斗篷已停用：short_code={short_code}")
                return None
            
            # 构建像素配置（使用 dp 参数匹配 FACEBOOK_PIXEL_CONFIG）
            pixel_config = self._build_pixel_config(short_link, dp)
            
            # 验证配置有效性
            if not self._validate_pixel_config(pixel_config, dp):
                return None
            
            # 更新缓存
            if use_cache:
                self._update_cache(cache_key, pixel_config)
            
            # 记录成功日志
            logger.info(
                f"[斗篷像素映射] 成功获取配置："
                f"dp={dp}, short_code={short_code}, "
                f"pixel_id={pixel_config['facebook_pixel_id'][:10] if pixel_config['facebook_pixel_id'] else '使用全局配置'}..."
            )
            
            return pixel_config
            
        except Exception as e:
            logger.error(
                f"[斗篷像素映射] 查询失败：dp={dp}, short_code={short_code}, error={str(e)}",
                exc_info=True
            )
            return None
    
    def _build_pixel_config(self, short_link: ShortLink, dp: str) -> Dict[str, Any]:
        """
        从 ShortLink 对象构建像素配置
        
        优先级：
        1. 短链接自定义配置（数据库字段）
        2. 配置字典中的 dp 配置（FACEBOOK_PIXEL_CONFIG[dp]）
        3. 全局配置（config.py）
        
        参数：
        - short_link: ShortLink 对象
        - dp: HTML 名称（如 master, test 等），用于匹配 FACEBOOK_PIXEL_CONFIG
        """
        # 优先级 1: 短链接自定义配置
        if short_link.facebook_pixel_id and short_link.facebook_access_token:
            logger.info(f"[斗篷像素映射] 使用短链接自定义配置：dp={dp}")
            return {
                "facebook_pixel_id": short_link.facebook_pixel_id,
                "facebook_access_token": short_link.facebook_access_token,
                "facebook_api_version": short_link.facebook_api_version or settings.FACEBOOK_API_VERSION,
                "dp_name": dp,
                "short_code": short_link.short_code,
                "original_url": short_link.original_url,
                "is_active": short_link.is_active,
                "title": short_link.title,
                "offer_id": short_link.offer_id,
                "channel_id": short_link.channel_id
            }
        
        # 优先级 2: 配置字典中的 dp 配置
        cloak_config = settings.FACEBOOK_PIXEL_CONFIG.get(dp)
        if cloak_config:
            logger.info(f"[斗篷像素映射] 使用配置字典中的配置：dp={dp}")
            return {
                "facebook_pixel_id": cloak_config.get("pixel_id", settings.FACEBOOK_PIXEL_ID),
                "facebook_access_token": cloak_config.get("access_token", settings.FACEBOOK_ACCESS_TOKEN),
                "facebook_api_version": cloak_config.get("api_version", settings.FACEBOOK_API_VERSION),
                "dp_name": dp,
                "short_code": short_link.short_code,
                "original_url": short_link.original_url,
                "is_active": short_link.is_active,
                "title": short_link.title,
                "offer_id": short_link.offer_id,
                "channel_id": short_link.channel_id
            }
        
        # 优先级 3: 全局配置
        logger.info(f"[斗篷像素映射] 使用全局配置：dp={dp}")
        return {
            "facebook_pixel_id": settings.FACEBOOK_PIXEL_ID,
            "facebook_access_token": settings.FACEBOOK_ACCESS_TOKEN,
            "facebook_api_version": settings.FACEBOOK_API_VERSION,
            "dp_name": dp,
            "short_code": short_link.short_code,
            "original_url": short_link.original_url,
            "is_active": short_link.is_active,
            "title": short_link.title,
            "offer_id": short_link.offer_id,
            "channel_id": short_link.channel_id
        }
    
    def _validate_pixel_config(
        self, 
        pixel_config: Dict[str, Any], 
        cloak_name: str
    ) -> bool:
        """
        验证像素配置的有效性
        
        验证项：
        1. Pixel ID 格式（如果提供）
        2. Access Token 非空
        3. API 版本格式
        """
        # 检查必需的字段
        if not pixel_config.get("facebook_access_token"):
            logger.error(
                f"[斗篷像素映射] 配置验证失败：Access Token 不能为空 "
                f"(cloak_name={cloak_name})"
            )
            return False
        
        # 验证 Pixel ID 格式（如果提供）
        pixel_id = pixel_config.get("facebook_pixel_id")
        if pixel_id:
            if not re.match(r'^\d{15,17}$', pixel_id):
                logger.warning(
                    f"[斗篷像素映射] Pixel ID 格式可能不正确："
                    f"cloak_name={cloak_name}, pixel_id={pixel_id[:10]}..."
                )
                # 不返回 False，因为可能是自定义 ID 格式
        
        # 验证 API 版本格式
        api_version = pixel_config.get("facebook_api_version")
        if api_version:
            if not re.match(r'^v\d+\.\d+$', api_version):
                logger.error(
                    f"[斗篷像素映射] API 版本格式无效："
                    f"cloak_name={cloak_name}, api_version={api_version}"
                )
                return False
        
        return True
    
    def _get_from_cache(self, cloak_name: str) -> Optional[Dict[str, Any]]:
        """
        从缓存获取像素配置
        """
        if cloak_name not in self._cache:
            return None
        
        # 检查缓存是否过期
        timestamp = self._cache_timestamps.get(cloak_name, 0)
        current_time = datetime.now().timestamp()
        
        if current_time - timestamp > self._cache_ttl:
            logger.info(f"[斗篷像素映射] 缓存过期：{cloak_name}")
            # 清除过期缓存
            del self._cache[cloak_name]
            if cloak_name in self._cache_timestamps:
                del self._cache_timestamps[cloak_name]
            return None
        
        return self._cache[cloak_name]
    
    def _update_cache(
        self, 
        cloak_name: str, 
        pixel_config: Dict[str, Any]
    ) -> None:
        """
        更新缓存
        """
        self._cache[cloak_name] = pixel_config
        self._cache_timestamps[cloak_name] = datetime.now().timestamp()
        logger.debug(f"[斗篷像素映射] 缓存更新：{cloak_name}")
    
    def invalidate_cache(self, cache_key: Optional[str] = None) -> None:
        """
        使缓存失效
        
        参数：
        - cache_key: 指定缓存键（格式：short_code:dp）
        - 如果不提供，清除所有缓存
        """
        if cache_key:
            if cache_key in self._cache:
                del self._cache[cache_key]
                if cache_key in self._cache_timestamps:
                    del self._cache_timestamps[cache_key]
                logger.info(f"[斗篷像素映射] 缓存已清除：{cache_key}")
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
            logger.info("[斗篷像素映射] 所有缓存已清除")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        """
        return {
            "cache_size": len(self._cache),
            "cache_items": list(self._cache.keys()),
            "cache_ttl": self._cache_ttl
        }


# 全局服务实例
cloak_pixel_service = CloakPixelMappingService()


async def get_cloak_pixel_config(
    db: AsyncSession,
    dp: str,
    short_code: str,
    use_cache: bool = True
) -> Optional[Dict[str, Any]]:
    """
    便捷函数：根据 dp 参数（HTML 名称）获取像素配置
    
    使用示例：
    # 当访问 /change/temp_42e8c1b0?dp=master 时
    config = await get_cloak_pixel_config(db, dp="master", short_code="temp_42e8c1b0")
    if config:
        pixel_id = config["facebook_pixel_id"]
        access_token = config["facebook_access_token"]
        api_version = config["facebook_api_version"]
    """
    return await cloak_pixel_service.get_pixel_config_by_dp_param(
        db, dp, short_code, use_cache
    )


def invalidate_cloak_cache(short_code: Optional[str] = None, dp: Optional[str] = None) -> None:
    """
    便捷函数：使缓存失效
    
    使用示例：
    # 清除特定 dp 的缓存
    invalidate_cloak_cache(short_code="temp_42e8c1b0", dp="master")
    
    # 清除所有缓存
    invalidate_cloak_cache()
    """
    cloak_pixel_service.invalidate_cache(
        cache_key=f"{short_code}:{dp}" if short_code and dp else None
    )
