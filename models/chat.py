import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, JSON

from core.database import Base


# -------------------------- 会话表 --------------------------
class AiSessionModel(Base):
    __tablename__ = "kh_ai_session"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='会话ID')
    user_id = Column(Integer, nullable=False, index=True, comment='所属用户ID')
    title = Column(String(255), nullable=False, comment='会话标题')
    create_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    update_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


# -------------------------- 消息表 --------------------------

class AiMessageModel(Base):
    __tablename__ = "kh_ai_message"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # 外键:删除会话时数据库级联删除其消息(ondelete='CASCADE')
    session_id = Column(Integer, ForeignKey('kh_ai_session.id', ondelete='CASCADE'), index=True, nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    sources = Column(JSON, nullable=False)
    create_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
