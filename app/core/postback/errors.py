"""Postback 流水线业务异常。"""


class DeductionProcessingError(Exception):
    """扣量计算或日志写入失败（fail-close 时向上抛出）。"""
