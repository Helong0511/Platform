"""
客户服务层
封装客户相关的业务逻辑
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
    """客户服务"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Client)

    async def list_clients(
        self,
        *,
        page: int = 1,
        page_size: int = 10,
        company_name: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Client], int]:
        """分页客户列表（管理员）。"""
        query = select(Client).options(selectinload(Client.user))
        count_query = select(func.count(Client.id))

        if company_name:
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
        根据ID获取客户详情
        
        Args:
            client_id: 客户ID
            current_user: 当前用户（用于权限检查）
            include_user: 是否包含用户信息
        
        Returns:
            Client: 客户对象
        
        Raises:
            HTTPException: 如果客户不存在或没有权限
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
        根据用户ID获取客户列表
        
        Args:
            user_id: 用户ID
            current_user: 当前用户（用于权限检查）
        
        Returns:
            List[Client]: 客户列表
        
        Raises:
            HTTPException: 如果没有权限
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
        创建新客户
        
        Args:
            client_data: 客户数据
            current_user: 当前用户（用于权限检查）
        
        Returns:
            Client: 创建的客户对象
        
        Raises:
            HTTPException: 如果没有权限
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
        await self.db.refresh(client)

        return client

    async def update_client(
            self,
            client_id: int,
            client_data: Dict[str, Any],
            current_user: User
    ) -> Client:
        """
        更新客户信息
        
        Args:
            client_id: 客户ID
            client_data: 更新的客户数据
            current_user: 当前用户（用于权限检查）
        
        Returns:
            Client: 更新后的客户对象
        
        Raises:
            HTTPException: 如果客户不存在或没有权限
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
        await self.db.refresh(client)

        return client

    async def delete_client(
            self,
            client_id: int,
            current_user: User
    ) -> None:
        """
        删除客户
        
        Args:
            client_id: 客户ID
            current_user: 当前用户（用于权限检查）
        
        Raises:
            HTTPException: 如果客户不存在或没有权限
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
