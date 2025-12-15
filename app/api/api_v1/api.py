"""
API路由聚合模块
统一管理所有API端点的路由注册
"""
from fastapi import APIRouter

# 创建主API路由器
api_router = APIRouter()

# 导入并注册各个功能模块的路由
# 注意：导入顺序不影响功能，但建议按功能模块分组
from app.api.api_v1.endpoints import (
    auth,
    users,
    clients,
    products,
    ad_data,
    dashboard,
    excel,
    ml_model,
    scheduled_tasks,
    audit_logs,
    client_api,
    product_assignments,
    sessions,
    telegram,
    macan_postback,
    tb_search_data,
)

# 认证路由
api_router.include_router(auth.router, prefix="/auth", tags=["认证管理"])

# 用户管理路由
api_router.include_router(users.router, prefix="/users", tags=["用户管理"])

# 客户管理路由
api_router.include_router(clients.router, prefix="/clients", tags=["客户管理"])

# 产品管理路由
api_router.include_router(products.router, prefix="/products", tags=["产品管理"])

# 产品分配历史路由
api_router.include_router(product_assignments.router, prefix="/product-assignments", tags=["产品分配历史"])

# 广告数据路由
api_router.include_router(ad_data.router, prefix="/ad-data", tags=["广告数据"])
api_router.include_router(tb_search_data.router, prefix="/tb-search-data", tags=["TB搜索数据"])

# 仪表盘路由
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["仪表盘"])

# Excel导入导出路由
api_router.include_router(excel.router, prefix="/excel", tags=["Excel处理"])

# 导入训练路由
api_router.include_router(ml_model.router, prefix="/ml-model", tags=["导入训练"])

# 定时任务管理路由
api_router.include_router(scheduled_tasks.router, prefix="/scheduled-tasks", tags=["定时任务管理"])

# 用户操作日志路由（仅管理员）
api_router.include_router(audit_logs.router, prefix="/audit-logs", tags=["操作日志"])

# 客户API路由（通过API密钥访问）
api_router.include_router(client_api.router, prefix="", tags=["客户API"])

# 会话管理路由
api_router.include_router(sessions.router, prefix="/sessions", tags=["会话管理"])

# Telegram Bot 管理路由
api_router.include_router(telegram.router, prefix="/telegram", tags=["Telegram Bot"])

# Macan S2S PostBack 路由（外部回调接口）
api_router.include_router(macan_postback.router, prefix="", tags=["Macan S2S"])
