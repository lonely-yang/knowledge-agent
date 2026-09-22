from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models import UserModel
from utils.auth import decode_token


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
