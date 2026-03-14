"""
Postback 处理模块

提供完整的 Postback 回调处理功能，包括：
- 数据验证（IP、格式、重复检测）
- 数据转换（标准化、Click 关联）
- 业务检查（Cap 限制、扣量计算）
- 数据保存
- 渠道转发
- 通知发送
"""

from app.core.postback.processor import PostbackProcessor
from app.core.postback.validators.ip_validator import IpValidator
from app.core.postback.validators.data_validator import DataValidator
from app.core.postback.validators.duplicate_checker import DuplicateChecker
from app.core.postback.transformers.normalizer import DataNormalizer
from app.core.postback.transformers.click_associator import ClickAssociator
from app.core.postback.checks.cap_checker import CapChecker
from app.core.postback.checks.discount_checker import DiscountChecker
from app.core.postback.savers.conversion_saver import ConversionSaver
from app.core.postback.forwarder import PostbackForwarder
from app.core.postback.notifier import PostbackNotifier

__all__ = [
    # 主处理器
    'PostbackProcessor',
    
    # 验证器
    'IpValidator',
    'DataValidator',
    'DuplicateChecker',
    
    # 转换器
    'DataNormalizer',
    'ClickAssociator',
    
    # 检查器
    'CapChecker',
    'DiscountChecker',
    
    # 保存器
    'ConversionSaver',
    
    # 转发和通知
    'PostbackForwarder',
    'PostbackNotifier',
]
