"""
仪表盘统计服务层。

功能说明：
- 封装管理端首页的核心 KPI：产品数、客户数、广告量、收入趋势等
- 按角色过滤可见范围；热点查询结果缓存 5 分钟减轻 DB 压力

在系统中的位置：
- 被 ``app.api_v1`` Dashboard 路由调用；依赖 ``app.core.cache`` 与 ``query_utils``

注意事项：
1. 客户用户仅统计已分配产品相关数据
2. 趋势图日期序列须补全缺失日期，避免折线断裂
"""
import logging
from datetime import timedelta
from typing import Dict, Any

from sqlalchemy import select, func, case, Float, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cached, set_cached, generate_cache_key
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.query_utils import date_range_condition, product_assignment_join_condition, check_use_assignment_table
from app.core.utils import get_app_now_naive
from app.models.models import User, AdData, Product, Client, UserRole, ProductAssignment

logger = logging.getLogger(__name__)


class DashboardService:
    """
    仪表盘统计服务。

    所有公开方法均接受 current_user，在 SQL 层完成数据隔离；
    聚合字段与前端 StatsCards / 趋势图组件字段一一对应。
    """

    def __init__(self, db: AsyncSession):
        """注入异步数据库会话。"""
        self.db = db

    async def get_dashboard_stats(
            self,
            period: str,
            current_user: User
    ) -> Dict[str, Any]:
        """
        获取仪表盘核心指标卡片数据（含环比趋势）。

        流程：读缓存 → 解析周期起止日期 → 聚合当前周期 → 聚合上一周期 →
        计算各指标环比% → 按角色组装 stats 列表与 ROI。

        Args:
            period: 时间周期，支持 day / week / month / last_month
            current_user: 当前登录用户（决定数据可见范围）

        Returns:
            含 stats（指标卡片列表）与 metrics（total_revenue、roi）的字典
        """
        # ====== 缓存优化 ======
        # 生成缓存键（包含用户ID和周期）
        cache_key = generate_cache_key("dashboard_stats", period, current_user.id)

        # 尝试从缓存获取（缓存 1 分钟）
        cached = await get_cached(cache_key)
        if cached:
            try:
                logger.debug(f"缓存命中: dashboard_stats, period={period}, user={current_user.id}")
                return cached
            except Exception as e:
                logger.warning(f"缓存数据格式错误，将重新查询: {e}")
                # 缓存数据格式错误，继续执行查询

        # ====== 确定时间范围 ======
        today = get_app_now_naive().date()
        if period == "day":
            start_date = today
            end_date = today
        elif period == "week":
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period == "month":
            start_date = today.replace(day=1)
            end_date = today
        elif period == "last_month":
            first_day_of_current_month = today.replace(day=1)
            last_day_of_last_month = first_day_of_current_month - timedelta(days=1)
            start_date = last_day_of_last_month.replace(day=1)
            end_date = last_day_of_last_month
        else:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail=f"无效的时间周期参数: {period}，支持: day, week, month, last_month"
            )

        # ====== 当前周期聚合查询 ======
        # 覆盖率/展示率/CTR 优先取行均值，无数据时按总量反算百分比
        query = select(
            func.cast(func.sum(AdData.request_count), Float).label('total_requests'),
            func.sum(AdData.match_count).label('total_matches'),
            func.coalesce(
                func.avg(AdData.coverage_rate),
                case((func.sum(AdData.request_count) == 0, 0),
                     else_=func.cast(func.sum(AdData.match_count), Float) * 100.0 / func.cast(
                         func.sum(AdData.request_count), Float))
            ).label('avg_coverage'),
            func.sum(AdData.display_count).label('total_impressions'),
            func.coalesce(
                func.avg(AdData.display_rate),
                case((func.sum(AdData.match_count) == 0, 0),
                     else_=func.cast(func.sum(AdData.display_count), Float) * 100.0 / func.cast(
                         func.sum(AdData.match_count), Float))
            ).label('avg_display_rate'),
            func.sum(AdData.click_count).label('total_clicks'),
            func.coalesce(
                func.avg(AdData.click_rate),
                case((func.sum(AdData.display_count) == 0, 0),
                     else_=func.cast(func.sum(AdData.click_count), Float) * 100.0 / func.cast(
                         func.sum(AdData.display_count), Float))
            ).label('avg_ctr'),
            func.avg(AdData.ecpm_after_deduct).label('avg_ecpm_deducted'),
            func.cast(func.sum(AdData.revenue_after_deduct), Float).label('total_revenue_deducted'),
            func.avg(AdData.ecpm_before_deduct).label('avg_ecpm_undeducted'),
            func.sum(AdData.revenue_before_deduct).label('total_revenue_undeducted'),
        )

        # 应用日期范围过滤
        date_condition = date_range_condition(AdData.date, start_date, end_date)
        if date_condition is not None:
            query = query.where(date_condition)

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        # 权限过滤
        query = query.join(Product, AdData.product_id == Product.id)
        if current_user.role != UserRole.ADMIN:
            if use_assignment_table:
                query = query.join(
                    ProductAssignment,
                    and_(
                        ProductAssignment.product_id == Product.id,
                        product_assignment_join_condition(
                            AdData.date,
                            ProductAssignment.start_date,
                            ProductAssignment.end_date
                        )
                    )
                )
                query = query.join(Client, ProductAssignment.client_id == Client.id)
            else:
                query = query.join(Client, Product.client_id == Client.id)
            query = query.where(Client.user_id == current_user.id)

        # 执行查询
        result = await self.db.execute(query)
        result = result.first()

        # 处理空结果
        if result is None:
            response_data = {
                "stats": [],
                "metrics": {"total_revenue": 0.0, "roi": 0.0}
            }
            await set_cached(cache_key, response_data, ttl=60)
            return response_data

        # ====== 上一周期日期范围（用于环比趋势） ======
        if period == "day":
            start_date_prev = start_date - timedelta(days=1)
            end_date_prev = end_date - timedelta(days=1)
        elif period == "week":
            start_date_prev = start_date - timedelta(days=7)
            end_date_prev = end_date - timedelta(days=7)
        elif period == "month":
            first_day_of_current_month = today.replace(day=1)
            start_date_prev = (first_day_of_current_month - timedelta(days=1)).replace(day=1)
            end_date_prev = first_day_of_current_month - timedelta(days=1)
        elif period == "last_month":
            first_day_of_last_month = start_date
            first_day_of_two_months_ago = (first_day_of_last_month - timedelta(days=1)).replace(day=1)
            end_date_prev = first_day_of_last_month - timedelta(days=1)
            start_date_prev = first_day_of_two_months_ago

        # ====== 上一周期聚合（字段与当前周期保持一致） ======
        query_prev = select(
            func.cast(func.sum(AdData.request_count), Float).label('total_requests'),
            func.sum(AdData.match_count).label('total_matches'),
            func.coalesce(
                func.avg(AdData.coverage_rate),
                case((func.sum(AdData.request_count) == 0, 0),
                     else_=func.cast(func.sum(AdData.match_count), Float) * 100.0 / func.cast(
                         func.sum(AdData.request_count), Float))
            ).label('avg_coverage'),
            func.sum(AdData.display_count).label('total_impressions'),
            func.coalesce(
                func.avg(AdData.display_rate),
                case((func.sum(AdData.match_count) == 0, 0),
                     else_=func.cast(func.sum(AdData.display_count), Float) * 100.0 / func.cast(
                         func.sum(AdData.match_count), Float))
            ).label('avg_display_rate'),
            func.sum(AdData.click_count).label('total_clicks'),
            func.coalesce(
                func.avg(AdData.click_rate),
                case((func.sum(AdData.display_count) == 0, 0),
                     else_=func.cast(func.sum(AdData.click_count), Float) * 100.0 / func.cast(
                         func.sum(AdData.display_count), Float))
            ).label('avg_ctr'),
            func.avg(AdData.ecpm_after_deduct).label('avg_ecpm_deducted'),
            func.cast(func.sum(AdData.revenue_after_deduct), Float).label('total_revenue_deducted'),
            func.avg(AdData.ecpm_before_deduct).label('avg_ecpm_undeducted'),
            func.sum(AdData.revenue_before_deduct).label('total_revenue_undeducted'),
        )

        date_condition_prev = date_range_condition(AdData.date, start_date_prev, end_date_prev)
        if date_condition_prev is not None:
            query_prev = query_prev.where(date_condition_prev)

        query_prev = query_prev.join(Product, AdData.product_id == Product.id)
        if current_user.role != UserRole.ADMIN:
            if use_assignment_table:
                query_prev = query_prev.join(
                    ProductAssignment,
                    and_(
                        ProductAssignment.product_id == Product.id,
                        product_assignment_join_condition(
                            AdData.date,
                            ProductAssignment.start_date,
                            ProductAssignment.end_date
                        )
                    )
                )
                query_prev = query_prev.join(Client, ProductAssignment.client_id == Client.id)
            else:
                query_prev = query_prev.join(Client, Product.client_id == Client.id)
            query_prev = query_prev.where(Client.user_id == current_user.id)

        result_prev = await self.db.execute(query_prev)
        result_prev = result_prev.first()

        # ====== 环比趋势：上一周期为 0 时，当前>0 记为 +100% ======
        def calculate_trend(current, previous):
            """环比涨跌幅（%）；上一周期为 0 时当前>0 记为 +100%。"""
            current = float(current or 0)
            previous = float(previous or 0)
            if previous == 0:
                return 100.0 if current > 0 else 0.0
            return round(((current - previous) / previous) * 100, 2)

        # 计算各指标趋势
        trend_requests = calculate_trend(
            result.total_requests if result else 0,
            result_prev.total_requests if result_prev else 0
        )
        trend_matches = calculate_trend(
            result.total_matches if result else 0,
            result_prev.total_matches if result_prev else 0
        )
        trend_coverage = calculate_trend(
            result.avg_coverage if result else 0,
            result_prev.avg_coverage if result_prev else 0
        )
        trend_impressions = calculate_trend(
            result.total_impressions if result else 0,
            result_prev.total_impressions if result_prev else 0
        )
        trend_display_rate = calculate_trend(
            result.avg_display_rate if result else 0,
            result_prev.avg_display_rate if result_prev else 0
        )
        trend_clicks = calculate_trend(
            result.total_clicks if result else 0,
            result_prev.total_clicks if result_prev else 0
        )
        trend_ctr = calculate_trend(
            result.avg_ctr if result else 0,
            result_prev.avg_ctr if result_prev else 0
        )
        trend_ecpm_deducted = calculate_trend(
            result.avg_ecpm_deducted if result else 0,
            result_prev.avg_ecpm_deducted if result_prev else 0
        )
        trend_revenue_deducted = calculate_trend(
            result.total_revenue_deducted if result else 0,
            result_prev.total_revenue_deducted if result_prev else 0
        )
        trend_ecpm_undeducted = calculate_trend(
            result.avg_ecpm_undeducted if result else 0,
            result_prev.avg_ecpm_undeducted if result_prev else 0
        )
        trend_revenue_undeducted = calculate_trend(
            result.total_revenue_undeducted if result else 0,
            result_prev.total_revenue_undeducted if result_prev else 0
        )

        # 构建基础指标
        base_stats = [
            {"id": "requests", "label": "请求数", "value": result.total_requests or 0, "trend": trend_requests,
             "precision": 0},
            {"id": "matches", "label": "匹配数", "value": result.total_matches or 0, "trend": trend_matches,
             "precision": 0},
            {"id": "coverage", "label": "覆盖率",
             "value": round(float(result.avg_coverage), 2) if (result and result.avg_coverage) else 0.0,
             "trend": trend_coverage, "precision": 2},
            {"id": "impressions", "label": "展示数", "value": result.total_impressions or 0 if result else 0,
             "trend": trend_impressions, "precision": 0},
            {"id": "display_rate", "label": "展示率",
             "value": round(float(result.avg_display_rate), 2) if (result and result.avg_display_rate) else 0.0,
             "trend": trend_display_rate, "precision": 2},
            {"id": "clicks", "label": "点击数", "value": result.total_clicks or 0 if result else 0,
             "trend": trend_clicks, "precision": 0},
            {"id": "ctr", "label": "点击率",
             "value": round(float(result.avg_ctr), 2) if (result and result.avg_ctr) else 0.0, "trend": trend_ctr,
             "precision": 2},
            {"id": "ecpm_deducted", "label": "eCPM(减扣后)",
             "value": round(float(result.avg_ecpm_deducted), 2) if (result and result.avg_ecpm_deducted) else 0.0,
             "trend": trend_ecpm_deducted, "precision": 2},
            {"id": "revenue_deducted", "label": "收益(减扣后)",
             "value": round(float(result.total_revenue_deducted), 2) if (
                     result and result.total_revenue_deducted) else 0.0, "trend": trend_revenue_deducted,
             "precision": 2}
        ]

        # 构建管理员指标
        admin_stats = [
            {"id": "ecpm_undeducted", "label": "eCPM(未减扣的)",
             "value": round(float(result.avg_ecpm_undeducted), 2) if (result and result.avg_ecpm_undeducted) else 0.0,
             "trend": trend_ecpm_undeducted, "precision": 2},
            {"id": "revenue_undeducted", "label": "收益(未减扣的)",
             "value": round(float(result.total_revenue_undeducted), 2) if (
                     result and result.total_revenue_undeducted) else 0.0, "trend": trend_revenue_undeducted,
             "precision": 2}
        ]

        # 根据角色组合指标
        is_admin = current_user.role == UserRole.ADMIN
        if is_admin:
            stats_data = base_stats + admin_stats
        else:
            stats_data = base_stats

        # ROI = 减扣后总收益 / 总请求数 × 1000（千次请求收益）
        total_revenue = round(float(result.total_revenue_deducted or 0), 2) if (
                result and result.total_revenue_deducted) else 0.0
        total_requests = float(result.total_requests or 0) if result else 0.0
        roi = round((total_revenue / total_requests * 1000) if total_requests > 0 else 0.0, 2)

        # 构建响应数据
        response_data = {
            "stats": stats_data,
            "metrics": {
                "total_revenue": total_revenue,
                "roi": roi
            }
        }

        # 缓存结果（缓存 1 分钟）
        await set_cached(cache_key, response_data, ttl=60)

        return response_data

    async def get_recent_ad_data(
            self,
            current_user: User,
            days: int = 7
    ) -> Dict[str, Any]:
        """
        获取最近 N 天各产品广告表现排行（按减扣后收益降序，最多 10 条）。

        异常时返回空列表而非抛错，避免仪表盘整页失败。

        Args:
            current_user: 当前用户
            days: 回溯天数，默认 7

        Returns:
            含 ads（产品列表）与 summary（汇总计数）的字典
        """
        try:
            # 查询最近N天的数据
            end_date = get_app_now_naive().date()
            start_date = end_date - timedelta(days=days)

            # 构建查询
            query = select(
                Product.name.label('product_name'),
                func.sum(AdData.display_count).label('impressions'),
                func.sum(AdData.click_count).label('clicks'),
                func.sum(AdData.revenue_after_deduct).label('revenue'),
                func.coalesce(
                    func.avg(AdData.click_rate),
                    func.avg(
                        case(
                            (func.sum(AdData.display_count) == 0, 0),
                            else_=func.cast(func.sum(AdData.click_count), Float) * 100.0 / func.cast(
                                func.sum(AdData.display_count), Float)
                        )
                    )
                ).label('avg_ctr')
            ).join(Product, AdData.product_id == Product.id)

            # 日期过滤
            date_condition = date_range_condition(AdData.date, start_date, end_date)
            if date_condition is not None:
                query = query.where(date_condition)

            # 检查是否使用产品分配历史表
            use_assignment_table = await check_use_assignment_table(self.db)

            # 根据用户角色过滤
            if current_user.role != UserRole.ADMIN:
                if use_assignment_table:
                    query = query.join(
                        ProductAssignment,
                        and_(
                            ProductAssignment.product_id == Product.id,
                            product_assignment_join_condition(
                                AdData.date,
                                ProductAssignment.start_date,
                                ProductAssignment.end_date
                            )
                        )
                    )
                    query = query.join(Client, ProductAssignment.client_id == Client.id)
                else:
                    query = query.join(Client, Product.client_id == Client.id)
                query = query.where(Client.user_id == current_user.id)

            # 分组和排序
            query = query.group_by(Product.id, Product.name).order_by(
                func.sum(AdData.revenue_after_deduct).desc()
            ).limit(10)

            # 执行查询
            result = await self.db.execute(query)
            ads_data = result.all()

            # 处理结果
            ads = []
            total_impressions = 0
            for row in ads_data:
                ctr = round(float(row.avg_ctr or 0), 2)
                revenue = round(float(row.revenue or 0), 2)
                ads.append({
                    "id": hash(row.product_name) % 1000000,
                    "name": row.product_name,
                    "impressions": int(row.impressions or 0),
                    "clicks": int(row.clicks or 0),
                    "status": "active",
                    "ctr": ctr,
                    "revenue": revenue
                })
                total_impressions += int(row.impressions or 0)

            return {
                "ads": ads,
                "summary": {
                    "total_ads": len(ads),
                    "active_ads": len(ads),
                    "total_impressions": total_impressions
                }
            }
        except Exception as e:
            logger.error(f"获取最近广告数据失败: {str(e)}", exc_info=True)
            # 返回空数据而不是抛出异常，保持健壮性
            return {
                "ads": [],
                "summary": {
                    "total_ads": 0,
                    "active_ads": 0,
                    "total_impressions": 0
                }
            }

    async def get_trend_data(
            self,
            period: str,
            current_user: User
    ) -> Dict[str, Any]:
        """
        获取趋势折线图时序数据。

        日视图按小时聚合（%H:00）；周/月/上月按自然日聚合。
        转化数序列固定为 0（AdData 表无 conversion_count 字段，占位供前端图例）。

        Args:
            period: 时间周期（day / week / month / last_month）
            current_user: 当前用户

        Returns:
            含 dates 与各指标 series 的字典
        """
        # ====== 缓存优化 ======
        cache_key = generate_cache_key("dashboard_trends", period, current_user.id)

        cached = await get_cached(cache_key)
        if cached:
            try:
                logger.debug(f"缓存命中: dashboard_trends, period={period}, user={current_user.id}")
                return cached
            except Exception as e:
                logger.warning(f"缓存数据格式错误，将重新查询: {e}")

        # 确定时间范围
        today = get_app_now_naive().date()
        if period == "day":
            start_date = today
            end_date = today
            date_format = "%H:00"
            date_trunc = func.date_format(AdData.date, "%H:00").label('hour')
        elif period == "week":
            start_date = today - timedelta(days=today.weekday())
            end_date = today
            date_format = "%Y-%m-%d"
            date_trunc = func.date_format(AdData.date, "%Y-%m-%d").label('day')
        elif period == "month":
            start_date = today.replace(day=1)
            end_date = today
            date_format = "%Y-%m-%d"
            date_trunc = func.date_format(AdData.date, "%Y-%m-%d").label('day')
        elif period == "last_month":
            first_day_of_current_month = today.replace(day=1)
            last_day_of_last_month = first_day_of_current_month - timedelta(days=1)
            start_date = last_day_of_last_month.replace(day=1)
            end_date = last_day_of_last_month
            date_format = "%Y-%m-%d"
            date_trunc = func.date_format(AdData.date, "%Y-%m-%d").label('day')
        else:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="无效的时间周期参数"
            )

        # 查询趋势数据
        columns = [
            date_trunc,
            func.sum(AdData.request_count).label('requests'),
            func.sum(AdData.match_count).label('matches'),
            func.sum(AdData.display_count).label('impressions'),
            func.sum(AdData.click_count).label('clicks')
        ]

        query = select(*columns)

        # 应用日期范围过滤
        date_condition = date_range_condition(AdData.date, start_date, end_date)
        if date_condition is not None:
            query = query.where(date_condition)

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        # 根据用户角色过滤数据
        query = query.join(Product, AdData.product_id == Product.id)
        if current_user.role != UserRole.ADMIN:
            if use_assignment_table:
                query = query.join(
                    ProductAssignment,
                    and_(
                        ProductAssignment.product_id == Product.id,
                        product_assignment_join_condition(
                            AdData.date,
                            ProductAssignment.start_date,
                            ProductAssignment.end_date
                        )
                    )
                )
                query = query.join(Client, ProductAssignment.client_id == Client.id)
            else:
                query = query.join(Client, Product.client_id == Client.id)
            query = query.where(Client.user_id == current_user.id)

        query = query.group_by(date_trunc).order_by(date_trunc)

        results = await self.db.execute(query)
        results = results.all()

        # 处理结果
        dates = []
        requests = []
        matches = []
        impressions = []
        clicks = []
        conversions = []

        for row in results:
            dates.append(row[0])
            requests.append(float(row[1] or 0))
            matches.append(float(row[2] or 0))
            impressions.append(float(row[3] or 0))
            clicks.append(float(row[4] or 0))
            conversions.append(0)  # AdData 模型没有 conversion_count 字段

        # 构建响应数据
        response_data = {
            "dates": dates,
            "series": [
                {"name": "请求数", "data": requests},
                {"name": "匹配数", "data": matches},
                {"name": "展示数", "data": impressions},
                {"name": "点击数", "data": clicks},
                {"name": "转化数", "data": conversions}
            ]
        }

        # 缓存结果（缓存 1 分钟）
        await set_cached(cache_key, response_data, ttl=60)

        return response_data
