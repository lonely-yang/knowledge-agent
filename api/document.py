from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, create_pg_tables, drop_pg_tables
from models import KhDocument
from schemas.content import DocContent
from schemas.document import KhDocumentRespDTO, KhDocumentRespDTOUpdate
from services.content_service import add_mongo_doc, delete_mongo_doc, update_mongo_doc
from services.document_service import create_kh_doc, delete_kh_doc, get_doc, update_kh_doc

pg_router = APIRouter(prefix='/pg',tags=['PG数据库'])


# 生成表
@pg_router.post('/create_table',description='权限操作，切勿使用')
async def create_table_api():
    return await create_pg_tables(tables=[KhDocument.__table__])


# 删除表
@pg_router.post('/drop_table',description='权限操作，切勿使用')
async def drop_table_api():
    return await drop_pg_tables(tables=[KhDocument.__table__])


# 查询 doc
@pg_router.get('/check',response_model=KhDocumentRespDTO)
async def get_doc_api(id:int,db:AsyncSession=Depends(get_db)):
    doc = await get_doc(db,id)
    return doc


@pg_router.get('/check_all',response_model=list[KhDocumentRespDTO])
async def get_all_docs(db:AsyncSession=Depends(get_db)):
    stmt = select(KhDocument)
    result = await db.execute(stmt)
    docs = result.scalars().all()
    return docs


# 新增doc
@pg_router.post('/add_doc',response_model=KhDocumentRespDTO)
async def add_doc_api(cfg:KhDocumentRespDTO,db:AsyncSession=Depends(get_db)):
    doc = await create_kh_doc(db,cfg)
    # 同步 MongoDB（原 create_kh_doc 内联逻辑，编排上移 api 层）
    if cfg.content:
        mongo_cfg = DocContent(
            _id=doc.content_id,
            document_id=doc.id,
            content=cfg.content,
            content_summary=doc.summary
        )
        await add_mongo_doc(mongo_cfg)
    return doc


# 删除doc
@pg_router.delete('/del_doc')
async def delete_kh_doc_api(doc_id:int,db:AsyncSession=Depends(get_db)):
    res = await delete_kh_doc(db,doc_id)
    # 同步删除 MongoDB（原 delete_kh_doc 内联逻辑，编排上移 api 层）
    if res:
        await delete_mongo_doc(doc_id)
    return res


# 修改doc
@pg_router.put('/update_doc',response_model=KhDocumentRespDTO)
async def update_kh_doc_api(dto:KhDocumentRespDTOUpdate,doc_id:int,db:AsyncSession=Depends(get_db)):
    doc = await get_doc(db,doc_id)
    if not doc:
        return None
    # 同步 MongoDB（原 update_kh_doc 内联逻辑，先于 PG 字段更新，编排上移 api 层）
    if doc.content_id is not None and dto.content:
        mongo_cfg = DocContent(
            _id=doc.content_id,
            document_id=doc.id,
            content=dto.content,
            content_summary=doc.summary,
        )
        await update_mongo_doc(doc_id=doc.content_id,cfg=mongo_cfg)
    return await update_kh_doc(db,dto,doc_id)
