from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, create_pg_tables
from models import UserModel, RoleModel, UserRoleModel
from schemas.user import (
    AddRoleDTO, BindRoleDTO, LoginDTO, RefreshTokenDTO, RegisterDTO,
    RoleRespDTO, UpdateUserDTO, UserRespDTO,
)
from utils.auth import create_access_token, create_refresh_token, decode_token
from utils.hashing import get_password_hash, verify_password

user_router = APIRouter(prefix='/user', tags=['用户'])
role_router = APIRouter(prefix='/role', tags=['角色'])


# -------------------------- 鉴权 --------------------------
async def get_current_user(authorization: Optional[str] = Header(None), db: AsyncSession = Depends(get_db)) -> UserModel:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少token")
    payload = decode_token(authorization[7:], "access")
    if not payload:
        raise HTTPException(status_code=401, detail="token无效或已过期")
    user = await db.get(UserModel, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


# -------------------------- 建表 --------------------------
@user_router.get('/create_table')
async def create_user_tables():
    return await create_pg_tables(
        tables=[UserModel.__table__, RoleModel.__table__, UserRoleModel.__table__]
    )


# -------------------------- 用户接口 --------------------------
async def get_user_by_username(db: AsyncSession, username: str):
    stmt = select(UserModel).where(UserModel.username == username)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


@user_router.post('/register', response_model=UserRespDTO)
async def register_api(dto: RegisterDTO, db: AsyncSession = Depends(get_db)):
    """用户注册"""
    username = dto.username.strip()
    email = dto.email.strip()
    if not username or not email:
        raise HTTPException(status_code=400, detail="用户名和邮箱不能为空")
    if len(dto.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度至少6位")
    if await get_user_by_username(db, username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    stmt = select(UserModel).where(UserModel.email == email)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="邮箱已存在")
    user = UserModel(username=username, password=get_password_hash(dto.password), email=email)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@user_router.post('/login')
async def login_api(dto: LoginDTO, db: AsyncSession = Depends(get_db)):
    """用户登录，返回 JWT token"""
    user = await get_user_by_username(db, dto.username)
    if not user or not verify_password(dto.password, user.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user.id, user.username)
    refresh_token = create_refresh_token(user.id, user.username)
    return {
        "token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserRespDTO.model_validate(user),
    }



@user_router.post('/refresh')
async def refresh_token_api(dto: RefreshTokenDTO, db: AsyncSession = Depends(get_db)):
    """用 refresh token 换取新的 access token"""
    payload = decode_token(dto.refresh_token, "refresh")
    if not payload:
        raise HTTPException(status_code=401, detail="refresh token无效或已过期")
    user = await db.get(UserModel, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    token = create_access_token(user.id, user.username)
    return {"token": token, "token_type": "bearer"}


@user_router.delete('/del_user')
async def del_user_api(user_id: int, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """删除用户，同时清理其角色关联"""
    user = await db.get(UserModel, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    await db.execute(delete(UserRoleModel).where(UserRoleModel.user_id == str(user_id)))
    await db.delete(user)
    await db.commit()
    return {"msg": "删除成功"}


@user_router.put('/update_user', response_model=UserRespDTO)
async def update_user_api(user_id: int, dto: UpdateUserDTO, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """修改用户，只更新传入的字段"""
    user = await db.get(UserModel, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    update_data = {k: v for k, v in dto.model_dump(exclude_unset=True).items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="没有要修改的字段")
    if "username" in update_data and update_data["username"] != user.username:
        if await get_user_by_username(db, update_data["username"]):
            raise HTTPException(status_code=400, detail="用户名已存在")
    if "email" in update_data and update_data["email"] != user.email:
        stmt = select(UserModel).where(UserModel.email == update_data["email"])
        if (await db.execute(stmt)).scalar_one_or_none():
            raise HTTPException(status_code=400, detail="邮箱已存在")
    if "password" in update_data:
        if len(update_data["password"]) < 6:
            raise HTTPException(status_code=400, detail="密码长度至少6位")
        update_data["password"] = get_password_hash(update_data["password"])
    for key, value in update_data.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return user


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
