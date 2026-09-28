import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


# -------------------------- 权限表(树形) --------------------------
class PermissionModel(Base):
    __tablename__ = "kh_permission"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    parent_id = Column(Integer, nullable=False, default=0, comment="0=根节点")
    permission_name = Column(String(50), nullable=False)
    permission_code = Column(String(50), nullable=False, unique=True)
    permission_type = Column(Integer, nullable=False, default=2, comment="1=目录 2=菜单/按钮")
    create_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


# -------------------------- 角色权限关联表 --------------------------
class RolePermissionModel(Base):
    __tablename__ = "kh_role_permission"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    role_id = Column(String(50), nullable=False)
    permission_id = Column(String(50), nullable=False)
    create_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
