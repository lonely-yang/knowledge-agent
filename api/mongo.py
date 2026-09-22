from fastapi import APIRouter

from core.database import SessionLocal
from schemas.content import DocContent
from services.content_service import add_mongo_doc, get_mongo_doc, update_mongo_doc
from services.document_service import delete_kh_doc

mongo_router = APIRouter(prefix='/mongo', tags=['MongoDB'])


@mongo_router.get('/check')
async def get_mongo_doc_api(doc_id: int):
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
