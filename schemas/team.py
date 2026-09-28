import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AddTeamDTO(BaseModel):
    team_name: str
    team_code: str
    description: str = ''


class UpdateTeamDTO(BaseModel):
    team_name: Optional[str] = None
    team_code: Optional[str] = None
    description: Optional[str] = None
    status: Optional[int] = None


class AddTeamMemberDTO(BaseModel):
    team_id: int
    user_id: int


class TeamRespDTO(BaseModel):
    id: int
    team_name: str
    team_code: str
    description: str
    member_count: int
    status: int
    create_at: datetime.datetime
    update_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)


class TeamPageRespDTO(BaseModel):
    total: int
    page: int
    page_size: int
    list: list[TeamRespDTO]


class TeamMemberRespDTO(BaseModel):
    team_id: int
    user_id: int
    username: str
    email: str
    create_at: datetime.datetime
