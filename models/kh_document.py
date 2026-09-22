"""
使用sqlalchemy 创建pg的文档元数据表
"""
from sqlalchemy import Column, String, BigInteger, TIMESTAMP, SmallInteger

from core.database import Base


# ----------------- 文章表，列表展示 -----------
class KhDocument(Base):
    __tablename__ = 'kh_document'
    id = Column(BigInteger,primary_key=True,comment='主键id')
    title=Column(String(50),comment='标题')
    content_id=Column(BigInteger,comment='关联mongoDB document_content_id')
    summary=Column(String,comment='摘要')
    doc_type=Column(String,comment='文件类型')
    status=Column(SmallInteger,comment='状态（0 草稿/ 1 已发布 / 2 已归档）',default=0)
    publish_time=Column(TIMESTAMP,comment='发布时间')
    create_at=Column(TIMESTAMP,comment='创建时间')

