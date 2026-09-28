from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import SessionLocal, get_db
from core.security import can_review_doc, get_current_user
from models import KhDocument, ReviewTaskModel, UserModel
from schemas.content import DocContent
from services.content_service import add_mongo_doc, get_mongo_doc, update_mongo_doc
from services.document_service import delete_kh_doc

mongo_router = APIRouter(prefix='/mongo', tags=['MongoDB'])


@mongo_router.get('/check')
async def get_mongo_doc_api(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """文档正文(与PG详情同权限:公开、作者本人,或可审核该待审文档的用户)"""
    doc = await db.get(KhDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.is_public != 1 and doc.author_id != current_user.id:
        has_pending = (
            await db.execute(
                select(ReviewTaskModel.id).where(
                    ReviewTaskModel.doc_id == doc_id, ReviewTaskModel.review_result.is_(None)
                )
            )
        ).scalar_one_or_none()
        if not has_pending or not await can_review_doc(db, current_user, doc):
            raise HTTPException(status_code=403, detail="无权查看该文档")
    return await get_mongo_doc(doc_id)


@mongo_router.post('/add_doc')
async def add_mongo_doc_api(cfg: DocContent):
    return await add_mongo_doc(cfg)


@mongo_router.put('/update_doc')
async def update_mongo_doc_api(doc_id: int, cfg: DocContent):
    return await update_mongo_doc(doc_id, cfg)


@mongo_router.delete('/del_doc')
async def delete_mongo_doc_api(doc_id: int):
    doc = await get_mongo_doc(doc_id)
    doc_dump = doc.model_dump()
    # 同步删除 PG 侧记录（原函数内互 import 逻辑，编排上移 api 层）
    async with SessionLocal() as session:
        await delete_kh_doc(session,doc_id=doc_dump['document_id'])
    await doc.delete()
    return {"msg": "删除成功"}
