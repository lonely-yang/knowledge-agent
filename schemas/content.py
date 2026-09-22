from datetime import datetime

from pydantic import Field, BaseModel


# pydantic 请求mox（新增/更新）
class DocContent(BaseModel):
    id:int|None=Field(description='主键id,对应kh_document.content_id',alias='_id')
    document_id: int | None = Field(description='对应kh_document.id')
    content: str | None = Field(default=None, description='Markdown 正文')
    content_len: int | None = Field(default=None, description='字符数')
    content_summary: str | None = Field(default=None, description='预览摘要')
    create_at: datetime | None = Field(default=None, description='创建时间')
    update_at: datetime | None = Field(default=None, description='更新时间')
