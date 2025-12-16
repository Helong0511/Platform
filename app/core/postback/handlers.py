"""
Postback 处理器基类和注册机制
各平台需要实现自己的处理器
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PostbackHandler(ABC):
    """Postback 处理器基类"""
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """返回平台名称"""
        pass
    
    @abstractmethod
    async def validate(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        验证 postback 数据
        
        Args:
            data: 原始请求数据
            
        Returns:
            (是否有效, 错误信息)
        """
        pass
    
    @abstractmethod
    async def normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化 postback 数据，转换为统一格式
        
        Args:
            data: 原始请求数据
            
        Returns:
            标准化后的数据字典，包含以下字段：
            - conversion_id: 转化ID（必填）
            - event_name: 事件名称（可选）
            - event_value: 事件价值（可选）
            - payout: 支付金额（可选）
            - devad_id: 设备广告ID（可选）
            - os: 操作系统（可选）
            - carrier: 运营商（可选）
            - ip: IP地址（可选）
            - gid: 渠道ID（可选）
            - product_id: 产品ID（可选）
            - client_id: 客户ID（可选）
        """
        pass
    
    async def validate_product_client(
        self, 
        product_id: Optional[int], 
        client_id: Optional[int],
        db: AsyncSession
    ) -> tuple[bool, Optional[str]]:
        """
        验证产品和客户是否存在且激活（可选实现）
        
        Args:
            product_id: 产品ID
            client_id: 客户ID
            db: 数据库会话
            
        Returns:
            (是否有效, 错误信息)
        """
        if product_id:
            from app.models.models import Product
            from sqlalchemy.future import select
            
            result = await db.execute(
                select(Product).where(Product.id == product_id, Product.is_active == True)
            )
            product = result.scalars().first()
            if not product:
                return False, f"产品不存在或未激活: product_id={product_id}"
        
        if client_id:
            from app.models.models import Client
            from sqlalchemy.future import select
            
            result = await db.execute(
                select(Client).where(Client.id == client_id, Client.is_active == True)
            )
            client = result.scalars().first()
            if not client:
                return False, f"客户不存在或未激活: client_id={client_id}"
        
        return True, None


# 处理器注册表
_handlers: Dict[str, PostbackHandler] = {}


def register_handler(handler: PostbackHandler) -> None:
    """
    注册 postback 处理器
    
    Args:
        handler: 处理器实例
    """
    platform = handler.platform_name
    if platform in _handlers:
        logger.warning(f"平台 {platform} 的处理器已存在，将被覆盖")
    _handlers[platform] = handler
    logger.info(f"已注册 postback 处理器: {platform}")


def get_handler(platform: str) -> Optional[PostbackHandler]:
    """
    获取指定平台的处理器
    
    Args:
        platform: 平台名称
        
    Returns:
        处理器实例，如果不存在则返回 None
    """
    return _handlers.get(platform)


def list_platforms() -> list[str]:
    """
    列出所有已注册的平台
    
    Returns:
        平台名称列表
    """
    return list(_handlers.keys())

