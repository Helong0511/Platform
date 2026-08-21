"""
定时任务统一配置文件
在这里配置所有定时任务，系统会自动完成注册

==========================================
添加新任务的步骤：
==========================================

1. 创建任务文件（如 app/scheduler_module/tasks/my_task.py）
   - 实现任务函数（如 async def my_task_function()）
   - 实现 get_task_result 函数（用于获取执行结果）
   - 实现 set_task_result 函数（用于保存执行结果）
   - 在任务执行时调用 set_task_result() 保存结果

2. 在 task_names.py 中添加任务名称常量（可选，但推荐）
   - MY_TASK_NAME = "我的新任务"

3. 在这里添加任务配置（只需添加一个配置项即可）
   - 取消注释下面的示例代码
   - 修改为你的任务信息

4. 完成！系统会自动：
   - 注册任务函数
   - 注册结果获取函数
   - 无需修改其他文件

==========================================
配置格式说明：
==========================================

{
    "任务名称（用于配置键）": {
        "task_name": "任务名称（与数据库中的 task_name 对应）",
        "task_module": "任务模块路径（如：app.scheduler_module.tasks.my_task）",
        "task_function": "任务函数名（如：my_task_function）",
        "result_getter_module": "结果获取函数模块路径（通常与 task_module 相同）",
        "result_getter_function": "结果获取函数名（通常是 get_task_result）",
        "wrapper": False,  # 可选，如果需要包装函数（如清理旧日志任务）设为 True
        # 数据库配置（可选，如果数据库中不存在，使用这些默认值）
        "cron_expression": "0 * * * *",  # Cron表达式（如：每10分钟 "*/10 * * * *"）
        "description": "任务描述",
    }
}
"""
from typing import Dict, Any

# 任务配置类型定义
TaskConfig = Dict[str, Any]

# ==============================================================================
# 定时任务配置
# ==============================================================================
# 格式说明：
# {
#     "任务名称": {
#         "task_name": "任务名称（与数据库中的 task_name 对应）",
#         "task_module": "任务模块路径（如：app.scheduler_module.tasks.tqt_task）",
#         "task_function": "任务函数名（如：tqt_api_task）",
#         "result_getter_module": "结果获取函数模块路径（通常与 task_module 相同）",
#         "result_getter_function": "结果获取函数名（通常是 get_task_result）",
#     }
# }
# ==============================================================================

