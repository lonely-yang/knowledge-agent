import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


# -------------------------- 审核任务表 --------------------------
class ReviewTaskModel(Base):
    __tablename__ = "kh_review_task"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    doc_id = Column(Integer, nullable=False)
    submitter_id = Column(Integer, nullable=False)
    reviewer_id = Column(Integer, nullable=True)
    reviewer_name = Column(String(50), nullable=True)
    review_result = Column(Integer, nullable=True, comment="NULL待审 1通过 2驳回")
    review_comment = Column(String(500), nullable=True)
    before_status = Column(Integer, nullable=False, default=0, comment="提交审核前的文档状态")
    reviewed_at = Column(DateTime, nullable=True)
    create_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
