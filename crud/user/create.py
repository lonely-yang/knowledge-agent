from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, DateTime, Integer, String, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import datetime

from core.database import Base, get_db, create_pg_tables
from utils.auth import create_access_token, create_refresh_token, decode_token
from utils.pwd import get_password_hash, verify_password

user_router = APIRouter(prefix='/user', tags=['用户'])
role_router = APIRouter(prefix='/role', tags=['角色'])


# -------------------------- 用户表 --------------------------
class KHUSERModel(Base):
    __tablename__ = "kh_user"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    password = Column(String(60), nullable=False, comment="bcrypt密码哈希 cost=12")
    email = Column(String(255), nullable=False, unique=True)
    create_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    update_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


# -------------------------- 角色表 --------------------------
class KHROLEModel(Base):
    __tablename__ = "kh_role"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    role_name = Column(String(50), nullable=False)
    role_code = Column(String(50), nullable=False, unique=True)
    description = Column(String(255), nullable=False)


# -------------------------- 用户角色关联表 --------------------------
class KHUSERROLEModel(Base):
    __tablename__ = "kh_user_role"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(50), nullable=False)
    role_id = Column(String(50), nullable=False)
    create_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


# -------------------------- DTO --------------------------
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


# -------------------------- 鉴权 --------------------------
async def get_current_user(authorization: Optional[str] = Header(None), db: AsyncSession = Depends(get_db)) -> KHUSERModel:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少token")
    payload = decode_token(authorization[7:], "access")
    if not payload:
        raise HTTPException(status_code=401, detail="token无效或已过期")
    user = await db.get(KHUSERModel, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


# -------------------------- 建表 --------------------------
@user_router.get('/create_table')
async def create_user_tables():
    return await create_pg_tables(
        tables=[KHUSERModel.__table__, KHROLEModel.__table__, KHUSERROLEModel.__table__]
    )


# -------------------------- 用户接口 --------------------------
async def get_user_by_username(db: AsyncSession, username: str):
    stmt = select(KHUSERModel).where(KHUSERModel.username == username)
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
    stmt = select(KHUSERModel).where(KHUSERModel.email == email)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="邮箱已存在")
    user = KHUSERModel(username=username, password=get_password_hash(dto.password), email=email)
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
    user = await db.get(KHUSERModel, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    token = create_access_token(user.id, user.username)
    return {"token": token, "token_type": "bearer"}


@user_router.delete('/del_user')
async def del_user_api(user_id: int, db: AsyncSession = Depends(get_db), current_user: KHUSERModel = Depends(get_current_user)):
    """删除用户，同时清理其角色关联"""
    user = await db.get(KHUSERModel, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    await db.execute(delete(KHUSERROLEModel).where(KHUSERROLEModel.user_id == str(user_id)))
    await db.delete(user)
    await db.commit()
    return {"msg": "删除成功"}


@user_router.put('/update_user', response_model=UserRespDTO)
async def update_user_api(user_id: int, dto: UpdateUserDTO, db: AsyncSession = Depends(get_db), current_user: KHUSERModel = Depends(get_current_user)):
    """修改用户，只更新传入的字段"""
    user = await db.get(KHUSERModel, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    update_data = {k: v for k, v in dto.model_dump(exclude_unset=True).items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="没有要修改的字段")
    if "username" in update_data and update_data["username"] != user.username:
        if await get_user_by_username(db, update_data["username"]):
            raise HTTPException(status_code=400, detail="用户名已存在")
    if "email" in update_data and update_data["email"] != user.email:
        stmt = select(KHUSERModel).where(KHUSERModel.email == update_data["email"])
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
async def add_role_api(dto: AddRoleDTO, db: AsyncSession = Depends(get_db), current_user: KHUSERModel = Depends(get_current_user)):
    """新增角色"""
    stmt = select(KHROLEModel).where(KHROLEModel.role_code == dto.role_code)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="角色编码已存在")
    role = KHROLEModel(**dto.model_dump())
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


@role_router.delete('/del_role')
async def del_role_api(role_id: int, db: AsyncSession = Depends(get_db), current_user: KHUSERModel = Depends(get_current_user)):
    """删除角色，同时清理其用户关联"""
    role = await db.get(KHROLEModel, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    await db.execute(delete(KHUSERROLEModel).where(KHUSERROLEModel.role_id == str(role_id)))
    await db.delete(role)
    await db.commit()
    return {"msg": "删除成功"}


@role_router.post('/bind_role')
async def bind_role_api(dto: BindRoleDTO, db: AsyncSession = Depends(get_db), current_user: KHUSERModel = Depends(get_current_user)):
    """给用户绑定角色"""
    if not await db.get(KHUSERModel, dto.user_id):
        raise HTTPException(status_code=404, detail="用户不存在")
    if not await db.get(KHROLEModel, dto.role_id):
        raise HTTPException(status_code=404, detail="角色不存在")
    stmt = select(KHUSERROLEModel).where(
        KHUSERROLEModel.user_id == str(dto.user_id), KHUSERROLEModel.role_id == str(dto.role_id)
    )
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该用户已绑定此角色")
    rel = KHUSERROLEModel(user_id=str(dto.user_id), role_id=str(dto.role_id))
    db.add(rel)
    await db.commit()
    return {"msg": "绑定成功"}


@role_router.delete('/unbind_role')
async def unbind_role_api(user_id: int, role_id: int, db: AsyncSession = Depends(get_db), current_user: KHUSERModel = Depends(get_current_user)):
    """给用户解绑角色"""
    stmt = delete(KHUSERROLEModel).where(
        KHUSERROLEModel.user_id == str(user_id), KHUSERROLEModel.role_id == str(role_id)
    )
    res = await db.execute(stmt)
    await db.commit()
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="绑定关系不存在")
    return {"msg": "解绑成功"}
