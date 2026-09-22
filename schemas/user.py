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


class RoleRespDTO(BaseModel):
    id: int
    role_name: str
    role_code: str
    description: str
    model_config = ConfigDict(from_attributes=True)
