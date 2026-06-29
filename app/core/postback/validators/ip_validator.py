"""
IP 白名单验证器

验证 Postback 请求的 IP 地址是否在白名单中
"""
import logging
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.models.models import PostbackIpWhitelist

logger = logging.getLogger(__name__)


class IpValidator:
    """IP 白名单验证器"""
    
    @staticmethod
    async def validate(
        request_ip: Optional[str],
        db: AsyncSession
    ) -> Tuple[bool, Optional[str]]:
        """
        验证 IP 地址
        
        Args:
            request_ip: 请求 IP 地址
            db: 数据库会话
        
        Returns:
            tuple: (是否通过验证，清理后的 IP 地址)
        """
        # 生产环境 IP 不可解析时拒绝处理
        if not request_ip or not request_ip.strip() or request_ip.strip() == "unknown":
            logger.warning("Postback 请求 IP 为空或无法获取：request_ip=%r", request_ip)
            if settings.is_production:
                return False, None
            return True, None
        
        # 清理 IP 地址
        cleaned_ip = IpValidator._clean_ip(request_ip)
        
        # 查询白名单
        is_whitelisted = await IpValidator._check_whitelist(cleaned_ip, db)
        
        if not is_whitelisted:
            logger.warning(f"IP 地址不在白名单中：{cleaned_ip}")
            return False, cleaned_ip
        
        return True, cleaned_ip
    
    @staticmethod
    def _clean_ip(request_ip: str) -> str:
        """
        清理 IP 地址（去除空格、端口号等）
        
        Args:
            request_ip: 原始 IP 地址
        
        Returns:
            str: 清理后的 IP 地址
        """
        cleaned_ip = request_ip.strip()
        
        # 如果包含端口号，只取 IP 部分
        if ":" in cleaned_ip:
            # 检查是否是 IPv6 格式 [::1]:8080
            if cleaned_ip.startswith("[") and "]" in cleaned_ip:
                # IPv6 地址带端口号
                ipv6_end = cleaned_ip.index("]")
                cleaned_ip = cleaned_ip[1:ipv6_end]
            else:
                # IPv4 地址带端口号
                parts = cleaned_ip.split(":")
                if len(parts) == 2 and parts[1].isdigit():
                    cleaned_ip = parts[0]
        
        return cleaned_ip
    
    @staticmethod
    async def _check_whitelist(cleaned_ip: str, db: AsyncSession) -> bool:
        """
        检查 IP 是否在白名单中
        
        Args:
            cleaned_ip: 清理后的 IP 地址
            db: 数据库会话
        
        Returns:
            bool: 是否在白名单中
        """
        # 查询所有启用的白名单 IP
        result = await db.execute(
            select(PostbackIpWhitelist.ip_address, PostbackIpWhitelist.id)
            .where(PostbackIpWhitelist.is_active == True)
        )
        whitelist_items = result.all()

        if not whitelist_items:
            if settings.is_production:
                logger.warning("Postback IP 白名单为空，生产环境拒绝处理")
                return False
            return True
        # 在 Python 中比较（去除空格后比较）
        for whitelist_item in whitelist_items:
            whitelist_ip = whitelist_item.ip_address.strip() if whitelist_item.ip_address else ""
            
            # 直接比较
            if whitelist_ip == cleaned_ip:
                return True
            
            # 如果白名单 IP 也包含端口号，只比较 IP 部分
            if ":" in whitelist_ip and not whitelist_ip.startswith("["):
                whitelist_ip_parts = whitelist_ip.split(":")
                if len(whitelist_ip_parts) == 2 and whitelist_ip_parts[1].isdigit():
                    if whitelist_ip_parts[0] == cleaned_ip:
                        return True
        
        return False
