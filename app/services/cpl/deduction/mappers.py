"""
转化扣减 API 响应与 Excel 导出行映射。
"""
from typing import Any, Dict, List

from app.models.models import ConversionDeductionConfig, ConversionDeductionLog
from app.schemas.cpl.deduction import (
    ConversionDeductionConfigResponse,
    ConversionDeductionLogResponse,
    DeductionStatsResponse,
)

_STRATEGY_LABELS = {
    "random": "随机",
    "proportional": "按比例",
    "round_robin": "轮询",
}


def to_config_response(config: ConversionDeductionConfig) -> ConversionDeductionConfigResponse:
    """将 ORM 配置转为 API 响应，并填充 level、target_id、target_name。"""
    config_data = ConversionDeductionConfigResponse.model_validate(config)
    if config.advertiser:
        config_data.target_name = config.advertiser.advertiser_name
        config_data.advertiser_name = config.advertiser.advertiser_name
        config_data.level = "advertiser"
        config_data.target_id = config.advertiser_id
    elif config.offer:
        config_data.target_name = config.offer.offer_name
        config_data.offer_name = config.offer.offer_name
        config_data.level = "offer"
        config_data.target_id = config.offer_id
    elif config.publisher:
        config_data.target_name = config.publisher.publisher_name
        config_data.publisher_name = config.publisher.publisher_name
        config_data.level = "publisher"
        config_data.target_id = config.publisher_id
    return config_data


def to_config_response_list(
    configs: List[ConversionDeductionConfig],
) -> List[ConversionDeductionConfigResponse]:
    return [to_config_response(c) for c in configs]


def to_log_response(log: ConversionDeductionLog) -> ConversionDeductionLogResponse:
    """将扣减日志 ORM 转为 API 响应，附加关联名称字段。"""
    log_data = ConversionDeductionLogResponse.model_validate(log)
    if log.advertiser:
        log_data.advertiser_name = log.advertiser.advertiser_name
    if log.offer:
        log_data.offer_name = log.offer.offer_name
    if log.publisher:
        log_data.publisher_name = log.publisher.publisher_name
    return log_data


def to_log_response_list(logs: List[ConversionDeductionLog]) -> List[ConversionDeductionLogResponse]:
    return [to_log_response(log) for log in logs]


def config_to_export_row(config: ConversionDeductionConfig) -> Dict[str, Any]:
    """将单条配置转为 Excel 导出行（中文列名）。"""
    level_name = ""
    target_name = ""
    if config.advertiser:
        level_name = "广告主"
        target_name = config.advertiser.advertiser_name
    elif config.offer:
        level_name = "Offer"
        target_name = config.offer.offer_name
    elif config.publisher:
        level_name = "渠道"
        target_name = config.publisher.publisher_name

    strategy_name = _STRATEGY_LABELS.get(config.deduction_strategy, config.deduction_strategy)
    return {
        "配置ID": config.id,
        "配置层级": level_name,
        "配置对象": target_name,
        "启用扣量": "是" if config.enable_volume_deduction else "否",
        "扣量比例": (
            f"{(config.volume_deduction_ratio * 100):.2f}%"
            if config.enable_volume_deduction
            else "0%"
        ),
        "扣减策略": strategy_name if config.enable_volume_deduction else "-",
        "启用扣金额": "是" if config.enable_amount_deduction else "否",
        "扣金额比例": (
            f"{(config.amount_deduction_ratio * 100):.2f}%"
            if config.enable_amount_deduction
            else "0%"
        ),
        "优先级": config.priority,
        "状态": "启用" if config.is_active else "禁用",
        "创建时间": config.created_at.strftime("%Y-%m-%d %H:%M:%S") if config.created_at else "",
        "更新时间": config.updated_at.strftime("%Y-%m-%d %H:%M:%S") if config.updated_at else "",
    }


def log_to_export_row(log: ConversionDeductionLog) -> Dict[str, Any]:
    """将单条扣减日志转为 Excel 导出行。"""
    log_response = to_log_response(log)
    strategy_label = _STRATEGY_LABELS.get(
        log_response.deduction_strategy,
        log_response.deduction_strategy or "",
    )
    return {
        "日志ID": log_response.id,
        "转化ID": log_response.conversion_id if log_response.conversion_id else "已扣量",
        "点击ID": log_response.click_id or "",
        "广告主": log_response.advertiser_name or "",
        "Offer": log_response.offer_name or "",
        "渠道": log_response.publisher_name or "",
        "扣减策略": strategy_label,
        "原始数量": log_response.original_volume or 0,
        "扣减数量": log_response.deducted_volume or 0,
        "最终数量": log_response.final_volume or 0,
        "扣量比例": f"{(log_response.volume_deduction_ratio or 0) * 100:.2f}%",
        "原始金额": f"${log_response.original_amount or 0:.2f}",
        "扣减金额": f"${log_response.deducted_amount or 0:.2f}",
        "最终金额": f"${log_response.final_amount or 0:.2f}",
        "扣金额比例": f"{(log_response.amount_deduction_ratio or 0) * 100:.2f}%",
        "扣减原因": log_response.deduction_reason or "",
        "创建时间": str(log_response.created_at) if log_response.created_at else "",
    }


def stats_to_export_rows(stats: DeductionStatsResponse) -> List[Dict[str, Any]]:
    """将统计数据转为 Excel 导出行列表（首行为汇总，其余为分组项）。"""
    data = [
        {
            "类型": "汇总",
            "原始转化数量": stats.original_volume,
            "扣减转化数量": stats.deducted_volume,
            "最终转化数量": stats.final_volume,
            "扣量比例": f"{(stats.volume_deduction_ratio * 100):.2f}%",
            "原始转化金额": f"${stats.original_amount:.2f}",
            "扣减转化金额": f"${stats.deducted_amount:.2f}",
            "最终转化金额": f"${stats.final_amount:.2f}",
            "扣金额比例": f"{(stats.amount_deduction_ratio * 100):.2f}%",
        }
    ]
    if stats.items:
        for item in stats.items:
            data.append({
                "类型": item.get("name", "未知"),
                "原始转化数量": item.get("original_volume", 0),
                "扣减转化数量": item.get("deducted_volume", 0),
                "最终转化数量": item.get("final_volume", 0),
                "扣量比例": f"{(item.get('volume_deduction_ratio', 0) * 100):.2f}%",
                "原始转化金额": f"${item.get('original_amount', 0):.2f}",
                "扣减转化金额": f"${item.get('deducted_amount', 0):.2f}",
                "最终转化金额": f"${item.get('final_amount', 0):.2f}",
                "扣金额比例": f"{(item.get('amount_deduction_ratio', 0) * 100):.2f}%",
            })
    return data
