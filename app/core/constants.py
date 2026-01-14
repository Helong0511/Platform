"""
应用常量定义
集中管理应用中使用的魔法数字和常量值
"""
# ====== 分页配置 ======
# 默认分页大小
DEFAULT_PAGE_SIZE = 10
# 最大分页大小
MAX_PAGE_SIZE = 100
# 默认分页大小（移动端）
MOBILE_DEFAULT_PAGE_SIZE = 10
# 最大分页大小（移动端）
MOBILE_MAX_PAGE_SIZE = 15
# 默认分页大小（平板端）
TABLET_DEFAULT_PAGE_SIZE = 15
# 最大分页大小（平板端）
TABLET_MAX_PAGE_SIZE = 25
# 桌面端最大分页大小
DESKTOP_MAX_PAGE_SIZE = 100

# ====== 查询超时配置 ======
# 数据库查询超时（秒）
QUERY_TIMEOUT = 30.0

# ====== 缓存配置 ======
# 默认缓存TTL（秒）
DEFAULT_CACHE_TTL = 300  # 5分钟
# 短期缓存TTL（秒）
SHORT_CACHE_TTL = 60  # 1分钟
# 长期缓存TTL（秒）
LONG_CACHE_TTL = 3600  # 1小时

# ====== 计算常量 ======
# eCPM 计算系数（收益/展示数 * ECPM_MULTIPLIER）
ECPM_MULTIPLIER = 1000
# 百分比计算系数
PERCENTAGE_MULTIPLIER = 100

# ====== 数值精度 ======
# 小数位数（用于 eCPM、收益等）
DECIMAL_PLACES = 2

# ====== 字符串长度限制 ======
# 任务名称最大长度
MAX_TASK_NAME_LENGTH = 100

