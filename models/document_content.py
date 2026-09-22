from datetime import datetime
from pydantic import Field, BaseModel
from beanie import Document

from core.config import settings

# Beanie Document 模型（映射Mongo集合）
class KHDocument(Document):
    id:int
    document_id:int
    content:str
    content_len:int
    content_summary:str
    create_at:datetime
    update_at:datetime

    class Settings:
        # 对应mongo集合名称
        name = "document_content"

# pydantic 请求mox（新增/更新）
class DocContent(BaseModel):
    id:int|None=Field(description='主键id,对应kh_document.content_id',alias='_id')
    document_id: int | None = Field(description='对应kh_document.id')
    content: str | None = Field(default=None, description='Markdown 正文')
    content_len: int | None = Field(default=None, description='字符数')
    content_summary: str | None = Field(default=None, description='预览摘要')
    create_at: datetime | None = Field(default=None, description='创建时间')
    update_at: datetime | None = Field(default=None, description='更新时间')

