"""
广告比率指标计算器。

功能说明：
- 计算 CTR、填充率、ECPM 等衍生比率指标
- 对分母为零场景返回安全默认值

在系统中的位置：
- 被 ``AdDataService`` 统计接口与导出逻辑调用

注意事项：
1. 比率结果建议保留固定小数位，与前端 ``percentFormat`` 一致
2. 勿将比率与绝对量混在同一聚合 SQL，先聚合再计算比率
"""
import logging

logger = logging.getLogger(__name__)


class RateCalculator:
    """比率计算器"""

    @staticmethod
    def calculate_coverage_rate(
            match_count: int,
            request_count: int
    ) -> float:
        """
        计算覆盖率
        
        Args:
            match_count: 匹配数
            request_count: 请求数
        
        Returns:
            float: 覆盖率（百分比）
        """
        if request_count <= 0:
            return 0.0

        rate = (match_count / request_count) * 100
        return round(rate, 2)

    @staticmethod
    def calculate_display_rate(
            display_count: int,
            match_count: int
    ) -> float:
        """
        计算展示率
        
        Args:
            display_count: 展示数
            match_count: 匹配数
        
        Returns:
            float: 展示率（百分比）
        """
        if match_count <= 0:
            return 0.0

        rate = (display_count / match_count) * 100
        return round(rate, 2)

    @staticmethod
    def calculate_click_rate(
            click_count: int,
            display_count: int
    ) -> float:
        """
        计算点击率
        
        Args:
            click_count: 点击数
            display_count: 展示数
        
        Returns:
            float: 点击率（百分比）
        """
        if display_count <= 0:
            return 0.0

        rate = (click_count / display_count) * 100
        return round(rate, 2)

    @staticmethod
    def calculate_viewability_rate(
            viewable_count: int,
            display_count: int
    ) -> float:
        """
        计算可见率
        
        Args:
            viewable_count: 可见展示数
            display_count: 展示数
        
        Returns:
            float: 可见率（百分比）
        """
        if display_count <= 0:
            return 0.0

        rate = (viewable_count / display_count) * 100
        return round(rate, 2)

    @staticmethod
    def calculate_all_rates(
            request_count: int,
            match_count: int,
            display_count: int,
            click_count: int
    ) -> dict:
        """
        计算所有比率
        
        Args:
            request_count: 请求数
            match_count: 匹配数
            display_count: 展示数
            click_count: 点击数
        
        Returns:
            dict: 比率字典
        """
        return {
            'coverage_rate': RateCalculator.calculate_coverage_rate(match_count, request_count),
            'display_rate': RateCalculator.calculate_display_rate(display_count, match_count),
            'click_rate': RateCalculator.calculate_click_rate(click_count, display_count),
        }
