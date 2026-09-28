from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, create_pg_tables as db_create_pg_tables
from core.security import get_current_user
from models import AiSessionModel, AiMessageModel, UserModel
from schemas.chat import SessionCreateDTO, SessionRespDTO, SessionUpdateDTO

chat_router = APIRouter(prefix='/chat', tags=['对话'])


# -------------------------- 建表 --------------------------
@chat_router.get('/create_chat_table')
async def create_pg_tables():
    return await db_create_pg_tables(
        tables=[AiSessionModel.__table__, AiMessageModel.__table__]
    )


# -------------------------- 会话 CRUD --------------------------
async def _get_owned_session(db: AsyncSession, session_id: int, user_id: int) -> AiSessionModel:
    """取会话并校验归属，非本人会话一律 404，避免泄露存在性"""
    session = await db.get(AiSessionModel, session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail='会话不存在')
    return session


@chat_router.post('/session', response_model=SessionRespDTO)
async def create_session_api(dto: SessionCreateDTO, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """新建会话"""
    title = dto.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail='会话标题不能为空')
    session = AiSessionModel(user_id=current_user.id, title=title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@chat_router.get('/session', response_model=list[SessionRespDTO])
async def list_sessions_api(db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """当前用户的会话列表"""
    stmt = select(AiSessionModel).where(AiSessionModel.user_id == current_user.id).order_by(AiSessionModel.id.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@chat_router.get('/session/{session_id}', response_model=SessionRespDTO)
async def get_session_api(session_id: int, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """查询单个会话"""
    return await _get_owned_session(db, session_id, current_user.id)


@chat_router.put('/session/{session_id}', response_model=SessionRespDTO)
async def update_session_api(session_id: int, dto: SessionUpdateDTO, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """修改会话标题"""
    session = await _get_owned_session(db, session_id, current_user.id)
    title = dto.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail='会话标题不能为空')
    session.title = title
    await db.commit()
    await db.refresh(session)
    return session


@chat_router.delete('/session/{session_id}')
async def delete_session_api(session_id: int, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """删除会话，其消息一并删除（显式删除 + 外键 ON DELETE CASCADE 双保险）"""
    session = await _get_owned_session(db, session_id, current_user.id)
    await db.execute(delete(AiMessageModel).where(AiMessageModel.session_id == session_id))
    await db.delete(session)
    await db.commit()
    return {"msg": "删除成功"}
