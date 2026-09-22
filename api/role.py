from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from models import UserModel, RoleModel, UserRoleModel
from schemas.user import AddRoleDTO, BindRoleDTO, RoleRespDTO

role_router = APIRouter(prefix='/role', tags=['角色'])


# -------------------------- 角色接口 --------------------------
@role_router.post('/add_role', response_model=RoleRespDTO)
async def add_role_api(dto: AddRoleDTO, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """新增角色"""
    stmt = select(RoleModel).where(RoleModel.role_code == dto.role_code)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="角色编码已存在")
    role = RoleModel(**dto.model_dump())
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


@role_router.delete('/del_role')
async def del_role_api(role_id: int, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """删除角色，同时清理其用户关联"""
    role = await db.get(RoleModel, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    await db.execute(delete(UserRoleModel).where(UserRoleModel.role_id == str(role_id)))
    await db.delete(role)
    await db.commit()
    return {"msg": "删除成功"}


@role_router.post('/bind_role')
async def bind_role_api(dto: BindRoleDTO, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """给用户绑定角色"""
    if not await db.get(UserModel, dto.user_id):
        raise HTTPException(status_code=404, detail="用户不存在")
    if not await db.get(RoleModel, dto.role_id):
        raise HTTPException(status_code=404, detail="角色不存在")
    stmt = select(UserRoleModel).where(
        UserRoleModel.user_id == str(dto.user_id), UserRoleModel.role_id == str(dto.role_id)
    )
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该用户已绑定此角色")
    rel = UserRoleModel(user_id=str(dto.user_id), role_id=str(dto.role_id))
    db.add(rel)
    await db.commit()
    return {"msg": "绑定成功"}


@role_router.delete('/unbind_role')
async def unbind_role_api(user_id: int, role_id: int, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """给用户解绑角色"""
    stmt = delete(UserRoleModel).where(
        UserRoleModel.user_id == str(user_id), UserRoleModel.role_id == str(role_id)
    )
    res = await db.execute(stmt)
    await db.commit()
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="绑定关系不存在")
    return {"msg": "解绑成功"}
