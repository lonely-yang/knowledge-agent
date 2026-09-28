import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


# -------------------------- 部门团队表 --------------------------
class TeamModel(Base):
    __tablename__ = "kh_team"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    team_name = Column(String(50), nullable=False)
    team_code = Column(String(50), nullable=False, unique=True)
    description = Column(String(255), nullable=False)
    member_count = Column(Integer, nullable=False, default=0)
    status = Column(Integer, nullable=False, default=1, comment="0=禁用 1=启用")
    create_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    update_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


# -------------------------- 部门成员关联表 --------------------------
class TeamMemberModel(Base):
    __tablename__ = "kh_team_member"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    team_id = Column(String(50), nullable=False)
    user_id = Column(String(50), nullable=False)
    create_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
