import datetime

import jwt

from core.config import settings

ALGORITHM = settings.JWT_ALGORITHM
SECRET_KEY = settings.JWT_SECRET_KEY


def _create_token(user_id: int, username: str, token_type: str, expire_minutes: int) -> str:
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=expire_minutes)
    payload = {"sub": str(user_id), "username": username, "type": token_type, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: int, username: str) -> str:
    """签发 access token（短期，用于接口鉴权）"""
    return _create_token(user_id, username, "access", settings.JWT_EXPIRE_MINUTES)


def create_refresh_token(user_id: int, username: str) -> str:
    """签发 refresh token（长期，用于刷新 access token）"""
    return _create_token(user_id, username, "refresh", settings.JWT_REFRESH_EXPIRE_MINUTES)


def decode_token(token: str, token_type: str) -> dict:
    """解析并校验 token 类型，无效、过期或类型不符返回空 dict"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return {}
    if payload.get("type") != token_type:
        return {}
    return payload
