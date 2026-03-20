"""
API端点模块统一导出
按业务模块组织，提供清晰的导入路径
"""
from fastapi import APIRouter

# 创建统一的路由聚合器
api_router = APIRouter()
main_router = api_router  # 保持向后兼容

# ==================== 认证模块 ====================
from app.api_v1 import auth

# ==================== 用户管理模块 ====================
from app.api_v1 import users

# ==================== 客户管理模块 ====================
from app.api_v1 import clients

# ==================== 产品管理模块 ====================
from app.api_v1 import products
# product_assignments 现在在 products 模块中
from app.api_v1.products import assignments_router as product_assignments

# ==================== 广告数据模块 ====================
from app.api_v1 import ad_data
from app.api_v1 import tb_search_data

# ==================== 仪表盘模块 ====================
from app.api_v1 import dashboard

# ==================== Excel处理模块 ====================
from app.api_v1 import excel

# ==================== ML模型模块 ====================
from app.api_v1 import ml_model

# ==================== 系统管理模块 ====================
from app.api_v1.system import (
    scheduled_tasks_router as scheduled_tasks,
    audit_logs_router as audit_logs,
    sessions_router as sessions,
    notification_configs_router as notification_configs,
    third_party_reports_router as third_party_reports,
)
from app.api_v1.system.telegram_status import router as telegram_status

# ==================== 外部接口模块 ====================
from app.api_v1.external import client_api_router as client_api, telegram_router as telegram

# ==================== Postback模块 ====================
from app.api_v1.postback import router as postback, bft_router as bft_postback, ip_whitelist_router as ip_whitelist

# ==================== 追踪模块 ====================
from app.api_v1.tracking import router as tracking, short_links_router as short_links

# ==================== CPL系统模块 ====================
from app.api_v1.cpl import (
    advertisers_router as advertisers,
    publishers_router as publishers,
    offers_router as offers,
    caps_router as caps,
    discounts_router as discounts,
    conversion_deductions_router as conversion_deductions,
    conversion_summary_router as conversion_summary,
    conversion_log_router as conversion_log,
    clicks_router as clicks,
    affiliate_tests_router as affiliate_tests,
)

# ==================== 路由注册 ====================
# 按业务模块分组注册，便于管理和维护

# ---------- 认证模块 ----------
api_router.include_router(auth.router, prefix="/auth", tags=["认证管理"])

# ---------- 用户管理模块 ----------
api_router.include_router(users.router, prefix="/users", tags=["用户管理"])

# ---------- 客户管理模块 ----------
api_router.include_router(clients.router, prefix="/clients", tags=["客户管理"])

# ---------- 产品管理模块 ----------
api_router.include_router(products.router, prefix="/products", tags=["产品管理"])
api_router.include_router(product_assignments, prefix="/product-assignments", tags=["产品分配历史"])

# ---------- 广告数据模块 ----------
api_router.include_router(ad_data.router, prefix="/ad-data", tags=["广告数据"])
api_router.include_router(tb_search_data.router, prefix="/tb-search-data", tags=["TB搜索数据"])

# ---------- 仪表盘模块 ----------
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["仪表盘"])

# ---------- Excel处理模块 ----------
api_router.include_router(excel.router, prefix="/excel", tags=["Excel处理"])

# ---------- ML模型模块 ----------
api_router.include_router(ml_model.router, prefix="/ml-model", tags=["导入训练"])

# ---------- 系统管理模块 ----------
api_router.include_router(scheduled_tasks, prefix="/scheduled-tasks", tags=["定时任务管理"])
api_router.include_router(audit_logs, prefix="/audit-logs", tags=["操作日志"])
api_router.include_router(sessions, prefix="/sessions", tags=["会话管理"])
api_router.include_router(notification_configs, prefix="/notification-configs", tags=["通知配置管理"])
api_router.include_router(telegram_status, prefix="/telegram", tags=["Telegram状态管理"])
api_router.include_router(third_party_reports, prefix="/third-party-reports", tags=["第三方上报日志"])

# ---------- 外部接口模块 ----------
# 客户API路由（通过API密钥访问，无前缀）
api_router.include_router(client_api, prefix="", tags=["客户API"])
# Telegram Bot 管理路由
api_router.include_router(telegram, prefix="/telegram", tags=["Telegram Bot"])

# ---------- Postback模块 ----------
# BFT S2S PostBack 路由（外部回调接口，保留向后兼容，无前缀）
api_router.include_router(bft_postback, prefix="", tags=["BFT S2S"])
# 统一 Postback 服务路由（推荐使用，无前缀）
api_router.include_router(postback, prefix="", tags=["Postback服务"])
# Postback IP 白名单管理路由
api_router.include_router(ip_whitelist, prefix="", tags=["Postback IP白名单"])

# ---------- 追踪模块 ----------
# 点击追踪路由（必须在其他路由之前，避免路径冲突，无前缀）
api_router.include_router(tracking, prefix="", tags=["点击追踪"])
# 短链接服务路由
api_router.include_router(short_links, prefix="/short-links", tags=["短链接服务"])

# ---------- CPL系统模块 ----------
api_router.include_router(advertisers, prefix="/advertisers", tags=["广告主管理"])
api_router.include_router(publishers, prefix="/publishers", tags=["渠道管理"])
api_router.include_router(offers, prefix="/offers", tags=["Offer管理"])
api_router.include_router(caps, prefix="/caps", tags=["Cap管理"])
api_router.include_router(discounts, prefix="/discounts", tags=["扣量管理"])
api_router.include_router(conversion_deductions, prefix="/conversion-deductions", tags=["转化扣减管理"])
api_router.include_router(conversion_summary, prefix="/conversion-summary", tags=["转化统计"])
api_router.include_router(conversion_log, prefix="/conversion-logs", tags=["转化日志（已废弃）"])
api_router.include_router(clicks, prefix="/clicks", tags=["短链接访问记录"])
api_router.include_router(affiliate_tests, prefix="/affiliate-tests", tags=["下游测试"])

# 导出所有路由（用于统一注册）
__all__ = [
    # 路由聚合器
    'api_router',
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
    'telegram_status',
    'third_party_reports',
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
    'affiliate_tests',
]

