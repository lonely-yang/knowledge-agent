from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class KhDocumentRespDTO(BaseModel):
    id:int
    title:Optional[str] = None
    content_id:int = None
    summary:Optional[str] = None
    doc_type:Optional[str] = None
    status:int = None
    publish_time: datetime | None = datetime.now()
    create_at: datetime | None = datetime.now()
    content: Optional[str] = Field(default=None, exclude=True, description='正文，仅用于同步MongoDB，不落PG表')
    model_config = ConfigDict(from_attributes=True)

class KhDocumentRespDTOUpdate(BaseModel):
    title:Optional[str] = None
    content_id:Optional[int] = None
    summary:Optional[str] = None
    doc_type:Optional[str] = None
    publish_time: datetime | None= datetime.now()
    create_at: datetime | None= datetime.now()
    content: Optional[str] = Field(default=None, exclude=True, description='正文，仅用于同步MongoDB，不落PG表')
    model_config = ConfigDict(from_attributes=True)
