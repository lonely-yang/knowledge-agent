import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


# -------------------------- 用户表 --------------------------
class UserModel(Base):
    __tablename__ = "kh_user"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    password = Column(String(60), nullable=False, comment="bcrypt密码哈希 cost=12")
    email = Column(String(255), nullable=False, unique=True)
    create_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    update_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


# -------------------------- 角色表 --------------------------
class RoleModel(Base):
    __tablename__ = "kh_role"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    role_name = Column(String(50), nullable=False)
    role_code = Column(String(50), nullable=False, unique=True)
    description = Column(String(255), nullable=False)
    create_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    update_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


# -------------------------- 用户角色关联表 --------------------------
class UserRoleModel(Base):
    __tablename__ = "kh_user_role"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(50), nullable=False)
    role_id = Column(String(50), nullable=False)
    create_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
