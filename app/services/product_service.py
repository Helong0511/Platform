"""
产品服务层。

功能说明：
- 产品 CRUD 与分页列表（客户用户仅可见归属产品）
- 创建时初始化 ProductAssignment；客户变更时 transfer_product_assignment
- 删除：有 AdData 则转移至「临时挂靠」，否则物理删除

特殊逻辑：
- 创建时若同名产品属于临时挂靠，则改绑 client_id 复用历史广告数据

在系统中的位置：
- 被管理端产品 API 调用；继承 ``BaseService[Product]``
"""
from typing import Optional, List, Dict, Any
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, text
from sqlalchemy.orm import selectinload, joinedload

from app.models.models import Product, Client, User, UserRole, AdData
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.utils import get_app_now_naive, find_or_create_default_client
from app.core.product_assignment import initialize_product_assignment, transfer_product_assignment
import logging

logger = logging.getLogger(__name__)


class ProductService(BaseService[Product]):
    """
    产品管理服务。

    写操作（创建/更新/删除）仅管理员可执行；读操作按 UserRole 过滤可见范围。
    """

    def __init__(self, db: AsyncSession):
        """注入数据库会话并绑定 Product 模型。"""
        super().__init__(db, Product)

    async def get_product_by_id(
            self,
            product_id: int,
            current_user: User,
            include_client: bool = True
    ) -> Product:
        """
        根据 ID 获取产品详情。

        客户用户通过 JOIN Client 过滤；不存在时区分「无权限」与「未找到」。

        Args:
            product_id: 产品 ID
            current_user: 当前用户
            include_client: 是否 selectinload 客户信息

        Returns:
            Product 对象
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
            search: Optional[str] = None,
            product_id: Optional[int] = None,
    ) -> tuple[List[Product], int]:
        """
        分页获取产品列表。

        名称/搜索优先前缀匹配或全文索引；管理员可按 client_id / product_id 筛选。

        Args:
            current_user: 当前用户
            page: 页码
            page_size: 每页数量
            client_id: 客户 ID（管理员）
            name: 产品名称前缀
            is_active: 启用状态
            search: 搜索词（全文或前缀）
            product_id: 精确产品 ID（广告数据跳转定位用）

        Returns:
            (产品列表, 总条数)
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

        if product_id is not None:
            conditions.append(Product.id == product_id)

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

        # 总数查询（优化：不加载关联数据；管理员按 client_id 过滤须与主查询一致）
        count_query = select(func.count(Product.id))
        if current_user.role != UserRole.ADMIN:
            count_query = count_query.join(Client, Product.client_id == Client.id).where(
                Client.user_id == current_user.id
            )
        elif client_id:
            count_query = count_query.where(Product.client_id == client_id)
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
        创建产品（仅管理员）。

        若已存在同名且归属「临时挂靠」的产品，则更新其 client_id
        与扣减比例（复用历史 AdData），否则新建并 initialize_product_assignment。

        Args:
            product_data: 含 name、client_id、扣减比例、Postback 配置等
            current_user: 当前用户

        Returns:
            创建或改绑后的产品对象
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

        # ====== 临时挂靠同名产品改绑逻辑 ======
        product_with_client_query = select(Product, Client).join(
            Client, Product.client_id == Client.id
        ).where(
            Product.name == product_data['name']
        )
        product_with_client_result = await self.db.execute(product_with_client_query)
        products_with_clients = product_with_client_result.unique().all()

        # 查找属于临时挂靠的产品
        admin_default_product = None
        for product_obj, client_obj in products_with_clients:
            if client_obj.company_name == "临时挂靠":
                admin_default_product = product_obj
                break

        # 如果找到属于临时挂靠的产品，更新client_id而不是创建新产品
        if admin_default_product:
            old_client_id = admin_default_product.client_id
            logger.info(
                f"产品名称 '{product_data['name']}' 属于临时挂靠（产品ID: {admin_default_product.id}，"
                f"原客户ID: {old_client_id}），将更新为客户ID: {client_id}"
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
            if 'downstream_postback_success_check' in product_data:
                admin_default_product.downstream_postback_success_check = product_data[
                    'downstream_postback_success_check'
                ]
            if 'notification_address' in product_data:
                admin_default_product.notification_address = product_data['notification_address']

            # 同步分配历史，避免 products.client_id 与 product_assignments 不一致
            try:
                await transfer_product_assignment(
                    db=self.db,
                    product_id=admin_default_product.id,
                    old_client_id=old_client_id,
                    new_client_id=client_id,
                    transfer_date=date.today(),
                )
            except Exception as e:
                await self.db.rollback()
                logger.error(
                    f"临时挂靠同名产品改绑时更新分配历史失败: product_id={admin_default_product.id}, err={e}",
                    exc_info=True,
                )
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail="产品从临时挂靠改绑时更新分配历史失败，请稍后重试",
                )

            await self.db.flush()
            await self.db.refresh(admin_default_product)

            logger.info(
                f"产品 '{product_data['name']}' 已从临时挂靠转移到客户ID {client_id}，"
                f"并更新了扣减比例与分配历史"
            )

            return admin_default_product

        # 如果没有找到属于临时挂靠的产品，创建新产品
        product = Product(
            client_id=client_id,
            name=product_data['name'],
            ecpm_deduct_ratio=ecpm_ratio,
            revenue_deduct_ratio=revenue_ratio,
            is_active=product_data.get('is_active', True),
            downstream_postback_url=product_data.get('downstream_postback_url'),
            downstream_postback_method=product_data.get('downstream_postback_method', 'GET'),
            downstream_postback_success_check=product_data.get('downstream_postback_success_check'),
            notification_address=product_data.get('notification_address')
        )

        self.db.add(product)
        await self.db.flush()  # 先flush以获取product.id

        # 初始化产品分配记录（失败则整体回滚，避免有产品无分配历史）
        product_start_date = date.today()
        await initialize_product_assignment(
            db=self.db,
            product_id=product.id,
            client_id=product.client_id,
            start_date=product_start_date,
        )
        logger.info(
            "产品 %s 的分配记录已初始化：客户 %s，开始日期: %s",
            product.id,
            product.client_id,
            product_start_date,
        )

        await self.db.flush()
        await self.db.refresh(product)

        logger.info(f"产品已创建: {product.name} (ID: {product.id})")
        return product

    async def update_product(
            self,
            product_id: int,
            product_data: Dict[str, Any],
            current_user: User
    ) -> Product:
        """
        更新产品信息（仅管理员，支持客户转移）。

        client_id 变更时须通过 transfer_product_assignment 维护分配历史；
        transfer_date / old_client_end_date 用于精确控制切换日期，须满足
        「旧客户结束日 + 1 天 = 新客户开始日」以避免 AdData 空窗。

        Args:
            product_id: 产品 ID
            product_data: 更新字段（可含 transfer_date、old_client_end_date）
            current_user: 当前用户

        Returns:
            更新后的产品对象
        """
        # 权限检查：仅管理员可更新产品
        self.require_admin(current_user)

        # 获取产品
        product = await self.get_product_by_id(product_id, current_user, include_client=False)

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

        # ====== 客户转移：校验日期连续性并写分配历史 ======
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
                await self.db.rollback()
                logger.error(f"产品分配历史验证失败: {str(e)}", exc_info=True)
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=str(e)
                )
            except Exception as e:
                await self.db.rollback()
                logger.error(f"记录产品分配历史失败: {str(e)}", exc_info=True)
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail="产品客户转移失败，请稍后重试",
                )

        # 更新产品字段
        for key, value in product_data.items():
            if hasattr(product, key):
                setattr(product, key, value)

        await self.db.flush()
        await self.db.refresh(product)

        try:
            from app.core.postback.forwarding.cache_manager import CacheManager
            await CacheManager.invalidate_product(product.id)
        except Exception as e:
            logger.debug("失效产品转发缓存失败: %s", e)

        logger.info(f"产品已更新: {product.name} (ID: {product.id})")
        return product

    async def delete_product(
            self,
            product_id: int,
            current_user: User
    ) -> Dict[str, Any]:
        """
        删除或软转移产品（仅管理员）。

        删除规则：
        1. 有关联 AdData → 转移至「临时挂靠」并清零扣减比例
        2. 无关联数据 → 物理删除

        Args:
            product_id: 产品 ID
            current_user: 当前用户

        Returns:
            含 transferred、message、new_client_id（转移时）的结果字典
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
            # 有关联广告数据：将产品转移到临时挂靠
            logger.info(
                f"产品 {product.name} (ID: {product_id}) 关联了 {ad_data_count} 条广告数据，"
                f"将转移到临时挂靠"
            )

            # 查找或创建临时挂靠客户
            admin_default_client = await find_or_create_default_client(self.db, current_user.id)

            # 保存旧客户ID
            old_client_id = product.client_id

            # 检查临时挂靠客户是否已有同名产品
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
                    f"临时挂靠已存在同名产品 '{product.name}' (ID: {existing_product.id})，"
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
                await transfer_product_assignment(
                    db=self.db,
                    product_id=product.id,
                    old_client_id=old_client_id,
                    new_client_id=admin_default_client.id,
                    transfer_date=date.today()
                )
                logger.info(
                    f"产品 {product.id} 的分配历史已更新："
                    f"从客户 {old_client_id} 转移到临时挂靠 {admin_default_client.id}"
                )
            except Exception as e:
                await self.db.rollback()
                logger.error(f"更新产品分配历史失败: {str(e)}", exc_info=True)
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail="产品转移时更新分配历史失败，请稍后重试",
                )

            await self.db.flush()
            await self.db.refresh(product)

            try:
                from app.core.postback.forwarding.cache_manager import CacheManager
                await CacheManager.invalidate_product(product.id)
            except Exception as e:
                logger.debug("失效产品转发缓存失败: %s", e)

            return {
                "transferred": True,
                "message": f"产品已转移到临时挂靠（该产品关联了 {ad_data_count} 条广告数据）",
                "new_client_id": admin_default_client.id
            }
        else:
            # 没有关联广告数据：直接删除产品
            logger.debug(f"产品 {product.name} (ID: {product_id}) 没有关联广告数据，将直接删除")

            try:
                from app.core.postback.forwarding.cache_manager import CacheManager
                await CacheManager.invalidate_product(product.id)
            except Exception as e:
                logger.debug("失效产品转发缓存失败: %s", e)

            # 删除产品
            await self.db.delete(product)
            await self.db.flush()

            logger.info(f"产品已删除: {product.name} (ID: {product_id})")

            return {
                "transferred": False,
                "message": "产品已成功删除"
            }
