"""
斗篷与 Facebook 像素配置映射服务。

运行时根据投放链接中的 dp 参数（斗篷名）解析应使用的 Facebook Pixel 与 CAPI Token，
供 /report 与 postback 处理器发送 Conversions API 事件。

配置优先级（高 → 低）：
1. 短链接自身配置的 facebook_pixel_id / facebook_access_token
2. cloak_configs 表中已启用且磁盘存在 {dp}.html 的斗篷配置
3. settings 全局 FACEBOOK_PIXEL_ID / FACEBOOK_ACCESS_TOKEN

缓存：内存缓存键为 {short_code}:{dp}，TTL 1 小时；配置或桥页变更时调用 invalidate_cloak_cache_for_dp。
"""
import logging
import re
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ShortLink, CloakConfig
from app.core.config import settings
from app.core.cloak_scripts_paths import bridge_html_exists

logger = logging.getLogger(__name__)


def _cloak_phase_report_dict(cloak_config: Optional[CloakConfig]) -> Dict[str, Any]:
    """从 cloak_configs 行提取加载/点击/postback 三阶段上报开关与事件（供 /report 与 CAPI 使用）。"""
    if not cloak_config:
        return {
            "cloak_click_report_enabled": True,
            "cloak_load_report_enabled": False,
            "cloak_load_report_event": "PageView",
            "cloak_load_report_value": None,
            "cloak_load_report_currency": "USD",
            "cloak_postback_report_enabled": False,
            "cloak_postback_report_event": "Purchase",
            "cloak_postback_report_value": None,
            "cloak_postback_report_currency": "USD",
        }
    return {
        "cloak_click_report_enabled": bool(getattr(cloak_config, "click_report_enabled", True)),
        "cloak_load_report_enabled": bool(getattr(cloak_config, "load_report_enabled", False)),
        "cloak_load_report_event": (getattr(cloak_config, "load_report_event", None) or "PageView").strip()
        or "PageView",
        "cloak_load_report_value": getattr(cloak_config, "load_report_value", None),
        "cloak_load_report_currency": (getattr(cloak_config, "load_report_currency", None) or "USD").strip()
        or "USD",
        "cloak_postback_report_enabled": bool(getattr(cloak_config, "postback_report_enabled", False)),
        "cloak_postback_report_event": (getattr(cloak_config, "postback_report_event", None) or "Purchase").strip()
        or "Purchase",
        "cloak_postback_report_value": getattr(cloak_config, "postback_report_value", None),
        "cloak_postback_report_currency": (getattr(cloak_config, "postback_report_currency", None) or "USD").strip()
        or "USD",
    }


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
        """初始化内存缓存与时间戳表，TTL 默认 1 小时。"""
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
        
        配置字典结构（来自斗篷表时含上报事件字段）：
        {
            "facebook_pixel_id": str,
            "facebook_access_token": str,
            "facebook_api_version": str,
            "cloak_report_event": Optional[str],
            "cloak_report_value": Optional[float],
            "cloak_report_currency": Optional[str],
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
            
            # 查询斗篷配置表（系统服务维护）
            cloak_config = await self._get_enabled_cloak_config(db, dp)

            # 构建像素配置（使用 dp 参数匹配）
            pixel_config = self._build_pixel_config(short_link, dp, cloak_config)
            
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
    
    async def _get_enabled_cloak_config(self, db: AsyncSession, dp: str) -> Optional[CloakConfig]:
        """查询已启用的斗篷配置；无对应 {dp}.html 桥页文件则视为不可用，不参与像素映射。"""
        if not bridge_html_exists(dp):
            logger.info(f"[斗篷像素映射] 未检测到桥页 HTML，斗篷不可用：dp={dp}")
            return None
        result = await db.execute(
            select(CloakConfig).where(
                CloakConfig.cloak_name == dp,
                CloakConfig.is_enabled.is_(True),
            )
        )
        return result.scalars().first()

    def _build_pixel_config(
        self,
        short_link: ShortLink,
        dp: str,
        cloak_config: Optional[CloakConfig] = None
    ) -> Dict[str, Any]:
        """
        从 ShortLink 对象构建像素配置
        
        优先级：
        1. 短链接自定义配置（数据库字段）
        2. 系统服务中的斗篷配置（cloak_configs）
        3. 全局配置（config.py）
        
        参数：
        - short_link: ShortLink 对象
        - dp: HTML 名称（如 master, test 等），用于匹配 cloak_configs.cloak_name
        """
        # 优先级 1: 短链接自定义配置
        if short_link.facebook_pixel_id and short_link.facebook_access_token:
            logger.info(f"[斗篷像素映射] 使用短链接自定义配置：dp={dp}")
            pixel_config = {
                "facebook_pixel_id": short_link.facebook_pixel_id,
                "facebook_access_token": short_link.facebook_access_token,
                "facebook_api_version": short_link.facebook_api_version or settings.FACEBOOK_API_VERSION,
                "dp_name": dp,
                "short_code": short_link.short_code,
                "original_url": short_link.original_url,
                "is_active": short_link.is_active,
                "title": short_link.title,
                "offer_id": short_link.offer_id,
                "channel_id": short_link.channel_id,
            }
            if cloak_config:
                pixel_config["cloak_report_event"] = getattr(cloak_config, "report_event", None) or "ViewContent"
                pixel_config["cloak_report_value"] = getattr(cloak_config, "report_value", None)
                pixel_config["cloak_report_currency"] = getattr(cloak_config, "report_currency", None) or "USD"
            pixel_config.update(_cloak_phase_report_dict(cloak_config))
            return pixel_config
        
        # 优先级 2: 系统服务中的斗篷配置
        if cloak_config and cloak_config.pixel_id and cloak_config.access_token:
            logger.info(f"[斗篷像素映射] 使用数据库斗篷配置：dp={dp}")
            pixel_config = {
                "facebook_pixel_id": cloak_config.pixel_id,
                "facebook_access_token": cloak_config.access_token,
                "facebook_api_version": settings.FACEBOOK_API_VERSION,
                "backup_facebook_pixel_id": cloak_config.backup_pixel_id,
                "backup_facebook_access_token": cloak_config.backup_access_token,
                "cloak_report_event": getattr(cloak_config, "report_event", None) or "ViewContent",
                "cloak_report_value": getattr(cloak_config, "report_value", None),
                "cloak_report_currency": getattr(cloak_config, "report_currency", None) or "USD",
                "dp_name": dp,
                "short_code": short_link.short_code,
                "original_url": short_link.original_url,
                "is_active": short_link.is_active,
                "title": short_link.title,
                "offer_id": short_link.offer_id,
                "channel_id": short_link.channel_id,
            }
            pixel_config.update(_cloak_phase_report_dict(cloak_config))
            return pixel_config

        # 优先级 3: 全局配置
        logger.info(f"[斗篷像素映射] 使用全局配置：dp={dp}")
        pixel_config = {
            "facebook_pixel_id": settings.FACEBOOK_PIXEL_ID,
            "facebook_access_token": settings.FACEBOOK_ACCESS_TOKEN,
            "facebook_api_version": settings.FACEBOOK_API_VERSION,
            "dp_name": dp,
            "short_code": short_link.short_code,
            "original_url": short_link.original_url,
            "is_active": short_link.is_active,
            "title": short_link.title,
            "offer_id": short_link.offer_id,
            "channel_id": short_link.channel_id,
        }
        pixel_config.update(_cloak_phase_report_dict(cloak_config))
        return pixel_config
    
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

    def invalidate_cache_for_dp(self, dp: str) -> None:
        """清除所有 short_code:dp 形式的条目（桥页上传/删除或斗篷更名后应调用）。"""
        if not dp or not re.match(r"^[a-zA-Z0-9_-]+$", dp):
            return
        suffix = f":{dp}"
        keys = [k for k in list(self._cache.keys()) if k.endswith(suffix)]
        for cache_key in keys:
            self.invalidate_cache(cache_key)
        if keys:
            logger.info(f"[斗篷像素映射] 已按 dp 清除缓存：dp={dp}, keys={len(keys)}")
    
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


def invalidate_cloak_cache_for_dp(dp: str) -> None:
    """按斗篷名称（dp）失效像素配置缓存。"""
    cloak_pixel_service.invalidate_cache_for_dp(dp)


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
