"""
仪表盘统计API端点
提供数据统计和趋势分析功能，包括：
- 获取仪表盘统计数据（按天、周、月、上月）
- 获取趋势数据（按日期分组）
- 计算各种指标（覆盖率、展示率、点击率、ROI等）
- 管理员可查看所有数据，客户只能查看自己的数据
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, Float, text, and_
from datetime import datetime, timedelta
import logging
from app.core.database import get_db
from app.schemas.ad_data import DashboardStatsResponse, TrendDataResponse
from app.schemas.base import ResponseBaseSchema
from app.core.security import get_current_user
from app.models.models import User, AdData, Product, Client, UserRole, ProductAssignment
from app.core.cache import get_cached, set_cached, generate_cache_key
from app.core.query_utils import date_range_condition, product_assignment_join_condition, check_use_assignment_table

# 创建路由实例
router = APIRouter()


@router.get("/stats", response_model=ResponseBaseSchema[DashboardStatsResponse])
async def get_dashboard_stats(period: str = "week", db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    """
    获取仪表盘统计数据
    - 支持按天、周、月、上月统计
    - 管理员可查看所有数据
    - 客户只能查看自己的数据
    - 使用缓存提升性能（缓存 1 分钟）
    """
    logger = logging.getLogger(__name__)

    try:
        # ====== 缓存优化 ======
        # 生成缓存键（包含用户ID和周期）
        cache_key = generate_cache_key("dashboard_stats", period, current_user.id)
        
        # 尝试从缓存获取（缓存 1 分钟）
        cached = await get_cached(cache_key)
        if cached:
            try:
                logger.debug(f"缓存命中: dashboard_stats, period={period}, user={current_user.id}")
                return ResponseBaseSchema.success(data=DashboardStatsResponse(**cached))
            except Exception as e:
                logger.warning(f"缓存数据格式错误，将重新查询: {e}")
                # 缓存数据格式错误，继续执行查询
        
        # ====== 查询逻辑 ======
        # ====== 确定时间范围 ======
        # 根据period参数计算开始和结束日期
        from app.core.utils import get_app_now_naive
        today = get_app_now_naive().date()
        if period == "day":
            # 今天
            start_date = today
            end_date = today
        elif period == "week":
            # 本周（从周一开始到今天）
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period == "month":
            # 本月（从1号到今天）
            start_date = today.replace(day=1)
            end_date = today
        elif period == "last_month":
            # 上个月（从1号到最后一天）
            first_day_of_current_month = today.replace(day=1)
            last_day_of_last_month = first_day_of_current_month - timedelta(days=1)
            start_date = last_day_of_last_month.replace(day=1)
            end_date = last_day_of_last_month
        else:
            raise HTTPException(status_code=400,
                                detail=f"无效的时间周期参数: {period}，支持: day, week, month, last_month")

        # 构建查询
        query = select(
            func.cast(func.sum(AdData.request_count), Float).label('total_requests'),
            func.sum(AdData.match_count).label('total_matches'),
            # 使用数据库字段，如果为空则计算（使用 COALESCE 确保向后兼容）
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
        
        # 应用日期范围过滤（使用优化后的函数）
        date_condition = date_range_condition(AdData.date, start_date, end_date)
        if date_condition is not None:
            query = query.where(date_condition)

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(db)
        
        # ====== 权限过滤 ======
        # 根据用户角色过滤数据（数据隔离）
        query = query.join(Product, AdData.product_id == Product.id)
        if current_user.role != UserRole.ADMIN:
            # 客户只能查看自己的产品数据
            if use_assignment_table:
                # 使用产品分配历史表（优化：避免在 AdData.date 上使用 func.date()）
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
                # 旧的查询方式
                query = query.join(Client, Product.client_id == Client.id)
            query = query.where(Client.user_id == current_user.id)
        else:
            # 管理员查看所有数据，不需要额外过滤
            pass

        # 执行查询
        result = await db.execute(query)
        result = result.first()

        # 处理空结果
        if result is None:
            # 如果当前周期没有数据，返回空数据
            response_data = DashboardStatsResponse(
                stats=[],
                metrics={"total_revenue": 0.0, "roi": 0.0}
            )
            await set_cached(cache_key, response_data.model_dump(), ttl=60)
            return ResponseBaseSchema.success(data=response_data)
        
        # 确保所有数值类型统一为float
        total_revenue = float(result.total_revenue_deducted or 0)
        total_impressions = float(result.total_impressions or 0)

        # 计算上一周期日期范围
        if period == "day":
            start_date_prev = start_date - timedelta(days=1)
            end_date_prev = end_date - timedelta(days=1)
        elif period == "week":
            start_date_prev = start_date - timedelta(days=7)
            end_date_prev = end_date - timedelta(days=7)
        elif period == "month":
            # 上一周期为上个月
            first_day_of_current_month = today.replace(day=1)
            start_date_prev = (first_day_of_current_month - timedelta(days=1)).replace(day=1)
            end_date_prev = first_day_of_current_month - timedelta(days=1)
        elif period == "last_month":
            # 上一周期为上上个月
            first_day_of_last_month = start_date
            last_day_of_last_month = end_date
            first_day_of_two_months_ago = (first_day_of_last_month - timedelta(days=1)).replace(day=1)
            end_date_prev = first_day_of_last_month - timedelta(days=1)
            start_date_prev = first_day_of_two_months_ago

        # 查询上一周期数据
        query_prev = select(
            func.cast(func.sum(AdData.request_count), Float).label('total_requests'),
            func.sum(AdData.match_count).label('total_matches'),
            # 使用数据库字段，如果为空则计算（使用 COALESCE 确保向后兼容）
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
        
        # 应用日期范围过滤（使用优化后的函数）
        date_condition_prev = date_range_condition(AdData.date, start_date_prev, end_date_prev)
        if date_condition_prev is not None:
            query_prev = query_prev.where(date_condition_prev)

        # 应用相同的用户角色过滤
        query_prev = query_prev.join(Product, AdData.product_id == Product.id)
        if current_user.role != UserRole.ADMIN:
            if use_assignment_table:
                # 使用产品分配历史表（优化：避免在 AdData.date 上使用 func.date()）
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
                # 旧的查询方式
                query_prev = query_prev.join(Client, Product.client_id == Client.id)
            query_prev = query_prev.where(Client.user_id == current_user.id)
        else:
            # 管理员查看所有数据，不需要额外过滤
            pass

        # 执行上一周期查询
        result_prev = await db.execute(query_prev)
        result_prev = result_prev.first()

        # 计算趋势百分比 (当前-上期)/上期*100
        def calculate_trend(current, previous):
            current = float(current or 0)
            previous = float(previous or 0)
            if previous == 0:
                return 100.0 if current > 0 else 0.0
            return round(((current - previous) / previous) * 100, 2)

        # 计算各指标趋势（安全处理空值）
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
        # 合并指标并返回
        # 根据角色组合指标
        is_admin = current_user.role == UserRole.ADMIN
        if is_admin:
            stats_data = base_stats + admin_stats
        else:
            stats_data = base_stats

        # 计算ROI（收益/请求数*1000）
        total_revenue = round(float(result.total_revenue_deducted or 0), 2) if (
                    result and result.total_revenue_deducted) else 0.0
        total_requests = float(result.total_requests or 0) if result else 0.0
        roi = round((total_revenue / total_requests * 1000) if total_requests > 0 else 0.0, 2)

        # 构建响应数据
        response_data = DashboardStatsResponse(
            stats=stats_data,
            metrics={
                "total_revenue": total_revenue,
                "roi": roi
            }
        )
        
        # 缓存结果（缓存 1 分钟）
        await set_cached(cache_key, response_data.model_dump(), ttl=60)
        
        return ResponseBaseSchema.success(data=response_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取仪表盘统计数据失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取统计数据失败: {str(e)}"
        )


@router.get("/recent-ads", response_model=ResponseBaseSchema[dict])
async def get_recent_ad_data(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取最近的广告数据
    - 返回最近7天的广告数据汇总
    - 管理员可查看所有数据
    - 客户只能查看自己的数据
    """
    try:
        # 查询最近7天的数据
        from app.core.utils import get_app_now_naive
        end_date = get_app_now_naive().date()
        start_date = end_date - timedelta(days=7)

        # 构建查询
        query = select(
            Product.name.label('product_name'),
            func.sum(AdData.display_count).label('impressions'),
            func.sum(AdData.click_count).label('clicks'),
            func.sum(AdData.revenue_after_deduct).label('revenue'),
            # 使用数据库字段，如果为空则计算（使用 COALESCE 确保向后兼容）
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

        # 日期过滤（使用优化后的函数）
        date_condition = date_range_condition(AdData.date, start_date, end_date)
        if date_condition is not None:
            query = query.where(date_condition)

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(db)
        
        # 根据用户角色过滤（Product已在第364行JOIN，这里不需要重复）
        if current_user.role != UserRole.ADMIN:
            if use_assignment_table:
                # 使用产品分配历史表（优化：避免在 AdData.date 上使用 func.date()）
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
                # 旧的查询方式
                query = query.join(Client, Product.client_id == Client.id)
            query = query.where(Client.user_id == current_user.id)

        # 分组和排序
        query = query.group_by(Product.id, Product.name).order_by(func.sum(AdData.revenue_after_deduct).desc()).limit(
            10)

        # 执行查询
        result = await db.execute(query)
        ads_data = result.all()

        # 处理结果
        ads = []
        total_impressions = 0
        for row in ads_data:
            ctr = round(float(row.avg_ctr or 0), 2)
            revenue = round(float(row.revenue or 0), 2)
            ads.append({
                "id": hash(row.product_name) % 1000000,  # 生成简单ID
                "name": row.product_name,
                "impressions": int(row.impressions or 0),
                "clicks": int(row.clicks or 0),
                "status": "active",
                "ctr": ctr,
                "revenue": revenue
            })
            total_impressions += int(row.impressions or 0)

        return ResponseBaseSchema.success(data={
            "ads": ads,
            "summary": {
                "total_ads": len(ads),
                "active_ads": len(ads),  # 简化处理，实际应该根据状态判断
                "total_impressions": total_impressions
            }
        })
    except Exception as e:
        logger.error(f"获取最近广告数据失败: {str(e)}")
        # 返回空数据而不是抛出异常，保持健壮性
        return ResponseBaseSchema.success(data={
            "ads": [],
            "summary": {
                "total_ads": 0,
                "active_ads": 0,
                "total_impressions": 0
            }
        })


@router.get("/trends", response_model=ResponseBaseSchema[TrendDataResponse])
async def get_trend_data(period: str = "week", db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """
    获取趋势数据
    - 支持按天、周、月、上月统计
    - 管理员可查看所有数据
    - 客户只能查看自己的数据
    - 使用缓存提升性能（缓存 1 分钟）
    """
    logger = logging.getLogger(__name__)

    try:
        # ====== 缓存优化 ======
        # 生成缓存键（包含用户ID和周期）
        cache_key = generate_cache_key("dashboard_trends", period, current_user.id)
        
        # 尝试从缓存获取（缓存 1 分钟）
        cached = await get_cached(cache_key)
        if cached:
            try:
                logger.debug(f"缓存命中: dashboard_trends, period={period}, user={current_user.id}")
                return ResponseBaseSchema.success(data=TrendDataResponse(**cached))
            except Exception as e:
                logger.warning(f"缓存数据格式错误，将重新查询: {e}")
                # 缓存数据格式错误，继续执行查询
        
        # 确定时间范围
        from app.core.utils import get_app_now_naive
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
            # 计算上个月的第一天和最后一天
            first_day_of_current_month = today.replace(day=1)
            last_day_of_last_month = first_day_of_current_month - timedelta(days=1)
            start_date = last_day_of_last_month.replace(day=1)
            end_date = last_day_of_last_month
            date_format = "%Y-%m-%d"
            date_trunc = func.date_format(AdData.date, "%Y-%m-%d").label('day')
        else:
            raise HTTPException(status_code=400, detail="无效的时间周期参数")

        # 查询趋势数据
        # 动态构建查询列
        columns = [
            date_trunc,
            func.sum(AdData.request_count).label('requests'),
            func.sum(AdData.match_count).label('matches'),
            func.sum(AdData.display_count).label('impressions'),
            func.sum(AdData.click_count).label('clicks')
        ]

        query = select(*columns)
        
        # 应用日期范围过滤（使用优化后的函数）
        date_condition = date_range_condition(AdData.date, start_date, end_date)
        if date_condition is not None:
            query = query.where(date_condition)

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(db)
        
        # 根据用户角色过滤数据
        query = query.join(Product, AdData.product_id == Product.id)
        if current_user.role != UserRole.ADMIN:
            if use_assignment_table:
                # 使用产品分配历史表（优化：避免在 AdData.date 上使用 func.date()）
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
                # 旧的查询方式
                query = query.join(Client, Product.client_id == Client.id)
            query = query.where(Client.user_id == current_user.id)

        query = query.group_by(date_trunc).order_by(date_trunc)

        results = await db.execute(query)
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
            # conversions 字段：当前 AdData 模型没有 conversion_count 字段，始终为 0
            conversions.append(0)

        # 构建响应数据
        response_data = TrendDataResponse(
            dates=dates,
            series=[
                {"name": "请求数", "data": requests},
                {"name": "匹配数", "data": matches},
                {"name": "展示数", "data": impressions},
                {"name": "点击数", "data": clicks},
                {"name": "转化数", "data": conversions}
            ]
        )
        
        # 缓存结果（缓存 1 分钟）
        await set_cached(cache_key, response_data.model_dump(), ttl=60)
        
        return ResponseBaseSchema.success(data=response_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取趋势数据失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取趋势数据失败: {str(e)}"
        )
