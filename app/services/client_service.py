"""
客户服务层。

功能说明：
- 客户（下游/渠道商户）的 CRUD 与分页列表
- 基于角色的访问控制：管理员全量操作，客户用户仅可查看自身关联 Client 数据
- 列表搜索支持 company_name 全文/模糊匹配（contact_person 同搜）

在系统中的位置：
- 被管理端客户 API 调用；继承 ``BaseService[Client]``

注意事项：
1. 创建客户常与 User 绑定，须在同一事务内保证关联一致
2. 删除客户前检查产品分配、通知配置等外键依赖
"""
import logging
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.fulltext_search import search_with_fulltext
from app.models.models import Client, User, UserRole
from app.services.base_service import BaseService

logger = logging.getLogger(__name__)


class ClientService(BaseService[Client]):
    """
    客户服务。

    继承 BaseService 获得通用 get_by_id 等能力；
    写操作（创建/更新/删除）仅限管理员，读操作按 user_id 隔离。
    """

    def __init__(self, db: AsyncSession):
        """注入数据库会话并绑定 Client 模型。"""
        super().__init__(db, Client)

    async def list_clients(
        self,
        *,
        page: int = 1,
        page_size: int = 10,
        company_name: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Client], int]:
        """
        分页查询客户列表（管理员后台）。

        Args:
            page: 页码
            page_size: 每页条数
            company_name: 公司名/联系人关键词（全文或 LIKE）
            is_active: 启用状态筛选；None 表示不限

        Returns:
            (客户列表, 总条数)；默认按 id 降序
        """
        query = select(Client).options(selectinload(Client.user))
        count_query = select(func.count(Client.id))

        if company_name:
            # 列表与 count 使用相同搜索条件，保证 total 与当前页一致
            query = await search_with_fulltext(
                db=self.db,
                model_class=Client,
                search_fields=["company_name", "contact_person"],
                search_term=company_name,
                base_query=query,
                use_fulltext=True,
            )
            count_query = await search_with_fulltext(
                db=self.db,
                model_class=Client,
                search_fields=["company_name", "contact_person"],
                search_term=company_name,
                base_query=count_query,
                use_fulltext=True,
            )
        if is_active is not None:
            query = query.where(Client.is_active == is_active)
            count_query = count_query.where(Client.is_active == is_active)

        total = (await self.db.execute(count_query)).scalar() or 0
        query = query.order_by(Client.id.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        return list(result.scalars().all()), int(total)

    async def get_client_by_id(
            self,
            client_id: int,
            current_user: User,
            include_user: bool = True
    ) -> Client:
        """
        根据 ID 获取客户详情。

        非管理员只能访问 user_id 与当前用户相同的客户记录。

        Args:
            client_id: 客户主键
            current_user: 当前登录用户
            include_user: 是否预加载关联 User

        Returns:
            Client 实体

        Raises:
            NOT_FOUND / FORBIDDEN
        """
        load_relations = ["user"] if include_user else None
        client = await self.get_by_id(client_id, load_relations=load_relations)

        if not client:
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                detail=f"客户 ID {client_id} 不存在"
            )

        # 权限检查：只有管理员或客户所属用户可以查看
        if current_user.role != UserRole.ADMIN and client.user_id != current_user.id:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="无权访问此客户信息"
            )

        return client

    async def get_clients_by_user_id(
            self,
            user_id: int,
            current_user: User
    ) -> List[Client]:
        """
        按用户 ID 列出其名下全部客户。

        权限：管理员任意 user_id；普通用户仅 user_id == current_user.id。

        Args:
            user_id: 关联用户 ID
            current_user: 当前登录用户

        Returns:
            客户列表（无分页）
        """
        # 权限检查：只有管理员或用户本人可以查看
        if current_user.role != UserRole.ADMIN and user_id != current_user.id:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="无权访问此用户的客户信息"
            )

        query = select(Client).where(Client.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def create_client(
            self,
            client_data: Dict[str, Any],
            current_user: User
    ) -> Client:
        """
        创建客户（仅管理员）。

        client_data 字段直接映射 Client 模型；flush 后返回带主键的实体。

        Args:
            client_data: 客户字段字典
            current_user: 当前用户

        Returns:
            新建 Client
        """
        # 权限检查：只有管理员可以创建客户
        if current_user.role != UserRole.ADMIN:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="只有管理员可以创建客户"
            )

        # 创建客户对象
        client = Client(**client_data)
        self.db.add(client)
        await self.db.flush()
        if client.id is not None:
            return await self.get_client_by_id(client.id, current_user, include_user=True)
        return client

    async def update_client(
            self,
            client_id: int,
            client_data: Dict[str, Any],
            current_user: User
    ) -> Client:
        """
        更新客户信息（仅管理员）。

        先通过 get_client_by_id 完成存在性与读权限校验，再按字典键 setattr。

        Args:
            client_id: 客户主键
            client_data: 待更新字段（忽略模型不存在的键）
            current_user: 当前用户

        Returns:
            更新后的 Client
        """
        client = await self.get_client_by_id(client_id, current_user)

        # 权限检查：只有管理员可以更新客户
        if current_user.role != UserRole.ADMIN:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="只有管理员可以更新客户信息"
            )

        # 更新字段
        for key, value in client_data.items():
            if hasattr(client, key):
                setattr(client, key, value)

        await self.db.flush()
        return await self.get_client_by_id(client_id, current_user, include_user=True)

    async def delete_client(
            self,
            client_id: int,
            current_user: User
    ) -> None:
        """
        删除客户（仅管理员）。

        Args:
            client_id: 客户主键
            current_user: 当前用户
        """
        client = await self.get_client_by_id(client_id, current_user)

        # 权限检查：只有管理员可以删除客户
        if current_user.role != UserRole.ADMIN:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="只有管理员可以删除客户"
            )

        await self.db.delete(client)
        await self.db.flush()
