import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SubmitReviewDTO(BaseModel):
    doc_id: int


class ReviewActionDTO(BaseModel):
    task_id: int
    result: int = 1  # 1通过 2驳回
    comment: Optional[str] = None


class ReviewTaskRespDTO(BaseModel):
    id: int
    doc_id: int
    title: Optional[str] = None
    reviewer_id: Optional[int] = None
    reviewer_name: Optional[str] = None
    review_result: Optional[int] = None
    review_comment: Optional[str] = None
    before_status: int
    reviewed_at: Optional[datetime.datetime] = None
    create_at: datetime.datetime
    can_review: Optional[bool] = None
    model_config = ConfigDict(from_attributes=True)


class ReviewPageRespDTO(BaseModel):
    total: int
    page: int
    page_size: int
    list: list[ReviewTaskRespDTO]
