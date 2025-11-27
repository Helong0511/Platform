"""
定时任务名称配置
统一管理所有定时任务的名称，避免在多个地方修改

使用说明：
1. 在这里定义所有任务名称常量
2. 所有任务文件、注册文件都引用这里的常量
3. 修改任务名称时，只需在这里修改一次即可
4. 添加新任务时，在这里添加常量并更新 ALL_TASK_NAMES 列表
"""

# ==================== 任务名称常量定义 ====================
# 数据归档任务
ARCHIVE_DATA_TASK_NAME = "数据归档任务"

# 清理旧日志任务
CLEANUP_LOGS_TASK_NAME = "清理旧日志"

# 清理过期会话和黑名单任务
CLEANUP_SESSIONS_TASK_NAME = "清理过期会话和黑名单"

# TQT API获取数据任务
TQT_API_TASK_NAME = "TQT API获取数据"

# Skymobi API获取数据任务
SKYMOBI_API_TASK_NAME = "Skymobi API获取数据"

# yangyangdeyi API获取数据任务
TBSJ_API_TASK_NAME = "yangyangdeyi API获取数据"

# yangyangdeyi API获取数据任务
ADDERMOBI_API_TASK_NAME = "Addermobi API获取数据"

# ==================== 任务名称映射 ====================
# 用于快速查找任务名称，格式：{任务模块名: 任务名称常量}

TASK_NAME_MAP = {
    "archive_old_data": ARCHIVE_DATA_TASK_NAME,
    "cleanup_old_logs": CLEANUP_LOGS_TASK_NAME,
    "cleanup_expired_sessions": CLEANUP_SESSIONS_TASK_NAME,
    "tqt_task": TQT_API_TASK_NAME,
    "skymobi_task": SKYMOBI_API_TASK_NAME,
    "tbsj_task": TBSJ_API_TASK_NAME,
    "addermobi_task": ADDERMOBI_API_TASK_NAME,
}

# ==================== 所有任务名称列表 ====================
# 用于批量操作和验证

ALL_TASK_NAMES = [
    ARCHIVE_DATA_TASK_NAME,
    CLEANUP_SESSIONS_TASK_NAME,
    CLEANUP_LOGS_TASK_NAME,
    TQT_API_TASK_NAME,
    SKYMOBI_API_TASK_NAME,
    TBSJ_API_TASK_NAME,
    ADDERMOBI_API_TASK_NAME,
]


# ==================== 辅助函数 ====================

def get_task_name_by_module(module_name: str) -> str | None:
    """
    根据模块名获取任务名称
    
    Args:
        module_name: 任务模块名（如：'tqt_task'）
        
    Returns:
        任务名称，如果不存在返回 None
    """
    return TASK_NAME_MAP.get(module_name)


def is_valid_task_name(task_name: str) -> bool:
    """
    检查任务名称是否有效
    
    Args:
        task_name: 要检查的任务名称
        
    Returns:
        如果任务名称在列表中返回 True，否则返回 False
    """
    return task_name in ALL_TASK_NAMES
