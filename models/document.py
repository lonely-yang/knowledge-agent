"""
使用sqlalchemy 创建pg的文档元数据表
"""
from sqlalchemy import Column, String, BigInteger, Integer, TIMESTAMP, SmallInteger

from core.database import Base


# ----------------- 文章表，列表展示 -----------
class KhDocument(Base):
    __tablename__ = 'kh_document'
    id = Column(BigInteger,primary_key=True,comment='主键id')
    title=Column(String(50),comment='标题')
    content_id=Column(BigInteger,comment='关联mongoDB document_content_id')
    summary=Column(String,comment='摘要')
    doc_type=Column(String,comment='文件类型')
    status=Column(SmallInteger,comment='状态（0 草稿/ 1 已发布 / 2 已归档 / 3 审核中）',default=0)
    publish_time=Column(TIMESTAMP,comment='发布时间')
    create_at=Column(TIMESTAMP,comment='创建时间')
    author_id=Column(Integer,comment='作者用户ID')
    team_id=Column(Integer,comment='归属部门ID(仅标记,不影响可见性)')
    is_public=Column(SmallInteger,comment='是否公开（0 否/ 1 是,非公开仅作者可见）',default=0,nullable=False)
    idx_status=Column(SmallInteger,comment='INDEX流程状态（NULL未开始/ 0 解析中 / 1 成功 / 2 失败）')
    rag_status=Column(SmallInteger,comment='RAG流程状态（NULL未开始/ 0 解析中 / 1 成功 / 2 失败）')
    kg_status=Column(SmallInteger,comment='KG流程状态（NULL未开始/ 0 解析中 / 1 成功 / 2 失败）')
