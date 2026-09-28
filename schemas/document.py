from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class KhDocumentRespDTO(BaseModel):
    id: Optional[int] = None
    title:Optional[str] = None
    content_id: Optional[int] = None
    summary:Optional[str] = None
    doc_type:Optional[str] = None
    status: Optional[int] = None
    publish_time: datetime | None = datetime.now()
    create_at: datetime | None = datetime.now()
    author_id: Optional[int] = None
    team_id: Optional[int] = None
    is_public: Optional[int] = 0
    content: Optional[str] = Field(default=None, exclude=True, description='正文，仅用于同步MongoDB，不落PG表')
    uploader: Optional[str] = Field(default=None, description='上传人用户名，关联kh_user实时查出，不落PG表')
    parse_status: Optional[int] = Field(default=None, description='文档解析总状态（0未解析/ 1 解析中 / 2 解析完成 / 3 解析失败），由3个MQ流程聚合，不落PG表')
    model_config = ConfigDict(from_attributes=True)

class KhDocumentRespDTOUpdate(BaseModel):
    title:Optional[str] = None
    content_id:Optional[int] = None
    summary:Optional[str] = None
    doc_type:Optional[str] = None
    status: Optional[int] = None
    publish_time: datetime | None= datetime.now()
    create_at: datetime | None= datetime.now()
    author_id: Optional[int] = None
    team_id: Optional[int] = None
    is_public: Optional[int] = None
    content: Optional[str] = Field(default=None, exclude=True, description='正文，仅用于同步MongoDB，不落PG表')
    model_config = ConfigDict(from_attributes=True)
