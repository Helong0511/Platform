"""
产品服务层
封装产品相关的业务逻辑
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import selectinload, joinedload

from app.models.models import Product, Client, User, UserRole, AdData
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.audit_log import log_user_action, log_activate, log_deactivate, log_update, log_delete
from app.core.utils import get_app_now_naive
import logging

logger = logging.getLogger(__name__)


class ProductService(BaseService[Product]):
    """产品服务"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(db, Product)
    
    async def get_product_by_id(
        self,
        product_id: int,
        current_user: User,
        include_client: bool = True
    ) -> Product:
        """
        根据ID获取产品详情
        
        Args:
            product_id: 产品ID
            current_user: 当前用户（用于权限检查）
            include_client: 是否包含客户信息
        
        Returns:
            Product: 产品对象
        
        Raises:
            HTTPException: 如果产品不存在或没有权限
        """
        # 构建查询 - 使用JOIN优化，避免N+1查询
        query = select(Product).where(Product.id == product_id)
        
        # 权限过滤：客户只能查看自己的产品
        if current_user.role != UserRole.ADMIN:
            query = query.join(Client, Product.client_id == Client.id).where(
                Client.user_id == current_user.id
            )
        
        # 如果需要客户信息，使用selectinload优化查询
        if include_client:
            query = query.options(selectinload(Product.client))
        
        result = await self.db.execute(query)
        product = result.scalar_one_or_none()
        
        if not product:
            # 如果是客户用户，可能是权限问题
            if current_user.role != UserRole.ADMIN:
                raise_api_exception(
                    ErrorCode.PRODUCT_NO_PERMISSION,
                    detail=f"您没有权限访问产品ID {product_id}，该产品不属于您的客户账户"
                )
            else:
                raise_api_exception(
                    ErrorCode.PRODUCT_NOT_FOUND,
                    detail=f"产品ID {product_id} 不存在"
                )
        
        return product
    
    async def get_products(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 10,
        client_id: Optional[int] = None,
        name: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None
    ) -> tuple[List[Product], int]:
        """
        获取产品列表（支持分页、筛选、搜索）
        
        Args:
            current_user: 当前用户（用于权限检查）
            page: 页码
            page_size: 每页数量
            client_id: 客户ID过滤
            name: 产品名称过滤
            is_active: 激活状态过滤
            search: 搜索关键词
        
        Returns:
            tuple: (产品列表, 总数)
        """
        # 构建查询 - 使用JOIN优化
        query = select(Product)
        
        # 权限过滤：客户只能查看自己的产品
        if current_user.role != UserRole.ADMIN:
            query = query.join(Client, Product.client_id == Client.id).where(
                Client.user_id == current_user.id
            )
        else:
            # 管理员可以查看所有产品，但可以按客户过滤
            if client_id:
                query = query.join(Client, Product.client_id == Client.id).where(
                    Client.id == client_id
                )
            else:
                # 使用left join以支持没有客户的产品
                query = query.outerjoin(Client, Product.client_id == Client.id)
        
        # 筛选条件
        conditions = []
        
        if name:
            # 优化：去掉func.lower()避免索引失效，使用前缀匹配可以使用索引
            # 如果数据库使用大小写不敏感的排序规则（如utf8mb4_unicode_ci），不需要func.lower()
            name_trimmed = name.strip()
            # 优先使用前缀匹配（可以使用索引）
            conditions.append(Product.name.like(f"{name_trimmed}%"))
            # 如果前缀匹配没有结果，也可以尝试包含匹配（性能较差，但更灵活）
            # conditions.append(Product.name.like(f"%{name_trimmed}%"))
        
        if is_active is not None:
            conditions.append(Product.is_active == is_active)
        
        if search:
            # 优化搜索：使用全文索引或前缀匹配
            search_trimmed = search.strip()
            
            # 尝试使用全文索引（如果存在）
            try:
                from sqlalchemy import text
                fulltext_condition = text(
                    "MATCH(name) AGAINST(:search_term IN NATURAL LANGUAGE MODE)"
                ).bindparams(search_term=search_trimmed)
                conditions.append(fulltext_condition)
            except Exception:
                # 全文索引不存在或查询失败，使用前缀匹配（可以使用普通索引）
                # 去掉func.lower()避免索引失效
                conditions.append(Product.name.like(f"{search_trimmed}%"))
                # 如果前缀匹配没有结果，也可以尝试包含匹配（性能较差，但更灵活）
                # conditions.append(Product.name.like(f"%{search_trimmed}%"))
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 总数查询（优化：不加载关联数据）
        count_query = select(func.count(Product.id))
        if current_user.role != UserRole.ADMIN:
            count_query = count_query.join(Client, Product.client_id == Client.id).where(
                Client.user_id == current_user.id
            )
        if conditions:
            count_query = count_query.where(and_(*conditions))
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页查询（使用selectinload优化客户信息加载）
        offset = (page - 1) * page_size
        query = query.options(selectinload(Product.client))
        query = query.order_by(Product.created_at.desc())
        query = query.offset(offset).limit(page_size)
        
        result = await self.db.execute(query)
        products = result.scalars().all()
        
        return products, total
    
    async def create_product(
        self,
        product_data: Dict[str, Any],
        current_user: User
    ) -> Product:
        """
        创建产品（支持处理默认客户（导入数据）的特殊逻辑）
        
        Args:
            product_data: 产品数据字典
            current_user: 当前用户
        
        Returns:
            Product: 创建或更新的产品对象
        """
        # 权限检查：仅管理员可创建产品
        self.require_admin(current_user)
        
        # 验证客户是否存在
        client_id = product_data.get('client_id')
        if not client_id:
            raise_api_exception(
                ErrorCode.PRODUCT_CLIENT_REQUIRED,
                detail="管理员创建产品时必须指定客户ID（client_id）"
            )
        
        client_result = await self.db.execute(
            select(Client).where(Client.id == client_id)
        )
        client = client_result.scalar_one_or_none()
        if not client:
            raise_api_exception(
                ErrorCode.CLIENT_NOT_FOUND,
                detail=f"指定的客户ID {client_id} 不存在，请确认客户是否存在"
            )
        
        # 验证减扣比例是否在有效范围内
        ecpm_ratio = product_data.get('ecpm_deduct_ratio', 0.0)
        revenue_ratio = product_data.get('revenue_deduct_ratio', 0.0)
        if (ecpm_ratio < 0 or ecpm_ratio > 1) or (revenue_ratio < 0 or revenue_ratio > 1):
            raise_api_exception(
                ErrorCode.PRODUCT_DEDUCT_RATIO_INVALID,
                detail=f"减扣比例必须在0-1之间。当前值：ecpm_deduct_ratio={ecpm_ratio}, revenue_deduct_ratio={revenue_ratio}"
            )
        
        # 检查当前客户是否已存在同名产品
        existing_product_result = await self.db.execute(
            select(Product).where(
                Product.client_id == client_id,
                Product.name == product_data['name']
            )
        )
        existing_product_for_client = existing_product_result.scalar_one_or_none()
        if existing_product_for_client:
            raise_api_exception(
                ErrorCode.PRODUCT_ALREADY_EXISTS,
                detail=f"客户ID {client_id} 已存在同名产品：{product_data['name']}。请使用不同的产品名称或更新现有产品"
            )
        
        # 检查是否存在相同名称的产品属于默认客户（导入数据）
        product_with_client_query = select(Product, Client).join(
            Client, Product.client_id == Client.id
        ).where(
            Product.name == product_data['name']
        )
        product_with_client_result = await self.db.execute(product_with_client_query)
        products_with_clients = product_with_client_result.unique().all()
        
        # 查找属于默认客户（导入数据）的产品
        admin_default_product = None
        for product_obj, client_obj in products_with_clients:
            if client_obj.company_name == "默认客户（导入数据）":
                admin_default_product = product_obj
                break
        
        # 如果找到属于默认客户（导入数据）的产品，更新client_id而不是创建新产品
        if admin_default_product:
            logger.info(
                f"产品名称 '{product_data['name']}' 属于默认客户（导入数据）（产品ID: {admin_default_product.id}，"
                f"原客户ID: {admin_default_product.client_id}），将更新为客户ID: {client_id}"
            )
            
            # 更新产品的client_id和扣减比例
            admin_default_product.client_id = client_id
            admin_default_product.ecpm_deduct_ratio = ecpm_ratio
            admin_default_product.revenue_deduct_ratio = revenue_ratio
            admin_default_product.is_active = product_data.get('is_active', True)
            
            # 更新下游 Postback 配置
            if 'downstream_postback_url' in product_data:
                admin_default_product.downstream_postback_url = product_data['downstream_postback_url']
            if 'downstream_postback_method' in product_data:
                admin_default_product.downstream_postback_method = product_data['downstream_postback_method']
            if 'notification_address' in product_data:
                admin_default_product.notification_address = product_data['notification_address']
            
            await self.db.commit()
            await self.db.refresh(admin_default_product)
            
            logger.info(
                f"产品 '{product_data['name']}' 已从默认客户（导入数据）转移到客户ID {client_id}，"
                f"并更新了扣减比例"
            )
            
            return admin_default_product
        
        # 如果没有找到属于管理员默认客户的产品，创建新产品
        product = Product(
            client_id=client_id,
            name=product_data['name'],
            ecpm_deduct_ratio=ecpm_ratio,
            revenue_deduct_ratio=revenue_ratio,
            is_active=product_data.get('is_active', True),
            downstream_postback_url=product_data.get('downstream_postback_url'),
            downstream_postback_method=product_data.get('downstream_postback_method', 'GET'),
            notification_address=product_data.get('notification_address')
        )
        
        self.db.add(product)
        await self.db.flush()  # 先flush以获取product.id
        
        # 初始化产品分配记录
        try:
            from datetime import date
            from app.core.product_assignment import initialize_product_assignment
            product_start_date = date.today()
            await initialize_product_assignment(
                db=self.db,
                product_id=product.id,
                client_id=product.client_id,
                start_date=product_start_date
            )
            logger.info(f"产品 {product.id} 的分配记录已初始化：客户 {product.client_id}，开始日期: {product_start_date}")
        except Exception as e:
            logger.warning(f"初始化产品分配记录失败: {str(e)}，但产品创建继续")
            # 分配记录初始化失败不影响产品创建，继续执行
        
        await self.db.commit()
        await self.db.refresh(product)
        
        # 记录审计日志
        await log_user_action(
            db=self.db,
            action_type="CREATE",
            user=current_user,
            username=current_user.username,
            resource_type="PRODUCT",
            resource_id=product.id,
            resource_name=product.name,
            success=True
        )
        
        logger.info(f"产品已创建: {product.name} (ID: {product.id})")
        return product
    
    async def update_product(
        self,
        product_id: int,
        product_data: Dict[str, Any],
        current_user: User
    ) -> Product:
        """
        更新产品信息（支持产品分配历史转移）
        
        Args:
            product_id: 产品ID
            product_data: 更新的数据字典（可能包含transfer_date和old_client_end_date）
            current_user: 当前用户
        
        Returns:
            Product: 更新后的产品对象
        """
        # 权限检查：仅管理员可更新产品
        self.require_admin(current_user)
        
        # 获取产品
        product = await self.get_product_by_id(product_id, current_user, include_client=False)
        
        # 记录旧的扣减比例，用于记录变更历史
        old_ecpm_deduct_ratio = product.ecpm_deduct_ratio
        old_revenue_deduct_ratio = product.revenue_deduct_ratio
        old_is_active = product.is_active
        
        # 如果更改产品名称，检查是否已存在
        if 'name' in product_data and product_data['name'] != product.name:
            existing_product_result = await self.db.execute(
                select(Product).where(
                    Product.client_id == product.client_id,
                    Product.name == product_data['name']
                )
            )
            existing_product = existing_product_result.scalar_one_or_none()
            if existing_product:
                raise_api_exception(
                    ErrorCode.PRODUCT_ALREADY_EXISTS,
                    detail=f"客户ID {product.client_id} 已存在同名产品：{product_data['name']}。请使用不同的产品名称"
                )
        
        # 验证减扣比例是否在有效范围内
        if 'ecpm_deduct_ratio' in product_data:
            ecpm_ratio = product_data['ecpm_deduct_ratio']
            if ecpm_ratio < 0 or ecpm_ratio > 1:
                raise_api_exception(
                    ErrorCode.PRODUCT_DEDUCT_RATIO_INVALID,
                    detail=f"eCPM减扣比例必须在0到1之间。当前值：{ecpm_ratio}"
                )
        
        if 'revenue_deduct_ratio' in product_data:
            revenue_ratio = product_data['revenue_deduct_ratio']
            if revenue_ratio < 0 or revenue_ratio > 1:
                raise_api_exception(
                    ErrorCode.PRODUCT_DEDUCT_RATIO_INVALID,
                    detail=f"收益减扣比例必须在0到1之间。当前值：{revenue_ratio}"
                )
        
        # 处理client_id变更（包括产品分配历史转移）
        old_client_id = product.client_id
        if 'client_id' in product_data and product_data['client_id'] != product.client_id:
            new_client_id = product_data['client_id']
            
            # 验证新客户是否存在
            client_result = await self.db.execute(
                select(Client).where(Client.id == new_client_id)
            )
            client = client_result.scalar_one_or_none()
            if not client:
                raise_api_exception(
                    ErrorCode.CLIENT_NOT_FOUND,
                    detail=f"客户ID {new_client_id} 不存在"
                )
            
            # 检查新客户是否已有同名产品
            existing_product_result = await self.db.execute(
                select(Product).where(
                    Product.client_id == new_client_id,
                    Product.name == product.name
                )
            )
            existing_product = existing_product_result.scalar_one_or_none()
            if existing_product:
                raise_api_exception(
                    ErrorCode.PRODUCT_ALREADY_EXISTS,
                    detail=f"目标客户ID {new_client_id} 已存在同名产品：{product.name}。无法转移产品"
                )
            
            # 处理产品分配历史转移
            from datetime import date, timedelta
            from app.core.product_assignment import transfer_product_assignment
            
            transfer_date = product_data.get("transfer_date")
            old_client_end_date = product_data.get("old_client_end_date")
            
            # 验证日期
            if transfer_date and transfer_date > date.today():
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"新客户开始日期不能是未来日期：{transfer_date}"
                )
            
            if old_client_end_date and old_client_end_date > date.today():
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"旧客户结束日期不能是未来日期：{old_client_end_date}"
                )
            
            # 如果同时提供了两个日期，验证它们的关系
            if transfer_date and old_client_end_date:
                if old_client_end_date >= transfer_date:
                    raise_api_exception(
                        ErrorCode.OPERATION_FAILED,
                        detail=f"旧客户结束日期（{old_client_end_date}）必须小于新客户开始日期（{transfer_date}）"
                    )
                # 验证日期连续性
                expected_start_date = old_client_end_date + timedelta(days=1)
                if transfer_date != expected_start_date:
                    raise_api_exception(
                        ErrorCode.OPERATION_FAILED,
                        detail=f"日期连续性错误：新客户开始日期（{transfer_date}）必须是旧客户结束日期（{old_client_end_date}）+ 1天，"
                        f"期望值：{expected_start_date}，以确保广告数据无空窗期"
                    )
            
            # 从product_data中移除这些字段，因为它们不是Product模型的字段
            product_data.pop("transfer_date", None)
            product_data.pop("old_client_end_date", None)
            
            # 执行产品分配历史转移
            try:
                await transfer_product_assignment(
                    db=self.db,
                    product_id=product.id,
                    old_client_id=old_client_id,
                    new_client_id=new_client_id,
                    transfer_date=transfer_date,
                    old_client_end_date=old_client_end_date
                )
                logger.info(
                    f"产品 {product.id} 的分配历史已更新："
                    f"从客户 {old_client_id} 转移到客户 {new_client_id}，"
                    f"新客户开始日期: {transfer_date or '自动计算'}，"
                    f"旧客户结束日期: {old_client_end_date or '自动计算'}"
                )
            except ValueError as e:
                # 验证失败（如重叠、空窗期等），需要回滚并返回错误
                await self.db.rollback()
                logger.error(f"产品分配历史验证失败: {str(e)}", exc_info=True)
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=str(e)
                )
            except Exception as e:
                # 其他异常（如数据库错误），记录日志但不影响产品转移
                logger.error(f"记录产品分配历史失败: {str(e)}", exc_info=True)
        
        # 更新产品字段
        for key, value in product_data.items():
            if hasattr(product, key):
                setattr(product, key, value)
        
        await self.db.commit()
        await self.db.refresh(product)
        
        # 如果 is_active 改变，记录激活/禁用日志
        if 'is_active' in product_data and product_data['is_active'] != old_is_active:
            from app.core.audit_log import log_activate, log_deactivate
            if product.is_active:
                await log_activate(
                    db=self.db,
                    user=current_user,
                    resource_type="PRODUCT",
                    resource_id=product.id,
                    resource_name=product.name
                )
            else:
                await log_deactivate(
                    db=self.db,
                    user=current_user,
                    resource_type="PRODUCT",
                    resource_id=product.id,
                    resource_name=product.name
                )
        
        # 记录审计日志
        log_details = {**product_data}
        log_details["note"] = "修改扣减比例后，不会更新现有广告数据，新比例只影响未来导入的数据"
        
        # 如果修改了扣减比例，记录变更历史
        if 'ecpm_deduct_ratio' in product_data or 'revenue_deduct_ratio' in product_data:
            deduct_ratio_changes = {}
            if 'ecpm_deduct_ratio' in product_data:
                new_ecpm_ratio = product_data['ecpm_deduct_ratio']
                deduct_ratio_changes["ecpm_deduct_ratio"] = {
                    "old_value": old_ecpm_deduct_ratio,
                    "new_value": new_ecpm_ratio,
                    "change": f"{old_ecpm_deduct_ratio} → {new_ecpm_ratio}",
                    "change_percentage": f"{(new_ecpm_ratio - old_ecpm_deduct_ratio) * 100:.2f}%"
                }
            if 'revenue_deduct_ratio' in product_data:
                new_revenue_ratio = product_data['revenue_deduct_ratio']
                deduct_ratio_changes["revenue_deduct_ratio"] = {
                    "old_value": old_revenue_deduct_ratio,
                    "new_value": new_revenue_ratio,
                    "change": f"{old_revenue_deduct_ratio} → {new_revenue_ratio}",
                    "change_percentage": f"{(new_revenue_ratio - old_revenue_deduct_ratio) * 100:.2f}%"
                }
            log_details["deduct_ratio_changes"] = deduct_ratio_changes
            log_details["is_deduct_ratio_adjusted"] = True
        
        # 如果只更新了 is_active，不记录 UPDATE 日志（避免重复）
        if len(product_data) > 1 or 'is_active' not in product_data:
            await log_user_action(
                db=self.db,
                action_type="UPDATE",
                user=current_user,
                username=current_user.username,
                resource_type="PRODUCT",
                resource_id=product.id,
                resource_name=product.name,
                success=True,
                details=log_details
            )
        
        logger.info(f"产品已更新: {product.name} (ID: {product.id})")
        return product
    
    async def delete_product(
        self,
        product_id: int,
        current_user: User
    ) -> Dict[str, Any]:
        """
        删除产品（支持转移到默认客户）
        
        删除规则：
        1. 如果产品关联了广告数据 → 将产品的 client_id 改为管理员的默认客户（不删除产品）
        2. 如果没有关联广告数据 → 直接删除产品
        
        Args:
            product_id: 产品ID
            current_user: 当前用户
        
        Returns:
            Dict: 包含操作结果的字典
                - transferred: bool - 是否转移到默认客户
                - message: str - 操作消息
                - new_client_id: int - 新客户ID（如果转移）
        """
        # 权限检查
        self.require_admin(current_user)
        
        # 获取产品
        product = await self.get_product_by_id(product_id, current_user, include_client=False)
        
        # 检查是否有关联的广告数据
        count_result = await self.db.execute(
            select(func.count(AdData.id)).where(AdData.product_id == product_id)
        )
        ad_data_count = count_result.scalar() or 0
        
        if ad_data_count > 0:
            # 有关联广告数据：将产品转移到默认客户（导入数据）
            logger.info(
                f"产品 {product.name} (ID: {product_id}) 关联了 {ad_data_count} 条广告数据，"
                f"将转移到默认客户（导入数据）"
            )
            
            # 查找或创建默认客户
            from app.core.utils import find_or_create_default_client
            admin_default_client = await find_or_create_default_client(self.db, current_user.id)
            
            # 保存旧客户ID
            old_client_id = product.client_id
            
            # 检查管理员的默认客户是否已有同名产品
            existing_product_result = await self.db.execute(
                select(Product).where(
                    Product.client_id == admin_default_client.id,
                    Product.name == product.name,
                    Product.id != product_id
                )
            )
            existing_product = existing_product_result.scalar_one_or_none()
            
            if existing_product:
                logger.warning(
                    f"默认客户（导入数据）已存在同名产品 '{product.name}' (ID: {existing_product.id})，"
                    f"将产品转移到该客户（ID: {admin_default_client.id}）"
                )
                product.client_id = admin_default_client.id
                product.ecpm_deduct_ratio = 0.0
                product.revenue_deduct_ratio = 0.0
            else:
                product.client_id = admin_default_client.id
                product.ecpm_deduct_ratio = 0.0
                product.revenue_deduct_ratio = 0.0
            
            # 更新产品分配历史
            try:
                from datetime import date
                from app.core.product_assignment import transfer_product_assignment
                await transfer_product_assignment(
                    db=self.db,
                    product_id=product.id,
                    old_client_id=old_client_id,
                    new_client_id=admin_default_client.id,
                    transfer_date=date.today()
                )
                logger.info(
                    f"产品 {product.id} 的分配历史已更新："
                    f"从客户 {old_client_id} 转移到默认客户 {admin_default_client.id}"
                )
            except Exception as e:
                logger.error(f"更新产品分配历史失败: {str(e)}", exc_info=True)
                # 分配历史更新失败不影响产品转移，继续执行
            
            await self.db.commit()
            await self.db.refresh(product)
            
            # 记录更新操作（产品转移）
            from app.core.audit_log import log_update
            await log_update(
                db=self.db,
                user=current_user,
                resource_type="PRODUCT",
                resource_id=product_id,
                resource_name=product.name,
                details={
                    "action": "transfer_to_admin_default_client",
                    "old_client_id": old_client_id,
                    "new_client_id": admin_default_client.id,
                    "ad_data_count": ad_data_count
                }
            )
            
            return {
                "transferred": True,
                "message": f"产品已转移到默认客户（导入数据）（该产品关联了 {ad_data_count} 条广告数据）",
                "new_client_id": admin_default_client.id
            }
        else:
            # 没有关联广告数据：直接删除产品
            logger.debug(f"产品 {product.name} (ID: {product_id}) 没有关联广告数据，将直接删除")
            
            # 记录删除操作（在删除前）
            from app.core.audit_log import log_delete
            await log_delete(
                db=self.db,
                user=current_user,
                resource_type="PRODUCT",
                resource_id=product_id,
                resource_name=product.name,
                details={
                    "client_id": product.client_id,
                    "deleted": True
                }
            )
            
            # 删除产品
            await self.db.delete(product)
            await self.db.commit()
            
            logger.info(f"产品已删除: {product.name} (ID: {product_id})")
            
            return {
                "transferred": False,
                "message": "产品已成功删除"
            }

