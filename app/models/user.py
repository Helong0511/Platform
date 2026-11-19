"""
用户 ORM 模型。
"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Enum, Text, Index, \
    UniqueConstraint, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from app.core.utils import get_app_now_naive
from app.models.base import Base, UserRole
from app.core.passwords import hash_password, verify_password, password_hash_needs_upgrade

class User(Base):
    """
    用户模型
    
    存储系统用户的基本信息，包括登录凭证、角色权限等
    一个用户可以有多个客户（Client），通过一对多关系关联
    
    表名: users
    
    字段说明：
    - id: 用户唯一标识，自增主键
    - username: 登录用户名，唯一且必填，最大50字符
    - hashed_password: 密码哈希（新密码使用 Argon2id，兼容历史 bcrypt）
    - full_name: 用户全名，可选
    - email: 用户邮箱，唯一且可选，用于找回密码等
    - role: 用户角色，枚举类型（ADMIN/CLIENT），默认CLIENT
    - is_active: 是否激活，False时无法登录
    - login_restricted: 是否限制登录，True时显示login_message
    - login_message: 登录限制提示消息，当login_restricted=True时显示
    - created_at: 创建时间，自动设置为当前时间（北京时间）
    - updated_at: 更新时间，每次更新时自动更新为当前时间
    
    关系：
    - clients: 一对多关系，一个用户可以有多个客户
    
    方法：
    - verify_password(password): 验证密码是否正确
    - get_password_hash(password): 获取密码的哈希值
    - set_password(password): 设置用户密码（自动加密）
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='用户ID')
    username = Column(String(50), unique=True, nullable=False, comment='用户名称(登录名称)')
    hashed_password = Column('hashed_password', String(191), nullable=False, comment='用户Hash密码')
    full_name = Column(String(100), comment='用户全名')
    email = Column(String(100), unique=True, comment='用户邮箱')
    role = Column(Enum(UserRole, values_callable=lambda obj: [e.value for e in UserRole], create_constraint=True), 
                  default=UserRole.CLIENT, nullable=False,
                  comment='用户角色(ADMIN 管理员 / CLIENT 客户)')
    is_active = Column(Boolean, default=True, comment='是否激活')
    login_restricted = Column(Boolean, default=False, comment='是否限制登录')
    login_message = Column(Text, comment='登录提示消息')
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    clients = relationship("Client", back_populates="user", cascade="all, delete-orphan")

    def verify_password(self, password: str) -> bool:
        """
        验证用户密码是否正确
        
        Args:
            password: 待验证的明文密码
            
        Returns:
            bool: 密码正确返回True，否则返回False
            
        示例:
            if user.verify_password("my_password"):
                # 密码验证成功
                pass
        """
        return verify_password(password, self.hashed_password)

    def needs_password_rehash(self, password: str) -> bool:
        """判断当前已验证密码哈希是否需要并且可以安全升级。"""
        return password_hash_needs_upgrade(password, self.hashed_password)

    def get_password_hash(self, password: str) -> str:
        """
        生成当前密码哈希（Argon2id）。
        
        历史 bcrypt 哈希仅用于兼容验证；新密码不再受 bcrypt 72 字节限制。
        
        Args:
            password: 明文密码
            
        Returns:
            str: 加密后的密码哈希值
            
        示例:
            hashed = user.get_password_hash("my_password")
        """
        return hash_password(password)
    
    def set_password(self, password: str) -> None:
        """
        设置用户密码（自动加密存储）
        
        这是设置密码的推荐方法，会自动调用get_password_hash进行加密
        
        Args:
            password: 明文密码
            
        示例:
            user.set_password("new_password")
            # 密码已自动加密并存储到hashed_password字段
        """
        self.hashed_password = self.get_password_hash(password)