TASK_CONFIGS: Dict[str, TaskConfig] = {
    # ========== 数据归档任务 ==========
    "数据归档任务": {
        "task_name": "数据归档任务",
        "task_module": "app.scheduler_module.tasks.archive_old_data",
        "task_function": "archive_old_ad_data",
        "result_getter_module": "app.scheduler_module.tasks.archive_old_data",
        "result_getter_function": "get_task_result",
        # 数据库配置（如果数据库中不存在，使用这些默认值）
        "cron_expression": "0 1 1 * *",  # 每月1号凌晨1点
        "description": "归档6个月前的数据",
    },

    # ========== 清理旧日志任务 ==========
    "清理旧日志": {
        "task_name": "清理旧日志",
        "task_module": "app.scheduler_module.tasks.cleanup_old_logs",
        "task_function": "cleanup_old_audit_logs",
        "result_getter_module": "app.scheduler_module.tasks.cleanup_old_logs",
        "result_getter_function": "get_task_result",
        # 特殊处理：需要包装函数使用配置参数
        "wrapper": True,
        # 数据库配置
        "cron_expression": "0 2 1 * *",  # 每月1号凌晨2点
        "description": "清理90天前的用户操作日志，减少日志表数据量",
    },

    # ========== 清理文件日志任务 ==========
    "清理文件日志": {
        "task_name": "清理文件日志",
        "task_module": "app.scheduler_module.tasks.cleanup_file_logs",
        "task_function": "cleanup_file_logs",
        "result_getter_module": "app.scheduler_module.tasks.cleanup_file_logs",
        "result_getter_function": "get_task_result",
        "cron_expression": "30 3 * * *",  # 每天凌晨 3:30
        "description": "清理超期文件日志：轮转备份归档/删除、archive 超期清理、gunicorn 溢出轮转与磁盘守卫",
    },

    # ========== 清理过期会话和黑名单任务 ==========
    "清理过期会话和黑名单": {
        "task_name": "清理过期会话和黑名单",
        "task_module": "app.scheduler_module.tasks.cleanup_expired_sessions",
        "task_function": "cleanup_expired_sessions",
        "result_getter_module": "app.scheduler_module.tasks.cleanup_expired_sessions",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "0 2 * * *",  # 每天凌晨2点
        "description": "清理过期超过30天的会话记录和黑名单记录，标记超过7天未活动的会话为非活跃",
    },

    # ========== 清理敏感路径拦截日志 ==========
    "清理敏感路径拦截日志": {
        "task_name": "清理敏感路径拦截日志",
        "task_module": "app.scheduler_module.tasks.cleanup_sensitive_path_probes",
        "task_function": "cleanup_sensitive_path_probe_logs",
        "result_getter_module": "app.scheduler_module.tasks.cleanup_sensitive_path_probes",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "0 3 * * *",  # 每天凌晨3点
        "description": "自动清理过期敏感路径拦截日志（默认保留最近90天，可通过环境变量调整）",
    },

    # ========== CPL 系统定时任务 ==========
    "每日Cap重置": {
        "task_name": "每日Cap重置",
        "task_module": "app.scheduler_module.tasks.cpl_tasks",
        "task_function": "reset_daily_caps_task",
        "result_getter_module": "app.scheduler_module.tasks.cpl_tasks",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "0 0 * * *",  # 每天 00:00（业务时区）
        "description": "重置所有Cap配置的每日计数，每天执行一次",
    },

    # ========== 短链接服务定时任务 ==========
    "短链接点击次数同步": {
        "task_name": "短链接点击次数同步",
        "task_module": "app.scheduler_module.tasks.short_link_tasks",
        "task_function": "sync_short_link_clicks_task",
        "result_getter_module": "app.scheduler_module.tasks.short_link_tasks",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "*/5 * * * *",  # 每5分钟执行一次
        "description": "将Redis中的短链接点击次数批量同步到数据库，每5分钟执行一次",
    },

    "点击记录队列批量处理": {
        "task_name": "点击记录队列批量处理",
        "task_module": "app.scheduler_module.tasks.short_link_tasks",
        "task_function": "process_clicks_queue_task",
        "result_getter_module": "app.scheduler_module.tasks.short_link_tasks",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "* * * * *",  # 每分钟执行一次（高并发优化，实际处理时会循环处理直到队列为空）
        "description": "从Redis队列批量取出点击记录并插入到数据库，每分钟执行一次，每次处理最多1000条（高并发优化）",
    },

    "点击记录归档": {
        "task_name": "点击记录归档",
        "task_module": "app.scheduler_module.tasks.archive_old_clicks",
        "task_function": "archive_old_clicks",
        "result_getter_module": "app.scheduler_module.tasks.archive_old_clicks",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "0 3 1 * *",  # 每月1号凌晨3点执行
        "description": "归档90天前的点击记录到归档表，减少主表数据量，提升查询性能",
    },

    "每日打开短链接": {
        "task_name": "每日打开短链接",
        "task_module": "app.scheduler_module.tasks.short_link_tasks",
        "task_function": "open_closed_short_links_task",
        "result_getter_module": "app.scheduler_module.tasks.short_link_tasks",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "0 0 * * *",  # 每天 00:00（业务时区，与 Cap 日切对齐）
        "description": "每天执行一次，在 Cap 有余量时将因超限关闭的短链接重新激活",
    },

    "Cap计数同步": {
        "task_name": "Cap计数同步",
        "task_module": "app.scheduler_module.tasks.cpl_tasks",
        "task_function": "cap_sync_task",
        "result_getter_module": "app.scheduler_module.tasks.cpl_tasks",
        "result_getter_function": "get_task_result",
        "cron_expression": "*/5 * * * *",
        "description": "每5分钟将 Redis Cap 计数同步到数据库",
    },

    # ========== TQT API获取数据任务 ==========
    "TQT API获取数据": {
        "task_name": "TQT API获取数据",
        "task_module": "app.scheduler_module.tasks.tqt_task",
        "task_function": "tqt_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "*/30 * * * *",  # 每10分钟
        "description": "每隔30分钟执行一次，从TQT API获取广告数据并导入到数据库",
    },

    # ========== Skymobi API获取数据任务 ==========
    "Skymobi API获取数据": {
        "task_name": "Skymobi API获取数据",
        "task_module": "app.scheduler_module.tasks.skymobi_task",
        "task_function": "skymobi_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "*/30 * * * *",  # 每10分钟
        "description": "每隔10分钟执行一次，从Skymobi API获取广告数据",
    },

    # ========== yangyangdeyi API获取数据任务 ==========
    "yangyangdeyi API获取数据": {
        "task_name": "yangyangdeyi API获取数据",
        "task_module": "app.scheduler_module.tasks.tbsj_task",
        "task_function": "tbsj_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "*/30 * * * *",  # 每10分钟
        "description": "每隔30分钟执行一次，从yangyangdeyi(/adunit)拉取国家+广告单元交叉数据",
    },

    # ========== Addermobi API获取数据任务 ==========
    "Addermobi API获取数据": {
        "task_name": "Addermobi API获取数据",
        "task_module": "app.scheduler_module.tasks.addermobi_task",
        "task_function": "addermobi_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "*/30 * * * *",  # 每10分钟
        "description": "每隔30分钟执行一次，从Addermobi API获取广告数据",
    },
    # ========== Huguang API获取数据任务 ==========
    "Huguang API获取数据": {
        "task_name": "Huguang API获取数据",
        "task_module": "app.scheduler_module.tasks.huguang_task",
        "task_function": "huguang_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "*/30 * * * *",  # 每30分钟
        "description": "每隔30分钟执行一次，从Huguang API获取广告数据",
    },

    # ========== ZhiSuo API获取数据任务 ==========
    "ZhiSuo API获取数据": {
        "task_name": "ZhiSuo API获取数据",
        "task_module": "app.scheduler_module.tasks.zhisuo_task",
        "task_function": "zhisuo_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        "cron_expression": "*/30 * * * *",
        "description": "每隔30分钟执行一次，从 ZhiSuo/tecnee API 按账号拉取；优先交叉(channeldata)，次之国家(channelcountry 补未覆盖)，可选单元/日报兜底；单账号失败隔离并继续其它账号（ZHISUO_API_ACCOUNT_FETCH 按 clientId 配置）",
    },

    # ========== Pomiad API获取数据任务 ==========
    "Pomiad API获取数据": {
        "task_name": "Pomiad API获取数据",
        "task_module": "app.scheduler_module.tasks.pomiad_task",
        "task_function": "pomiad_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        "cron_expression": "*/30 * * * *",
        "description": "每隔30分钟执行一次，从 Pomiad API 获取广告明细数据",
    },

    # ========== H5 Deer API获取数据任务 ==========
    "H5 Deer API获取数据": {
        "task_name": "H5 Deer API获取数据",
        "task_module": "app.scheduler_module.tasks.h5deer_task",
        "task_function": "h5deer_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        "cron_expression": "*/30 * * * *",
        "description": "每隔30分钟执行一次，从 H5 Deer API 获取广告明细数据",
    },

    # ========== Aya API获取数据任务 ==========
    "Aya API获取数据": {
        "task_name": "Aya API获取数据",
        "task_module": "app.scheduler_module.tasks.aya_task",
        "task_function": "aya_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        "cron_expression": "*/30 * * * *",
        "description": (
            "每隔30分钟执行一次，从 Aya API 拉取日报/国家/广告单元报表"
            "（默认仅国家维度；AYA_API_FETCH_DAILY / COUNTRY / UNIT 控制）"
        ),
    },

    # ========== FlyMobi API获取数据任务 ==========
    "FlyMobi API获取数据": {
        "task_name": "FlyMobi API获取数据",
        "task_module": "app.scheduler_module.tasks.flymobi_task",
        "task_function": "flymobi_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        "cron_expression": "*/30 * * * *",
        "description": (
            "每隔30分钟执行一次，从 FlyMobi API 拉取 Ad Manager 报表"
            "（默认 countryList；FLYMOBI_API_FETCH_UNIT / DAILY 控制）"
        ),
    },

    # ========== LeiYang API获取数据任务 ==========
    "LeiYang API获取数据": {
        "task_name": "LeiYang API获取数据",
        "task_module": "app.scheduler_module.tasks.leiyang_task",
        "task_function": "leiyang_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        "cron_expression": "*/30 * * * *",
        "description": (
            "每隔30分钟执行一次，从 LeiYang DataManager 拉取报表"
            "（默认 atomic 国家+广告单元；LEIYANG_API_FETCH_ATOMIC / COUNTRY / UNIT / DAILY 控制）"
        ),
    },

    # ========== Google API获取数据任务（GAM） ==========
    "Google API获取数据": {
        "task_name": "Google API获取数据",
        "task_module": "app.scheduler_module.tasks.gam_task",
        "task_function": "google_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        "cron_expression": "0 * * * *",
        "description": (
            "每小时整点从 Google Ad Manager 拉取 ad_unit/country/site 报表（内存），"
            "country 交叉行与 ad_unit 纯单元行分形态入库；日期默认昨天+今天；"
            "需存在 config/gam_scheduler.json 且配置账号后才会执行"
        ),
    },

    # ========== IDGTN API获取数据任务 ==========
    "IDGTN API获取数据": {
        "task_name": "IDGTN API获取数据",
        "task_module": "app.scheduler_module.tasks.idgtn_task",
        "task_function": "idgtn_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        "cron_expression": "*/30 * * * *",
        "description": (
            "每隔30分钟执行一次，从 IDGTN /download/country 拉取广告单元+日期+国家报表"
            "（按平台 cross 维度入库；IDGTN_API_FETCH_COUNTRY 控制）"
        ),
    },

    # ========== PlayHorizonx API获取数据任务 ==========
    "PlayHorizonx API获取数据": {
        "task_name": "PlayHorizonx API获取数据",
        "task_module": "app.scheduler_module.tasks.playhorizonx_task",
        "task_function": "playhorizonx_api_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        "cron_expression": "*/30 * * * *",
        "description": (
            "每隔30分钟执行一次，从 PlayHorizonx /reports/index 拉取广告单元报表"
            "（按平台 unit 维度入库；PLAYHORIZONX_API_FETCH_UNIT 控制）"
        ),
    },

    # ==============================================================================
    # 添加新任务示例（取消注释并修改即可）
    # ==============================================================================
    # "新任务名称": {
    #     "task_name": "新任务名称",
    #     "task_module": "app.scheduler_module.tasks.my_new_task",
    #     "task_function": "my_new_task_function",
    #     "result_getter_module": "app.scheduler_module.tasks.my_new_task",
    #     "result_getter_function": "get_task_result",
    #     # 数据库配置（可选，如果不提供会使用默认值）
    #     "cron_expression": "0 * * * *",  # 默认每小时

    # ========== 通知汇总任务 ==========
    "通知汇总任务（每小时）": {
        "task_name": "通知汇总任务（每小时）",
        "task_module": "app.scheduler_module.tasks.notification_summary_task",
        "task_function": "process_hourly_notification_task",
        "result_getter_module": "app.scheduler_module.tasks.notification_summary_task",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "0 * * * *",  # 每小时整点执行
        "description": "每小时执行一次，汇总并发送 hourly 频率的客户通知",
    },

    "通知汇总任务（每天）": {
        "task_name": "通知汇总任务（每天）",
        "task_module": "app.scheduler_module.tasks.notification_summary_task",
        "task_function": "process_daily_notification_task",
        "result_getter_module": "app.scheduler_module.tasks.notification_summary_task",
        "result_getter_function": "get_task_result",
        # 数据库配置
        "cron_expression": "0 0 * * *",  # 每天 00:00 执行
        "description": "每天执行一次，汇总并发送 daily 频率的客户通知",
    },

    # ========== 广告数据健康巡检 ==========
    "广告数据标准日冻结": {
        "task_name": "广告数据标准日冻结",
        "task_module": "app.scheduler_module.tasks.ad_data_health_task",
        "task_function": "ad_data_baseline_freeze_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        "cron_expression": "30 0 * * *",  # 每天 00:30 冻结昨天
        "description": "每天 00:30 将昨天 ad_data 按「日期+产品+来源」冻结为倒扣标准（请求数+收益扣前）",
    },
    "广告数据健康巡检": {
        "task_name": "广告数据健康巡检",
        "task_module": "app.scheduler_module.tasks.ad_data_health_task",
        "task_function": "ad_data_health_scan_task",
        "result_getter_module": "app.scheduler_module.task_result_store",
        "result_getter_function": "get_task_result",
        "cron_expression": "0 1 * * *",  # 每天 01:00
        "description": "缺数/断档/昨有今无/昨天vs前天结算收益跌幅/倒扣vs日标准（请求数与收益扣前）",
    },
    #     "description": "任务描述",
    # },
}
