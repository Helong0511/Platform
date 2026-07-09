"""核心缺陷修复回归：轮询扣量、Addermobi 覆盖率缩放。"""
from types import SimpleNamespace

from app.core.deduction.deduction_manager import (
    ConversionStats,
    ProportionalDeductionStrategy,
    RoundRobinDeductionStrategy,
)
from app.scheduler_module.upstream_import import preprocess_addermobi_match_counts


def _deduction_config(ratio: float):
    return SimpleNamespace(volume_deduction_ratio=ratio)


def test_round_robin_does_not_deduct_first_conversion():
    """processed=0 时不应扣量（与 proportional 对齐）。"""
    strategy = RoundRobinDeductionStrategy()
    config = _deduction_config(0.2)  # interval=5
    stats = ConversionStats()
    assert stats.processed == 0
    assert strategy.should_deduct(config, stats) is False


def test_round_robin_deducts_on_interval():
    strategy = RoundRobinDeductionStrategy()
    config = _deduction_config(0.2)  # interval=5
    stats = ConversionStats()
    # 第 5 笔（processed 从 0 计到 4 后再判，或直接设 processed=4）
    stats.processed = 4
    assert strategy.should_deduct(config, stats) is True
    stats.processed = 5
    assert strategy.should_deduct(config, stats) is False


def test_proportional_and_round_robin_align_on_first():
    config = _deduction_config(0.25)  # interval=4
    stats = ConversionStats()
    assert ProportionalDeductionStrategy().should_deduct(config, stats) is False
    assert RoundRobinDeductionStrategy().should_deduct(config, stats) is False


def test_addermobi_coverage_percent_scaled():
    rows = [
        {
            "AdRequests": 1000,
            "MatchedAdRequests": 0,
            "AdRequestsCoverage": 80,  # 百分比
        }
    ]
    preprocess_addermobi_match_counts(rows)
    assert rows[0]["MatchedAdRequests"] == 800


def test_addermobi_coverage_ratio_unchanged():
    rows = [
        {
            "AdRequests": 1000,
            "MatchedAdRequests": 0,
            "AdRequestsCoverage": 0.8,  # 0–1 比例
        }
    ]
    preprocess_addermobi_match_counts(rows)
    assert rows[0]["MatchedAdRequests"] == 800
