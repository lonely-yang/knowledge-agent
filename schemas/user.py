import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RegisterDTO(BaseModel):
    username: str
    password: str
    email: str


class LoginDTO(BaseModel):
    username: str
    password: str


class RefreshTokenDTO(BaseModel):
    refresh_token: str


class UpdateUserDTO(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    email: Optional[str] = None


class AddRoleDTO(BaseModel):
    role_name: str
    role_code: str
    description: str


class BindRoleDTO(BaseModel):
    user_id: int
    role_id: int


class UserRespDTO(BaseModel):
    id: int
    username: str
    email: str
    create_at: datetime.datetime
    update_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)


class UserWithRolesRespDTO(UserRespDTO):
    role_codes: list[str] = []
    team_name: Optional[str] = None


class UserPageRespDTO(BaseModel):
    total: int
    page: int
    page_size: int
    list: list[UserWithRolesRespDTO]


class AssignRolesDTO(BaseModel):
    user_id: int
    role_codes: list[str]


class CreateUserDTO(BaseModel):
    username: str
    password: str
    email: str
    role_codes: list[str] = []


class UpdateRoleDTO(BaseModel):
    role_name: Optional[str] = None
    role_code: Optional[str] = None
    description: Optional[str] = None


class RoleRespDTO(BaseModel):
    id: int
    role_name: str
    role_code: str
    description: str
    create_at: datetime.datetime
    update_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)


class RoleWithUsersRespDTO(RoleRespDTO):
    users: list[UserRespDTO] = []
