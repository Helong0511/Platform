"""
API端点模块统一导出
按业务模块组织，提供清晰的导入路径
"""
from fastapi import APIRouter

# 创建统一的路由聚合器
main_router = APIRouter()

# ==================== 认证模块 ====================
from . import auth

# ==================== 用户管理模块 ====================
from . import users

# ==================== 客户管理模块 ====================
from . import clients

# ==================== 产品管理模块 ====================
from . import products
# product_assignments 现在在 products 模块中
from .products import assignments_router as product_assignments

# ==================== 广告数据模块 ====================
from . import ad_data
from . import tb_search_data

# ==================== 仪表盘模块 ====================
from . import dashboard

# ==================== Excel处理模块 ====================
from . import excel

# ==================== ML模型模块 ====================
from . import ml_model

# ==================== 系统管理模块 ====================
from .system import (
    scheduled_tasks_router as scheduled_tasks,
    audit_logs_router as audit_logs,
    sessions_router as sessions,
    notification_configs_router as notification_configs,
)

# ==================== 外部接口模块 ====================
from .external import client_api_router as client_api, telegram_router as telegram

# ==================== Postback模块 ====================
from .postback import router as postback, bft_router as bft_postback

# ==================== 追踪模块 ====================
from .tracking import router as tracking, short_links_router as short_links

# ==================== CPL系统模块 ====================
from .cpl import (
    advertisers_router as advertisers,
    publishers_router as publishers,
    offers_router as offers,
    caps_router as caps,
    discounts_router as discounts,
    conversion_deductions_router as conversion_deductions,
    conversion_summary_router as conversion_summary,
    conversion_log_router as conversion_log,
    clicks_router as clicks,
    advertiser_tests_router as advertiser_tests,
    affiliate_tests_router as affiliate_tests,
)

# ==================== 其他 ====================
from . import notify_api

# 导出所有路由（用于统一注册）
__all__ = [
    # 认证
    'auth',
    # 用户管理
    'users',
    # 客户管理
    'clients',
    # 产品管理
    'products',
    'product_assignments',
    # 广告数据
    'ad_data',
    'tb_search_data',
    # 仪表盘
    'dashboard',
    # Excel处理
    'excel',
    # ML模型
    'ml_model',
    # 系统管理
    'scheduled_tasks',
    'audit_logs',
    'sessions',
    'notification_configs',
    # 外部接口
    'client_api',
    'telegram',
    # Postback
    'postback',
    'bft_postback',
    # 追踪
    'tracking',
    'short_links',
    # CPL系统
    'advertisers',
    'publishers',
    'offers',
    'caps',
    'discounts',
    'conversion_deductions',
    'conversion_summary',
    'conversion_log',
    'clicks',
    # 测试
    'advertiser_tests',
    'affiliate_tests',
    # 其他
    'notify_api',
]

