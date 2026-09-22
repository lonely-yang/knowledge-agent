from datetime import datetime

from fastapi import APIRouter, HTTPException,Depends
from pydantic import ValidationError
from models.document_content import KHDocument, DocContent,settings
from beanie import init_beanie
from beanie.operators import Set
from pymongo import AsyncMongoClient
from core.database import SessionLocal

mongo_router = APIRouter(prefix='/mongo', tags=['MongoDB'])

# ========== 数据库初始化：应用启动时只执行一次 ==========
async def init_mongodb():
    """在 app startup 事件中调用，全局一次性初始化beanie"""
    client = AsyncMongoClient(settings.MONGO_URI)
    await init_beanie(
        database=client[settings.DB_NAME],
        document_models=[KHDocument],
    )
    return client

@mongo_router.get('/check')
async def get_mongo_doc_api(doc_id: int):
    doc = await KHDocument.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail='文档不存在')
    return doc


@mongo_router.post('/add_doc')
async def add_mongo_doc_api(cfg: DocContent):
    data = cfg.model_dump(by_alias=False, exclude_none=True)
    if 'id' not in data:
        raise HTTPException(status_code=422, detail='缺少 _id（对应 kh_document.content_id）')
    data.setdefault('content_len', len(data.get('content') or ''))
    data.setdefault('content_summary', '')
    now = datetime.now()
    data.setdefault('create_at', now)
    data.setdefault('update_at', now)
    try:
        doc = KHDocument(**data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await doc.insert()
    return doc


@mongo_router.put('/update_doc')
async def update_mongo_doc_api(doc_id: int, cfg: DocContent):
    doc = await KHDocument.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail='文档不存在')
    update_data = cfg.model_dump(by_alias=False, exclude_unset=True)
    update_data.pop('id', None)
    if not update_data:
        raise HTTPException(status_code=422, detail='没有可更新的字段')
    await doc.update(Set(update_data))
    return await KHDocument.get(doc_id)


@mongo_router.delete('/del_doc')
async def delete_mongo_doc_api(doc_id: int):
    doc = await KHDocument.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail='文档不存在')
    doc_dump = doc.model_dump()

    async with SessionLocal() as session:
        from crud.postgre import delete_kh_doc
        await delete_kh_doc(session,doc_id=doc_dump['document_id'])
        await doc.delete()
    return {"msg": "删除成功"}
