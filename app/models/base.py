"""
ORM 基类与公共枚举、密码工具。
"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Enum, Text, Index, \
    UniqueConstraint, Date
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid
from passlib.context import CryptContext
from app.core.utils import get_app_now_naive

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
Base = declarative_base()


class UserRole(str, enum.Enum):
    """用户角色：ADMIN 管理员 / CLIENT 客户。"""
    ADMIN = "admin"
    CLIENT = "client"
