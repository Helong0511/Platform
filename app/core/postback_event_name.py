"""Postback 事件名规范化工具；保持轻量，避免导入 Postback 包时触发处理器注册。"""


def normalize_event_name(value) -> str:
    """将缺失/空白事件名统一映射为 default，确保各入库路径使用同一幂等键。"""
    normalized = str(value).strip() if value is not None else ""
    return normalized or "default"
