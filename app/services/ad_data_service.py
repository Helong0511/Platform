"""
广告数据服务层
封装广告数据的业务逻辑
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import date, datetime, timedelta
from calendar import monthrange
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, text, literal_column, case, Float, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import load_only

from app.models.models import (
    AdData, Product, Client, User, UserRole, ProductAssignment, CountryInfo
)
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception, handle_integrity_error
from app.core.errors import ErrorCode
from app.core.security import is_admin
from app.core.cache import get_cached, set_cached, generate_cache_key
from app.core.query_utils import (
    product_assignment_join_condition,
    check_use_assignment_table,
    join_country_info as join_country_info_util,
    apply_date_range_filter,
    date_range_condition
)
from app.core.utils import (
    unpack_ad_data_query_result,
    calculate_coverage_rate,
    calculate_display_rate,
    calculate_click_rate
)
from app.core.country_code import find_country_code_by_any_format, resolve_country_name
from app.core.constants import PERCENTAGE_MULTIPLIER, ECPM_MULTIPLIER
import logging

logger = logging.getLogger(__name__)


def join_country_info_for_ad_data(query):
    """
    辅助函数：统一处理 CountryInfo 的 JOIN，解决排序规则冲突问题
    传入 AdData.country_code 列
    """
    return join_country_info_util(query, AdData.country_code)


class AdDataService(BaseService[AdData]):
    """广告数据服务"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, AdData)

    def require_admin(self, current_user: User):
        """检查用户是否为管理员，如果不是则抛出权限不足异常"""
        if current_user.role != UserRole.ADMIN:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="只有管理员才能执行此操作"
            )

    async def get_ad_data_by_id(
        self,
        data_id: int,
        current_user: User
    ) -> Tuple[AdData, Product, Client, User, Optional[ProductAssignment], Optional[CountryInfo]]:
        """
        根据ID获取广告数据详情（包含关联信息）

        Args:
            data_id: 广告数据ID
            current_user: 当前用户

        Returns:
            Tuple: (ad_data, product, client, user, assignment_or_none, country_info_or_none)
        """

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        if use_assignment_table:
            # 使用产品分配历史表
            query = select(AdData, Product, Client, User, ProductAssignment, CountryInfo)
            query = query.options(load_only(
                Client.id, Client.user_id, Client.company_name, Client.contact_person,
                Client.phone, Client.address, Client.is_active, Client.created_at, Client.updated_at
            ))
            query = query.join(Product, AdData.product_id == Product.id)
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
            query = select(AdData, Product, Client, User, CountryInfo)
            query = query.options(load_only(
                Client.id, Client.user_id, Client.company_name, Client.contact_person,
                Client.phone, Client.address, Client.is_active, Client.created_at, Client.updated_at
            ))
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)

        query = query.join(User, Client.user_id == User.id)
        query = join_country_info_for_ad_data(query)  # 左关联国家信息
        query = query.where(AdData.id == data_id)
        # 只显示激活状态的产品（is_active = True）
        query = query.where(Product.is_active == True)

        result = await self.db.execute(query)
        data = result.unique().first()

        if not data:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据ID {data_id} 不存在"
            )

        # 使用统一的查询结果解包函数
        try:
            ad_data, product, client, user, assignment, country_info = unpack_ad_data_query_result(
                data, use_assignment_table
            )
        except (ValueError, Exception) as e:
            logger.error(f"解构数据失败: {str(e)}, data={data}")
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据ID {data_id} 数据格式错误"
            )

        # 验证关联数据完整性
        if not product:
            raise_api_exception(
                ErrorCode.AD_DATA_PRODUCT_NOT_FOUND,
                detail=f"广告数据关联的产品ID {ad_data.product_id} 不存在"
            )
        if not client:
            raise_api_exception(
                ErrorCode.CLIENT_NOT_FOUND,
                detail=f"广告数据关联的客户ID {product.client_id if product else '未知'} 不存在"
            )
        if not user:
            raise_api_exception(
                ErrorCode.USER_NOT_FOUND,
                detail=f"广告数据关联的用户ID {client.user_id if client else '未知'} 不存在"
            )

        # 权限检查
        if not is_admin(current_user) and client.user_id != current_user.id:
            raise_api_exception(
                ErrorCode.AD_DATA_NO_PERMISSION,
                detail=f"您没有权限访问广告数据ID {data_id}，该数据不属于您的客户账户"
            )

        return ad_data, product, client, user, assignment, country_info

    async def update_ad_data(
        self,
        data_id: int,
        update_data: Dict[str, Any],
        current_user: User
    ) -> AdData:
        """
        更新广告数据（包含完整的业务逻辑：验证、唯一性检查、比率计算、错误处理）

        Args:
            data_id: 广告数据ID
            update_data: 更新的数据字典
            current_user: 当前用户

        Returns:
            AdData: 更新后的广告数据对象
        """

        # 权限检查
        if not is_admin(current_user):
            raise_api_exception(
                ErrorCode.AD_DATA_UPDATE_FORBIDDEN,
                detail="仅管理员可以更新广告数据。客户用户没有更新权限"
            )

        # 查询广告数据
        query = select(AdData).where(AdData.id == data_id)
        result = await self.db.execute(query)
        ad_data = result.scalars().first()

        if not ad_data:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据ID {data_id} 不存在"
            )

        # 定义允许更新的字段白名单
        allowed_fields = {
            'product_id', 'country_code', 'request_count', 'match_count', 'display_count',
            'click_count', 'viewability_rate', 'ecpm_after_deduct', 'ecpm_before_deduct',
            'revenue_after_deduct', 'revenue_before_deduct'
        }

        # 过滤不允许更新的字段
        filtered_update_data = {
            k: v for k, v in update_data.items()
            if k in allowed_fields
        }

        # 如果更新product_id，验证产品是否存在
        if 'product_id' in filtered_update_data:
            product_id = filtered_update_data['product_id']
            product_result = await self.db.execute(
                select(Product).where(Product.id == product_id)
            )
            product = product_result.scalars().first()
            if not product:
                raise_api_exception(
                    ErrorCode.AD_DATA_PRODUCT_NOT_FOUND,
                    detail=f"指定的产品ID {product_id} 不存在，请确认产品是否存在"
                )

        # 如果更新country_code，验证国家代码是否有效
        if 'country_code' in filtered_update_data:
            country_input = filtered_update_data['country_code']
            if country_input:
                # 支持多种格式：alpha_2_code、alpha_3_code、numeric_code、country_name_en、country_name_zh、official_name_en、official_name_zh
                found_country_code = await find_country_code_by_any_format(self.db, country_input)
                if found_country_code:
                    filtered_update_data['country_code'] = found_country_code
                else:
                    raise_api_exception(
                        ErrorCode.OPERATION_FAILED,
                        detail=f"无法识别国家代码格式: {country_input}。请使用有效的国家代码（如 'US'、'USA'、'840'、'United States of America' 或 '美国'）"
                    )
            else:
                # 如果传入空字符串或 None，设置为 'ZZ'（全部区域）
                filtered_update_data['country_code'] = 'ZZ'

        # 检查唯一性约束：如果更新了 product_id 或 country_code，需要检查是否会违反唯一性约束
        # 唯一性约束：同一日期、产品ID和国家代码只能有一条记录
        if 'product_id' in filtered_update_data or 'country_code' in filtered_update_data:
            # 确定更新后的值
            new_product_id = filtered_update_data.get('product_id', ad_data.product_id)
            new_country_code = filtered_update_data.get('country_code', ad_data.country_code)
            
            # 构建日期范围查询（AdData.date 是 DateTime 类型）
            if isinstance(ad_data.date, datetime):
                date_start = ad_data.date.replace(hour=0, minute=0, second=0, microsecond=0)
                date_end = ad_data.date.replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                date_start = datetime.combine(ad_data.date, datetime.min.time())
                date_end = datetime.combine(ad_data.date, datetime.max.time())
            
            # 查询是否存在相同的记录（排除当前记录）
            # 国家代码匹配逻辑：如果新国家代码是'ZZ'，匹配'ZZ'或NULL
            if new_country_code == "ZZ":
                country_condition = or_(
                    AdData.country_code == "ZZ",
                    AdData.country_code.is_(None)
                )
            else:
                country_condition = AdData.country_code == new_country_code
            
            existing_query = select(AdData).where(
                AdData.id != ad_data.id,  # 排除当前记录
                AdData.date >= date_start,
                AdData.date <= date_end,
                AdData.product_id == new_product_id,
                country_condition
            )
            existing_result = await self.db.execute(existing_query)
            existing_data = existing_result.scalars().first()
            
            if existing_data:
                # 存在冲突记录，获取详细信息
                existing_country_name = "全部区域"
                if existing_data.country_code and existing_data.country_code != "ZZ":
                    country_info_result = await self.db.execute(
                        select(CountryInfo).where(CountryInfo.alpha_2_code == existing_data.country_code)
                    )
                    country_info = country_info_result.scalar_one_or_none()
                    if country_info:
                        existing_country_name = country_info.country_name_zh
                
                product_result = await self.db.execute(select(Product).where(Product.id == new_product_id))
                product = product_result.scalar_one_or_none()
                product_name = product.name if product else f"产品ID {new_product_id}"
                
                # 获取日期值用于错误提示
                date_value = ad_data.date
                if isinstance(date_value, datetime):
                    date_value = date_value.date()
                elif hasattr(date_value, 'date'):
                    date_value = date_value.date()
                
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"更新失败：已存在相同的记录（日期={date_value}，产品={product_name}，国家={existing_country_name}）。请先删除或修改冲突的记录（ID: {existing_data.id}）"
                )

        # 更新字段
        for key, value in filtered_update_data.items():
            if key in allowed_fields and hasattr(ad_data, key):
                setattr(ad_data, key, value)
        
        # 如果基础数据字段有变化，重新计算比率字段
        if any(key in filtered_update_data for key in ['request_count', 'match_count', 'display_count', 'click_count']):
            ad_data.calculate_rates()

        # 保存更新
        try:
            self.db.add(ad_data)
            # 刷新对象以触发约束检查（在自动提交之前）
            await self.db.flush()
            await self.db.refresh(ad_data)
        except Exception as e:
            error_msg = str(e)
            
            # 检查是否是 IntegrityError（唯一性约束冲突）
            if isinstance(e, IntegrityError):
                # 提取冲突信息
                conflict_info = ""
                if "Duplicate entry" in error_msg:
                    # 从错误信息中提取冲突的键值
                    match = re.search(r"Duplicate entry '([^']+)'", error_msg)
                    if match:
                        conflict_info = f"冲突的键值: {match.group(1)}"
                
                # 获取更新后的值用于错误提示
                new_product_id = filtered_update_data.get('product_id', ad_data.product_id)
                new_country_code = filtered_update_data.get('country_code', ad_data.country_code)
                
                # 获取产品名称
                product_result = await self.db.execute(select(Product).where(Product.id == new_product_id))
                product = product_result.scalar_one_or_none()
                product_name = product.name if product else f"产品ID {new_product_id}"
                
                # 获取国家名称
                country_name = "全部区域"
                if new_country_code and new_country_code != "ZZ":
                    country_info_result = await self.db.execute(
                        select(CountryInfo).where(CountryInfo.alpha_2_code == new_country_code)
                    )
                    country_info = country_info_result.scalar_one_or_none()
                    if country_info:
                        country_name = country_info.country_name_zh
                
                # 获取日期
                date_value = ad_data.date
                if isinstance(date_value, datetime):
                    date_value = date_value.date()
                elif hasattr(date_value, 'date'):
                    date_value = date_value.date()
                
                # 使用统一的 IntegrityError 处理函数
                handle_integrity_error(
                    error=e,
                    constraint_name="uq_ad_data_date_product_country",
                    custom_message=(
                        f"更新失败：已存在相同的记录（日期={date_value}，产品={product_name}，国家={country_name}）。"
                        f"同一日期、产品和国家的组合必须唯一，请先删除或修改冲突的记录。{conflict_info}"
                    ),
                    log_context="Update ad data"
                )
            
            logger.error(f"更新广告数据失败: {error_msg}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新广告数据失败：{error_msg}。请检查数据格式或联系管理员"
            )

        logger.info(f"广告数据已更新: ID={data_id}")
        return ad_data

    async def delete_ad_data(
        self,
        data_id: int,
        current_user: User
    ) -> None:
        """
        删除广告数据

        Args:
            data_id: 广告数据ID
            current_user: 当前用户
        """
        # 权限检查
        if not is_admin(current_user):
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="仅管理员可以删除广告数据"
            )

        # 查询广告数据
        ad_data = await self.get_by_id(data_id)

        if not ad_data:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据ID {data_id} 不存在"
            )

        # 删除广告数据
        await self.db.delete(ad_data)
        await self.db.commit()

        logger.info(f"广告数据已删除: ID={data_id}")

    async def get_clients_with_data(
        self,
        current_user: User,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        获取有广告数据的客户列表（用于下拉选择）

        Args:
            current_user: 当前用户
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            List[Dict]: 客户列表
        """
        # 缓存优化
        cache_key = generate_cache_key("clients_with_data", current_user.id, start_date, end_date)
        cached = await get_cached(cache_key)
        if cached:
            return cached.get("data", [])

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        # 构建基础查询 - 返回 Client.id 和 User.full_name
        if use_assignment_table:
            # 使用产品分配历史表：从AdData开始，明确指定FROM子句
            query = select(func.distinct(Client.id), User.full_name, User.username, Client.user_id)
            query = query.select_from(AdData)
            query = query.join(Product, AdData.product_id == Product.id)
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
            # 旧的查询方式：从Client开始
            query = select(func.distinct(Client.id), User.full_name, User.username, Client.user_id)
            query = query.select_from(Client)
            query = query.join(Product, Product.client_id == Client.id)
            query = query.join(AdData, AdData.product_id == Product.id)

        query = query.join(User, Client.user_id == User.id)

        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)

        # 权限过滤
        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)

        # 日期范围过滤：使用统一的日期范围过滤函数，如果没有指定日期范围，默认查询当前月的数据
        query = apply_date_range_filter(
            query,
            AdData.date,
            start_date,
            end_date,
            default_to_current_month=True
        )

        # 执行查询
        result = await self.db.execute(query)
        clients_data = result.all()

        # 转换为响应格式 - 使用 full_name，如果没有则使用 username
        clients_list = []
        for client_id, full_name, username, user_id in clients_data:
            clients_list.append({
                "id": client_id,
                "full_name": full_name or username or "未知客户",
                "user_id": user_id
            })

        # 按用户名称排序
        clients_list.sort(key=lambda x: x["full_name"])

        # 缓存结果（缓存 5 分钟）
        await set_cached(cache_key, {"data": clients_list, "count": len(clients_list)}, ttl=300)

        return clients_list

    async def get_countries_with_data(
        self,
        current_user: User,
        client_id: Optional[int] = None,
        product_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        获取有广告数据的国家列表（用于下拉选择）

        Args:
            current_user: 当前用户
            client_id: 客户ID过滤
            product_id: 产品ID过滤
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            List[Dict]: 国家列表
        """
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        # 构建基础查询 - 返回 distinct 的 country_code
        if use_assignment_table:
            query = select(func.distinct(AdData.country_code), CountryInfo.country_name_zh)
            query = query.select_from(AdData)
            query = query.join(Product, AdData.product_id == Product.id)
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
            query = select(func.distinct(AdData.country_code), CountryInfo.country_name_zh)
            query = query.select_from(AdData)
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)

        query = join_country_info_for_ad_data(query)  # 左关联国家信息

        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)

        # 权限过滤
        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        else:
            if client_id:
                query = query.where(Client.id == client_id)

        # 产品ID过滤
        if product_id:
            query = query.where(AdData.product_id == product_id)

        # 日期范围过滤：使用统一的日期范围过滤函数，如果没有指定日期范围，默认查询当前月的数据
        query = apply_date_range_filter(
            query,
            AdData.date,
            start_date,
            end_date,
            default_to_current_month=True
        )

        # 过滤掉空的国家代码
        query = query.where(
            and_(
                AdData.country_code.isnot(None),
                AdData.country_code != ''
            )
        )

        # 执行查询
        result = await self.db.execute(query)
        countries_data = result.all()

        # 转换为响应格式
        countries_list = []
        for country_code, country_name_zh in countries_data:
            if not country_code:
                continue

            # 处理特殊国家代码：使用统一的国家名称解析函数
            display_name = resolve_country_name(
                None,  # 没有 CountryInfo 对象，只有代码
                country_code,
                default_unknown='未知区域',
                default_all='全部区域'
            ) or country_name_zh or country_code

            countries_list.append({
                "code": country_code,
                "name_zh": display_name
            })

        # 按国家名称排序
        countries_list.sort(key=lambda x: x["name_zh"])

        return countries_list

    async def get_products_with_data(
        self,
        current_user: User,
        client_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        获取有广告数据的产品列表（用于下拉选择）

        Args:
            current_user: 当前用户
            client_id: 客户ID过滤
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            List[Dict]: 产品列表
        """
        # 缓存优化
        cache_key = generate_cache_key("products_with_data", current_user.id, client_id, start_date, end_date)
        cached = await get_cached(cache_key)
        if cached:
            return cached.get("data", [])

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        # 构建基础查询
        if use_assignment_table:
            # 使用产品分配历史表
            query = select(func.distinct(Product.id), Product.name, Product.client_id)
            query = query.join(AdData, AdData.product_id == Product.id)
            # 关联产品分配历史表：根据广告数据的日期匹配正确的分配记录
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
            query = select(func.distinct(Product.id), Product.name, Product.client_id)
            query = query.join(Client, Product.client_id == Client.id)
            query = query.join(AdData, AdData.product_id == Product.id)

        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)

        # 权限过滤
        if not is_admin(current_user):
            # 客户用户：通过 Client.user_id 过滤，只能看到自己的产品
            query = query.where(Client.user_id == current_user.id)
        elif client_id:
            # 管理员按客户ID过滤：如果指定了客户，只返回该客户的产品
            query = query.where(Client.id == client_id)

        # 日期范围过滤：使用统一的日期范围过滤函数，如果没有指定日期范围，默认查询当前月的数据
        query = apply_date_range_filter(
            query,
            AdData.date,
            start_date,
            end_date,
            default_to_current_month=True
        )

        # 执行查询
        result = await self.db.execute(query)
        products_data = result.all()

        # 转换为响应格式
        products_list = []
        for product_id, product_name, product_client_id in products_data:
            products_list.append({
                "id": product_id,
                "name": product_name or "未知产品",
                "client_id": product_client_id
            })

        # 按产品 id 倒序排序（从大到小）
        products_list.sort(key=lambda x: x["id"], reverse=True)

        # 缓存结果（缓存 5 分钟）
        await set_cached(cache_key, {"data": products_list, "count": len(products_list)}, ttl=300)

        return products_list

    async def get_date_range(
        self,
        current_user: User,
        client_id: Optional[int] = None
    ) -> Dict[str, Optional[str]]:
        """
        获取广告数据的日期范围（最早日期和最新日期）

        Args:
            current_user: 当前用户
            client_id: 客户ID过滤

        Returns:
            Dict: 包含 min_date 和 max_date 的字典
        """
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        # 构建查询：获取日期的最小值和最大值
        if use_assignment_table:
            # 使用产品分配历史表
            query = select(
                func.min(func.date(AdData.date)).label("min_date"),
                func.max(func.date(AdData.date)).label("max_date")
            )
            query = query.join(Product, AdData.product_id == Product.id)

            end_date_with_default = func.coalesce(
                func.date_add(ProductAssignment.end_date, text("INTERVAL 1 DAY")),
                literal_column("'2099-12-31'")
            )
            query = query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    AdData.date >= ProductAssignment.start_date,
                    AdData.date < end_date_with_default
                )
            )
            query = query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            # 旧的查询方式
            query = select(
                func.min(func.date(AdData.date)).label("min_date"),
                func.max(func.date(AdData.date)).label("max_date")
            )
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)

        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)

        # 权限过滤
        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        else:
            if client_id:
                query = query.where(Client.id == client_id)

        # 执行查询
        result = await self.db.execute(query)
        row = result.first()

        if row and row.min_date and row.max_date:
            return {
                "min_date": row.min_date.isoformat() if hasattr(row.min_date, 'isoformat') else str(row.min_date),
                "max_date": row.max_date.isoformat() if hasattr(row.max_date, 'isoformat') else str(row.max_date)
            }
        else:
            # 没有数据
            return {
                "min_date": None,
                "max_date": None
            }

    async def batch_delete_ad_data(
        self,
        data_ids: List[int],
        current_user: User
    ) -> int:
        """
        批量删除广告数据

        Args:
            data_ids: 广告数据ID列表
            current_user: 当前用户

        Returns:
            int: 实际删除的记录数
        """
        if not data_ids or len(data_ids) == 0:
            raise_api_exception(
                ErrorCode.AD_DATA_EMPTY_SELECTION,
                detail="请选择要删除的广告数据。数据ID列表不能为空"
            )

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        # 获取所有广告数据及关联的产品和客户信息
        if use_assignment_table:
            # 使用产品分配历史表
            query = select(AdData, Product, Client, ProductAssignment).join(
                Product, AdData.product_id == Product.id
            ).join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    product_assignment_join_condition(
                        AdData.date,
                        ProductAssignment.start_date,
                        ProductAssignment.end_date
                    )
                )
            ).join(
                Client, ProductAssignment.client_id == Client.id
            ).where(AdData.id.in_(data_ids))
        else:
            # 旧的查询方式
            query = select(AdData, Product, Client).join(
                Product, AdData.product_id == Product.id
            ).join(
                Client, Product.client_id == Client.id
            ).where(AdData.id.in_(data_ids))

        result = await self.db.execute(query)
        all_data = result.unique().all()

        if not all_data:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"未找到要删除的广告数据。请确认数据ID是否正确"
            )

        # 权限检查和过滤
        deletable_data = []
        if not is_admin(current_user):
            # 客户只能删除自己的广告数据
            for data_row in all_data:
                if use_assignment_table:
                    ad_data, product, client, product_assignment = data_row
                else:
                    ad_data, product, client = data_row

                if client.user_id == current_user.id:
                    deletable_data.append(ad_data)
                else:
                    logger.warning(f"用户 {current_user.username} 尝试删除无权访问的数据 ID: {ad_data.id}")
        else:
            # 管理员可以删除所有数据
            if use_assignment_table:
                deletable_data = [ad_data for ad_data, _, _, _ in all_data]
            else:
                deletable_data = [ad_data for ad_data, _, _ in all_data]

        if not deletable_data:
            raise_api_exception(
                ErrorCode.AD_DATA_DELETE_FORBIDDEN,
                detail="您没有权限删除选中的广告数据。部分数据不属于您的客户账户"
            )

        # 批量删除（使用批量操作优化性能）
        deleted_count = 0
        try:
            # 获取要删除的数据ID列表
            deletable_ids = [ad_data.id for ad_data in deletable_data]

            # 使用批量删除语句（更高效）
            delete_stmt = delete(AdData).where(AdData.id.in_(deletable_ids))
            result = await self.db.execute(delete_stmt)
            deleted_count = result.rowcount

            await self.db.commit()
            logger.info(f"Batch deleted {deleted_count} ad data records by {current_user.username}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"批量删除广告数据失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"批量删除广告数据失败：{str(e)}。请稍后重试或联系管理员"
            )

        return deleted_count

    async def get_ad_data_summary(
        self,
        current_user: User,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        client_id: Optional[int] = None,
        product_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        获取广告数据汇总统计

        Args:
            current_user: 当前用户
            start_date: 开始日期
            end_date: 结束日期
            client_id: 客户ID过滤
            product_id: 产品ID过滤

        Returns:
            Dict: 汇总统计数据
        """
        # 缓存优化
        cache_key = generate_cache_key("ad_data_summary", current_user.id, start_date, end_date, client_id, product_id)
        cached = await get_cached(cache_key)
        if cached:
            return cached

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        # 构建主查询：汇总所有指标
        # 使用数据库字段计算平均值，如果字段为空则使用计算值（使用 COALESCE 确保向后兼容）
        query = select(
            func.sum(AdData.request_count).label("total_requests"),
            func.sum(AdData.match_count).label("total_matches"),
            func.sum(AdData.display_count).label("total_displays"),
            func.sum(AdData.click_count).label("total_clicks"),
            func.sum(AdData.ecpm_after_deduct).label("total_ecpm_after"),
            func.sum(AdData.revenue_after_deduct).label("total_revenue_after"),
            func.coalesce(
                func.avg(AdData.coverage_rate),
                case((func.sum(AdData.request_count) == 0, 0),
                     else_=func.cast(func.sum(AdData.match_count), Float) * 100.0 / func.cast(
                         func.sum(AdData.request_count), Float))
            ).label("avg_coverage_rate"),
            func.coalesce(
                func.avg(AdData.display_rate),
                case((func.sum(AdData.match_count) == 0, 0),
                     else_=func.cast(func.sum(AdData.display_count), Float) * 100.0 / func.cast(
                         func.sum(AdData.match_count), Float))
            ).label("avg_display_rate"),
            func.coalesce(
                func.avg(AdData.click_rate),
                case((func.sum(AdData.display_count) == 0, 0),
                     else_=func.cast(func.sum(AdData.click_count), Float) * 100.0 / func.cast(
                         func.sum(AdData.display_count), Float))
            ).label("avg_click_rate")
        )
        query = query.join(Product, AdData.product_id == Product.id)

        # 使用产品分配历史表
        if use_assignment_table:
            # 优化：避免在 AdData.date 列上使用 func.date()，改为直接比较 DATE 和 DATETIME
            # MySQL 会自动将 DATE 转换为 DATETIME（时间部分为 00:00:00）进行比较
            # 为了包含整天的数据，结束日期需要加 1 天
            query = query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    # MySQL 会自动将 DATE 转换为 DATETIME，所以可以直接比较
                    AdData.date >= ProductAssignment.start_date,
                    or_(
                        ProductAssignment.end_date.is_(None),
                        # 使用 DATE_ADD 确保包含整天的数据（end_date 23:59:59.999999）
                        AdData.date < func.date_add(ProductAssignment.end_date, text("INTERVAL 1 DAY"))
                    )
                )
            )
            query = query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            query = query.join(Client, Product.client_id == Client.id)

        # 根据用户角色设置权限过滤
        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        else:
            if client_id:
                query = query.where(Client.id == client_id)

        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)

        # 产品ID过滤
        if product_id:
            query = query.where(AdData.product_id == product_id)

        # 日期范围过滤
        query = apply_date_range_filter(
            query,
            AdData.date,
            start_date,
            end_date,
            default_to_current_month=True
        )

        # 执行汇总查询
        result = await self.db.execute(query)
        summary = result.first()

        # 处理空结果
        if summary is None:
            total_requests = 0
            total_matches = 0
            total_displays = 0
            total_clicks = 0
            total_ecpm_after = 0
            total_revenue_after = 0
            avg_coverage_rate = 0
            avg_display_rate = 0
            avg_click_rate = 0
        else:
            total_requests = summary.total_requests or 0
            total_matches = summary.total_matches or 0
            total_displays = summary.total_displays or 0
            total_clicks = summary.total_clicks or 0
            total_ecpm_after = summary.total_ecpm_after or 0
            total_revenue_after = summary.total_revenue_after or 0
            avg_coverage_rate = summary.avg_coverage_rate or 0
            avg_display_rate = summary.avg_display_rate or 0
            avg_click_rate = summary.avg_click_rate or 0

        # 如果是管理员，还需要汇总未减扣的数据
        total_ecpm_before = 0
        total_revenue_before = 0
        if is_admin(current_user):
            admin_query = select(
                func.sum(AdData.ecpm_before_deduct).label("total_ecpm_before"),
                func.sum(AdData.revenue_before_deduct).label("total_revenue_before")
            )
            admin_query = admin_query.join(Product, AdData.product_id == Product.id)

            # 使用与主查询相同的产品分配历史表逻辑
            if use_assignment_table:
                admin_query = admin_query.join(
                    ProductAssignment,
                    and_(
                        ProductAssignment.product_id == Product.id,
                        AdData.date >= ProductAssignment.start_date,
                        or_(
                            ProductAssignment.end_date.is_(None),
                            AdData.date < func.date_add(ProductAssignment.end_date, text("INTERVAL 1 DAY"))
                        )
                    )
                )
                admin_query = admin_query.join(Client, ProductAssignment.client_id == Client.id)
            else:
                admin_query = admin_query.join(Client, Product.client_id == Client.id)

            admin_query = admin_query.where(Product.is_active == True)

            if client_id:
                admin_query = admin_query.where(Client.id == client_id)
            if product_id:
                admin_query = admin_query.where(AdData.product_id == product_id)

            admin_query = apply_date_range_filter(
                admin_query,
                AdData.date,
                start_date,
                end_date,
                default_to_current_month=True
            )

            admin_result = await self.db.execute(admin_query)
            admin_summary = admin_result.first()
            if admin_summary:
                total_ecpm_before = admin_summary.total_ecpm_before or 0
                total_revenue_before = admin_summary.total_revenue_before or 0

        # 构建响应数据
        response_data = {
            "date_range": {
                "start_date": start_date or (date.today() - timedelta(days=30)),
                "end_date": end_date or date.today()
            },
            "total_requests": total_requests,
            "total_matches": total_matches,
            "total_displays": total_displays,
            "total_clicks": total_clicks,
            "avg_coverage_rate": round(avg_coverage_rate, 4),
            "avg_display_rate": round(avg_display_rate, 4),
            "avg_click_rate": round(avg_click_rate, 4),
            "total_ecpm_after_deduct": round(total_ecpm_after, 4),
            "total_revenue_after_deduct": round(total_revenue_after, 4)
        }

        # 管理员额外返回未减扣汇总数据
        if current_user.role == "admin":
            response_data.update({
                "total_ecpm_before_deduct": round(total_ecpm_before, 4),
                "total_revenue_before_deduct": round(total_revenue_before, 4)
            })

        # 缓存结果（缓存 2 分钟）
        await set_cached(cache_key, response_data, ttl=120)

        return response_data

    async def get_daily_summary(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 10,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        client_id: Optional[int] = None,
        product_id: Optional[str] = None,
        sort_by: str = "date",
        sort_order: str = "desc"
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        获取每日汇总数据（按产品+日期汇总）

        Args:
            current_user: 当前用户
            page: 页码
            page_size: 每页数量
            start_date: 开始日期
            end_date: 结束日期
            client_id: 客户ID过滤
            product_id: 产品ID过滤（字符串格式）
            sort_by: 排序字段
            sort_order: 排序方向

        Returns:
            Tuple[List[Dict], int]: (汇总数据列表, 总数)
        """
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        # 构建汇总查询：按产品+日期分组
        query = select(
            func.date(AdData.date).label("date"),
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Client.id.label("client_id"),
            Client.company_name.label("client_name"),
            User.full_name.label("user_full_name"),
            User.username.label("user_username"),
            func.sum(AdData.request_count).label("request_count"),
            func.sum(AdData.match_count).label("match_count"),
            func.sum(AdData.display_count).label("display_count"),
            func.sum(AdData.click_count).label("click_count"),
            func.avg(AdData.viewability_rate).label("viewability_rate"),
            func.sum(AdData.cpc).label("cpc"),
            func.sum(AdData.pageviews).label("pageviews"),
            func.sum(AdData.revenue_after_deduct).label("revenue_after_deduct"),
            func.sum(AdData.revenue_before_deduct).label("revenue_before_deduct")
        ).join(Product, AdData.product_id == Product.id)

        # 只显示激活状态的产品
        query = query.where(Product.is_active == True)

        if use_assignment_table:
            # 使用产品分配历史表
            end_date_with_default = func.coalesce(
                func.date_add(ProductAssignment.end_date, text("INTERVAL 1 DAY")),
                literal_column("'2099-12-31'")
            )
            query = query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    AdData.date >= ProductAssignment.start_date,
                    AdData.date < end_date_with_default
                )
            )
            query = query.join(Client, ProductAssignment.client_id == Client.id)
        else:
            query = query.join(Client, Product.client_id == Client.id)

        query = query.join(User, Client.user_id == User.id)

        # 权限过滤
        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        else:
            if client_id:
                query = query.where(Client.id == client_id)

        # 产品ID过滤
        if product_id and product_id.strip():
            try:
                product_id_int = int(product_id)
                query = query.where(AdData.product_id == product_id_int)
            except ValueError:
                logger.warning(f"无效的产品ID参数: {product_id}")

        # 日期范围过滤
        query = apply_date_range_filter(
            query,
            AdData.date,
            start_date,
            end_date,
            default_to_current_month=True
        )

        # 分组
        query = query.group_by(
            func.date(AdData.date),
            Product.id,
            Product.name,
            Client.id,
            Client.company_name,
            User.full_name,
            User.username
        )

        # 验证排序字段
        valid_sort_fields = {
            "date": func.date(AdData.date),
            "product": Product.name,
            "product_id": Product.id,
            "request_count": func.sum(AdData.request_count),
            "match_count": func.sum(AdData.match_count),
            "display_count": func.sum(AdData.display_count),
            "click_count": func.sum(AdData.click_count),
            "cpc": func.sum(AdData.cpc),
            "pageviews": func.sum(AdData.pageviews),
            "coverage_rate": func.avg(AdData.coverage_rate),
            "display_rate": func.avg(AdData.display_rate),
            "click_rate": func.avg(AdData.click_rate),
            "viewability_rate": func.avg(AdData.viewability_rate),
            "ecpm_after_deduct": func.sum(AdData.revenue_after_deduct),
            "revenue_after_deduct": func.sum(AdData.revenue_after_deduct),
            "revenue_before_deduct": func.sum(AdData.revenue_before_deduct)
        }

        # 需要内存排序的字段
        memory_sort_fields = {"ecpm_before_deduct"}

        # 判断是否需要内存排序
        need_memory_sort = sort_by in memory_sort_fields

        # SQL排序
        if sort_by in valid_sort_fields:
            sort_column = valid_sort_fields[sort_by]
            if sort_order.lower() == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())
        elif not need_memory_sort:
            # 无效的排序字段，使用默认排序
            sort_by = "date"
            sort_column = valid_sort_fields[sort_by]
            if sort_order.lower() == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())

        # 计算总数
        total = 0
        if not need_memory_sort:
            try:
                # 使用子查询优化计数
                subquery = select(
                    func.date(AdData.date).label("date"),
                    Product.id.label("product_id")
                ).select_from(AdData)
                subquery = subquery.join(Product, AdData.product_id == Product.id)
                subquery = subquery.where(Product.is_active == True)

                if use_assignment_table:
                    end_date_with_default = func.coalesce(
                        func.date_add(ProductAssignment.end_date, text("INTERVAL 1 DAY")),
                        literal_column("'2099-12-31'")
                    )
                    subquery = subquery.join(
                        ProductAssignment,
                        and_(
                            ProductAssignment.product_id == Product.id,
                            AdData.date >= ProductAssignment.start_date,
                            AdData.date < end_date_with_default
                        )
                    )
                    subquery = subquery.join(Client, ProductAssignment.client_id == Client.id)
                else:
                    subquery = subquery.join(Client, Product.client_id == Client.id)

                # 应用相同的过滤条件
                if not is_admin(current_user):
                    subquery = subquery.where(Client.user_id == current_user.id)
                else:
                    if client_id:
                        subquery = subquery.where(Client.id == client_id)

                if product_id and product_id.strip():
                    try:
                        product_id_int = int(product_id)
                        subquery = subquery.where(AdData.product_id == product_id_int)
                    except ValueError:
                        pass

                subquery = apply_date_range_filter(
                    subquery,
                    AdData.date,
                    start_date,
                    end_date,
                    default_to_current_month=True
                )

                subquery = subquery.group_by(
                    func.date(AdData.date),
                    Product.id
                )

                count_query = select(func.count()).select_from(subquery.alias("distinct_groups"))
                count_result = await self.db.execute(count_query)
                total = count_result.scalar() or 0
            except Exception as e:
                logger.error(f"计算每日汇总总数失败: {str(e)}")
                total = 0

        # 分页查询
        if need_memory_sort:
            # 获取所有数据（不分页）
            result = await self.db.execute(query)
            all_summary_data = result.all()
        else:
            # 使用SQL分页
            offset = (page - 1) * page_size
            result = await self.db.execute(query.offset(offset).limit(page_size))
            all_summary_data = result.all()

        # 转换为响应格式
        ad_data_responses = []
        for row in all_summary_data:
            date_obj = row.date if isinstance(row.date, date) else row.date.date() if hasattr(row.date, 'date') else row.date
            date_str = date_obj.isoformat() if hasattr(date_obj, 'isoformat') else str(date_obj)

            # 获取汇总后的数值
            total_request_count = int(row.request_count or 0)
            total_match_count = int(row.match_count or 0)
            total_display_count = int(row.display_count or 0)
            total_click_count = int(row.click_count or 0)
            total_viewability_rate = float(row.viewability_rate or 0.0)
            total_cpc = float(row.cpc or 0.0)
            total_pageviews = int(row.pageviews or 0)
            total_revenue_after = float(row.revenue_after_deduct or 0.0)
            total_revenue_before = float(row.revenue_before_deduct or 0.0)

            # 根据汇总后的数值重新计算比率
            coverage_rate = round(
                (total_match_count / total_request_count * PERCENTAGE_MULTIPLIER) if total_request_count > 0 else 0.0,
                2
            )
            display_rate = round(
                (total_display_count / total_match_count * PERCENTAGE_MULTIPLIER) if total_match_count > 0 else 0.0,
                2
            )
            click_rate = round(
                (total_click_count / total_display_count * 100) if total_display_count > 0 else 0.0,
                2
            )
            ecpm_after_deduct = round(
                (total_revenue_after / total_display_count * ECPM_MULTIPLIER) if total_display_count > 0 else 0.0,
                4
            )
            ecpm_before_deduct = round(
                (total_revenue_before / total_display_count * ECPM_MULTIPLIER) if total_display_count > 0 else 0.0,
                4
            )

            client_name = row.client_name or ""
            user_name = row.user_full_name or row.user_username or ""

            response_data = {
                "id": 0,  # 汇总数据没有ID
                "date": date_str,
                "product_id": row.product_id,
                "product_name": row.product_name or "",
                "country_code": "ZZ",  # 全部区域
                "country_name_zh": "全部区域",
                "request_count": total_request_count,
                "match_count": total_match_count,
                "coverage_rate": coverage_rate,
                "display_count": total_display_count,
                "display_rate": display_rate,
                "click_count": total_click_count,
                "click_rate": click_rate,
                "viewability_rate": round(total_viewability_rate, 2),
                "cpc": round(total_cpc, 2),
                "pageviews": total_pageviews,
                "ecpm_after_deduct": ecpm_after_deduct,
                "revenue_after_deduct": round(total_revenue_after, 4),
                "user_name": user_name
            }

            # 管理员额外返回未减扣数据
            if is_admin(current_user):
                response_data.update({
                    "client_id": row.client_id,
                    "client_name": client_name,
                    "ecpm_before_deduct": ecpm_before_deduct,
                    "revenue_before_deduct": round(total_revenue_before, 4)
                })

            ad_data_responses.append(response_data)

        # 内存排序（如果需要）
        if need_memory_sort:
            reverse_order = sort_order.lower() == "desc"
            if sort_by == "ecpm_before_deduct":
                ad_data_responses.sort(key=lambda x: x.get("ecpm_before_deduct", 0) or 0, reverse=reverse_order)
            # 内存排序后，需要重新计算总数和分页
            total = len(ad_data_responses)
            offset = (page - 1) * page_size
            ad_data_responses = ad_data_responses[offset:offset + page_size]

        return ad_data_responses, total

    async def get_ad_data(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 10,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        client_id: Optional[int] = None,
        product_id: Optional[str] = None,
        country_code: Optional[str] = None,
        sort_by: str = "date",
        sort_order: str = "desc"
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        获取广告数据列表（支持分页、过滤和排序）

        Args:
            current_user: 当前用户
            page: 页码
            page_size: 每页数量
            start_date: 开始日期
            end_date: 结束日期
            client_id: 客户ID过滤
            product_id: 产品ID过滤（字符串格式）
            country_code: 国家代码过滤
            sort_by: 排序字段
            sort_order: 排序方向

        Returns:
            Tuple[List[Dict], int]: (广告数据列表, 总数)
        """
        # 延迟导入，避免循环导入
        from app.api_v1.excel.utils import normalize_date_key
        
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        # 构建查询基础
        if use_assignment_table:
            # 使用产品分配历史表进行查询
            query = select(AdData, Product, Client, User, ProductAssignment, CountryInfo)
            query = query.options(load_only(
                Client.id, Client.user_id, Client.company_name, Client.contact_person,
                Client.phone, Client.address, Client.is_active, Client.created_at, Client.updated_at
            ))
            query = query.join(Product, AdData.product_id == Product.id)
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
            query = query.join(User, Client.user_id == User.id)
            query = join_country_info_for_ad_data(query)
        else:
            # 旧的查询方式
            query = select(AdData, Product, Client, User, CountryInfo)
            query = query.options(load_only(
                Client.id, Client.user_id, Client.company_name, Client.contact_person,
                Client.phone, Client.address, Client.is_active, Client.created_at, Client.updated_at
            ))
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)
            query = query.join(User, Client.user_id == User.id)
            query = join_country_info_for_ad_data(query)

        # 权限过滤
        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        else:
            if client_id:
                query = query.where(Client.id == client_id)

        # 产品状态过滤
        query = query.where(Product.is_active == True)

        # 产品ID过滤
        if product_id and product_id.strip():
            try:
                product_id_int = int(product_id)
                query = query.where(AdData.product_id == product_id_int)
            except ValueError:
                logger.warning(f"无效的产品ID参数: {product_id}")

        # 国家代码过滤
        if country_code and country_code.strip():
            country_code_clean = country_code.strip()
            if country_code_clean and country_code_clean != 'ZZ' and len(country_code_clean) <= 2:
                query = query.where(AdData.country_code == country_code_clean)
            elif country_code_clean and len(country_code_clean) > 2:
                logger.warning(f"国家代码长度超过2个字符: {country_code_clean}，将忽略此过滤条件")

        # 日期范围过滤
        query = apply_date_range_filter(
            query,
            AdData.date,
            start_date,
            end_date,
            default_to_current_month=True
        )

        # 验证排序字段并设置排序
        valid_sort_fields = {
            "date": AdData.date,
            "client": Client.company_name,
            "client_id": Client.id,
            "product": Product.name,
            "product_id": Product.id,
            "request_count": AdData.request_count,
            "match_count": AdData.match_count,
            "display_count": AdData.display_count,
            "click_count": AdData.click_count,
            "cpc": AdData.cpc,
            "pageviews": AdData.pageviews,
            "ecpm_after_deduct": AdData.ecpm_after_deduct,
            "ecpm_before_deduct": AdData.ecpm_before_deduct,
            "revenue_after_deduct": AdData.revenue_after_deduct,
            "revenue_before_deduct": AdData.revenue_before_deduct,
            "coverage_rate": AdData.coverage_rate,
            "display_rate": AdData.display_rate,
            "click_rate": AdData.click_rate,
            "viewability_rate": AdData.viewability_rate
        }

        # 默认排序字段
        if sort_by not in valid_sort_fields:
            sort_by = "date"

        # 获取排序字段
        sort_column = valid_sort_fields[sort_by]

        # 设置排序方向
        if sort_order.lower() == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # 计算总数
        total = 0
        try:
            # 构建过滤条件列表
            filter_conditions = []

            # 权限过滤
            if not is_admin(current_user):
                filter_conditions.append(Client.user_id == current_user.id)
            elif client_id:
                filter_conditions.append(Client.id == client_id)

            # 产品状态过滤
            filter_conditions.append(Product.is_active == True)

            # 产品ID过滤
            if product_id and product_id.strip():
                try:
                    product_id_int = int(product_id)
                    filter_conditions.append(AdData.product_id == product_id_int)
                except ValueError:
                    pass

            # 国家代码过滤
            if country_code and country_code.strip():
                country_code_clean = country_code.strip()
                if country_code_clean and country_code_clean != 'ZZ' and len(country_code_clean) <= 2:
                    filter_conditions.append(AdData.country_code == country_code_clean)

            # 日期范围过滤
            date_range_start = start_date
            date_range_end = end_date
            if not date_range_start and not date_range_end:
                today = date.today()
                month_start = date(today.year, today.month, 1)
                _, last_day = monthrange(today.year, today.month)
                month_end = date(today.year, today.month, last_day)
                date_range_start = month_start
                date_range_end = month_end

            date_condition = date_range_condition(AdData.date, date_range_start, date_range_end)
            if date_condition is not None:
                # 直接添加条件，不再检查类型
                filter_conditions.append(date_condition)

            # 优化：计数查询不需要JOIN User表
            count_query = select(func.count(AdData.id))
            count_query = count_query.join(Product, AdData.product_id == Product.id)
            if use_assignment_table:
                count_query = count_query.join(
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
                count_query = count_query.join(Client, ProductAssignment.client_id == Client.id)
            else:
                count_query = count_query.join(Client, Product.client_id == Client.id)

            # 应用所有过滤条件
            if filter_conditions:
                count_query = count_query.where(and_(*filter_conditions))

            count_result = await self.db.execute(count_query)
            total = count_result.scalar() or 0
        except Exception as e:
            logger.error(f"计算广告数据总数失败: {str(e)}")
            total = 0

        # 分页查询
        offset = (page - 1) * page_size
        result = await self.db.execute(query.offset(offset).limit(page_size))
        data = result.unique().all()

        # 转换为响应格式
        ad_data_responses = []
        for row in data:
            try:
                ad_data, product, client, user, assignment, country_info = unpack_ad_data_query_result(
                    row, use_assignment_table
                )
            except (ValueError, Exception) as e:
                logger.warning(f"解构数据失败: {str(e)}, row={row}")
                continue

            # 使用统一的比率计算函数
            coverage_rate = calculate_coverage_rate(
                ad_data.match_count,
                ad_data.request_count,
                ad_data.coverage_rate
            )
            display_rate = calculate_display_rate(
                ad_data.display_count,
                ad_data.match_count,
                ad_data.display_rate
            )
            click_rate = calculate_click_rate(
                ad_data.click_count,
                ad_data.display_count,
                ad_data.click_rate
            )
            viewability_rate = ad_data.viewability_rate if ad_data.viewability_rate is not None else 0.0

            # 将 DateTime 转换为 date
            date_value = normalize_date_key(ad_data.date)

            # 获取国家名称
            country_name_zh = resolve_country_name(country_info, ad_data.country_code)

            response_data = {
                "id": ad_data.id,
                "date": date_value,
                "product_id": product.id,
                "product_name": product.name,
                "country_code": ad_data.country_code,
                "country_name_zh": country_name_zh,
                "request_count": ad_data.request_count,
                "match_count": ad_data.match_count,
                "coverage_rate": coverage_rate,
                "display_count": ad_data.display_count,
                "display_rate": display_rate,
                "click_count": ad_data.click_count,
                "click_rate": click_rate,
                "viewability_rate": round(viewability_rate, 2),
                "cpc": round(ad_data.cpc or 0.0, 2),
                "pageviews": ad_data.pageviews or 0,
                "ecpm_after_deduct": round(ad_data.ecpm_after_deduct, 4),
                "revenue_after_deduct": round(ad_data.revenue_after_deduct, 4)
            }

            # 管理员额外返回未减扣数据和客户信息
            if is_admin(current_user):
                response_data.update({
                    "client_id": client.id,
                    "client_name": client.company_name,
                    "user_name": user.full_name or user.username,
                    "ecpm_before_deduct": round(ad_data.ecpm_before_deduct, 4),
                    "revenue_before_deduct": round(ad_data.revenue_before_deduct, 4)
                })

            ad_data_responses.append(response_data)

        return ad_data_responses, total

