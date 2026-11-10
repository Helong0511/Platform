"""
定时任务名称常量配置模块。

功能说明：
- 集中定义所有 scheduled_tasks.name 对应的中文/业务任务名常量
- 提供 ``ALL_TASK_NAMES`` 列表供 DB 初始化与注册表校验使用

使用说明：
1. 新增任务时在此添加 ``XXX_TASK_NAME`` 常量并更新 ``ALL_TASK_NAMES``
2. tasks/*.py、task_config.py、task_registry 均引用本模块常量，禁止硬编码字符串
3. 重命名任务须同步更新 DB 已有行或做迁移，否则调度器找不到函数

在系统中的位置：
- 被整个 scheduler_module 与 scheduled_task_service 引用

注意事项：
1. 任务名同时出现在管理端 UI，修改需考虑运营人员识别习惯
2. 常量值长度受 scheduled_tasks.name 字段限制
"""

# Postback 下游转发队列处理
POSTBACK_FORWARD_QUEUE_TASK_NAME = "Postback转发队列处理"

# ==================== 任务名称常量定义 ====================
# 数据归档任务
ARCHIVE_DATA_TASK_NAME = "数据归档任务"

# 清理旧日志任务（DB 审计）
CLEANUP_LOGS_TASK_NAME = "清理旧日志"

# 清理文件日志任务（logs/ 磁盘文件）
CLEANUP_FILE_LOGS_TASK_NAME = "清理文件日志"

# 清理过期会话和黑名单任务
CLEANUP_SESSIONS_TASK_NAME = "清理过期会话和黑名单"

# 清理敏感路径拦截日志任务
CLEANUP_SENSITIVE_PROBES_TASK_NAME = "清理敏感路径拦截日志"

# TQT API获取数据任务
TQT_API_TASK_NAME = "TQT API获取数据"

# Skymobi API获取数据任务
SKYMOBI_API_TASK_NAME = "Skymobi API获取数据"

# yangyangdeyi API获取数据任务
TBSJ_API_TASK_NAME = "yangyangdeyi API获取数据"

# yangyangdeyi API获取数据任务
ADDERMOBI_API_TASK_NAME = "Addermobi API获取数据"

# Huguang API获取数据任务
HUGUANG_API_TASK_NAME = "Huguang API获取数据"

# ZhiSuo API获取数据任务
ZHISUO_API_TASK_NAME = "ZhiSuo API获取数据"

# Pomiad API获取数据任务
POMIAD_API_TASK_NAME = "Pomiad API获取数据"

# H5 Deer API获取数据任务
H5DEER_API_TASK_NAME = "H5 Deer API获取数据"

# Aya API获取数据任务
AYA_API_TASK_NAME = "Aya API获取数据"

# FlyMobi API获取数据任务
FLYMOBI_API_TASK_NAME = "FlyMobi API获取数据"

# LeiYang API获取数据任务
LEIYANG_API_TASK_NAME = "LeiYang API获取数据"

# IDGTN API获取数据任务
IDGTN_API_TASK_NAME = "IDGTN API获取数据"

# PlayHorizonx API获取数据任务
PLAYHORIZONX_API_TASK_NAME = "PlayHorizonx API获取数据"

# SweetStaste API获取数据任务
SWEETSTASTE_API_TASK_NAME = "SweetStaste API获取数据"

# Asone API获取数据任务
ASONE_API_TASK_NAME = "Asone API获取数据"

# Google Ad Manager API获取数据任务
GAM_API_TASK_NAME = "Google API获取数据"

# CPL 系统定时任务
RESET_DAILY_CAPS_TASK_NAME = "每日Cap重置"

# 广告数据健康巡检
AD_DATA_BASELINE_FREEZE_TASK_NAME = "广告数据标准日冻结"
AD_DATA_HEALTH_SCAN_TASK_NAME = "广告数据健康巡检"

# ==================== 任务名称映射 ====================
# 用于快速查找任务名称，格式：{任务模块名: 任务名称常量}

TASK_NAME_MAP = {
    "forward_tasks": POSTBACK_FORWARD_QUEUE_TASK_NAME,
    "archive_old_data": ARCHIVE_DATA_TASK_NAME,
    "cleanup_old_logs": CLEANUP_LOGS_TASK_NAME,
    "cleanup_file_logs": CLEANUP_FILE_LOGS_TASK_NAME,
    "cleanup_expired_sessions": CLEANUP_SESSIONS_TASK_NAME,
    "cleanup_sensitive_path_probes": CLEANUP_SENSITIVE_PROBES_TASK_NAME,
    "tqt_task": TQT_API_TASK_NAME,
    "skymobi_task": SKYMOBI_API_TASK_NAME,
    "tbsj_task": TBSJ_API_TASK_NAME,
    "addermobi_task": ADDERMOBI_API_TASK_NAME,
    "huguang_task": HUGUANG_API_TASK_NAME,
    "zhisuo_task": ZHISUO_API_TASK_NAME,
    "pomiad_task": POMIAD_API_TASK_NAME,
    "h5deer_task": H5DEER_API_TASK_NAME,
    "aya_task": AYA_API_TASK_NAME,
    "flymobi_task": FLYMOBI_API_TASK_NAME,
    "leiyang_task": LEIYANG_API_TASK_NAME,
    "idgtn_task": IDGTN_API_TASK_NAME,
    "playhorizonx_task": PLAYHORIZONX_API_TASK_NAME,
    "sweetstaste_task": SWEETSTASTE_API_TASK_NAME,
    "asone_task": ASONE_API_TASK_NAME,
    "gam_task": GAM_API_TASK_NAME,
    "cpl_tasks": RESET_DAILY_CAPS_TASK_NAME,
    "ad_data_health_task": AD_DATA_HEALTH_SCAN_TASK_NAME,
}

# ==================== 所有任务名称列表 ====================
# 用于批量操作和验证

ALL_TASK_NAMES = [
    POSTBACK_FORWARD_QUEUE_TASK_NAME,
    ARCHIVE_DATA_TASK_NAME,
    CLEANUP_SESSIONS_TASK_NAME,
    CLEANUP_SENSITIVE_PROBES_TASK_NAME,
    CLEANUP_LOGS_TASK_NAME,
    CLEANUP_FILE_LOGS_TASK_NAME,
    TQT_API_TASK_NAME,
    SKYMOBI_API_TASK_NAME,
    TBSJ_API_TASK_NAME,
    ADDERMOBI_API_TASK_NAME,
    HUGUANG_API_TASK_NAME,
    ZHISUO_API_TASK_NAME,
    POMIAD_API_TASK_NAME,
    H5DEER_API_TASK_NAME,
    AYA_API_TASK_NAME,
    FLYMOBI_API_TASK_NAME,
    LEIYANG_API_TASK_NAME,
    IDGTN_API_TASK_NAME,
    PLAYHORIZONX_API_TASK_NAME,
    SWEETSTASTE_API_TASK_NAME,
    ASONE_API_TASK_NAME,
    GAM_API_TASK_NAME,
    RESET_DAILY_CAPS_TASK_NAME,
    AD_DATA_BASELINE_FREEZE_TASK_NAME,
    AD_DATA_HEALTH_SCAN_TASK_NAME,
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
