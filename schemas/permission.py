from pydantic import BaseModel, ConfigDict


class PermissionNodeDTO(BaseModel):
    id: int
    parent_id: int
    permission_name: str
    permission_code: str
    permission_type: int
    children: list['PermissionNodeDTO'] = []
    model_config = ConfigDict(from_attributes=True)


class AssignPermissionDTO(BaseModel):
    role_id: int
    permission_ids: list[int]


class RolePermissionRespDTO(BaseModel):
    role_id: int
    permission_ids: list[int]
