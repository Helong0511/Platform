"""Excel 导入/导出模块

职责：广告数据与 TB 搜索数据的批量 Excel 导入、导出。

权限：需登录；部分导出需管理员。

说明：Excel 批量导入/导出，支持广告数据等业务的表格批处理。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。"""
from .router import router

__all__ = ['router']
