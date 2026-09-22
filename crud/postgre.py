from datetime import datetime
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from models import KhDocument
from fastapi import APIRouter
from sqlalchemy import select

from core.database import SessionLocal, get_db, create_pg_tables, drop_pg_tables
from schemas.content import DocContent
from schemas.document import KhDocumentRespDTO, KhDocumentRespDTOUpdate

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
async def get_doc(session:AsyncSession,id:int):
    doc = await session.get(KhDocument,id)
    return doc
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
async def create_kh_doc(session: AsyncSession,dto:KhDocumentRespDTO):
    # 判断类型
    if isinstance(dto, dict):
        dto_data = dict(dto)
    else:
        dto_data = dto.model_dump()
    content = dto_data.pop('content', None)
    doc = KhDocument(**dto_data)
    doc.summary = content[:100]
    now = datetime.now()
    doc.create_at = now
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    # 同步 MongoDB
    if content:
        if doc.content_id is None:
            # 未显式指定 content_id 时，用 PG 自增主键作为 Mongo _id，保证关联唯一
            doc.content_id = doc.id
            await session.commit()
            await session.refresh(doc)
        mongo_cfg = DocContent(
            _id=doc.content_id,
            document_id=doc.id,
            content=content,
            content_summary=doc.summary
        )
        from crud.mongodb import add_mongo_doc_api
        await add_mongo_doc_api(mongo_cfg)
    return doc
@pg_router.post('/add_doc',response_model=KhDocumentRespDTO)
async def add_doc_api(cfg:KhDocumentRespDTO,db:AsyncSession=Depends(get_db)):
    res = await create_kh_doc(db,cfg)
    return res
# 删除doc
async def delete_kh_doc(session:AsyncSession,doc_id:int) -> bool:
    doc = await get_doc(session, id=doc_id)
    if not doc:
        return False
    await session.delete(doc)
    await session.commit()
    from crud.mongodb import delete_mongo_doc_api
    await delete_mongo_doc_api(doc_id)
    return True
@pg_router.delete('/del_doc')
async def delete_kh_doc_api(doc_id:int,db:AsyncSession=Depends(get_db)):
    res = await delete_kh_doc(db,doc_id)
    return res
# 修改doc
async def update_kh_doc(session:AsyncSession,dto:KhDocumentRespDTOUpdate,doc_id:int) -> KhDocumentRespDTOUpdate | None:
    doc = await get_doc(session, id=doc_id)
    if not doc:
        return None
    update_data = dto.model_dump(exclude_unset=True)  # exclude_unset=True：只更新前端传过来的字段，不传的保留原值
    update_data.pop("id", None)

    # 同步 MongoDB
    if doc.content_id is not None and dto.content:
        mongo_cfg = DocContent(
            _id=doc.content_id,
            document_id=doc.id,
            content=dto.content,
            content_summary=doc.summary,
        )
        from crud.mongodb import update_mongo_doc_api
        await update_mongo_doc_api(doc_id=doc.content_id,cfg=mongo_cfg)

    # 循环赋值给数据库ORM对象
    for key, value in update_data.items():
        setattr(doc, key, value)

    await session.commit()
    await session.refresh(doc)
    doc.content = dto.content
    return doc
@pg_router.put('/update_doc',response_model=KhDocumentRespDTO)
async def update_kh_doc_api(dto:KhDocumentRespDTOUpdate,doc_id:int,db:AsyncSession=Depends(get_db)):
    res = await update_kh_doc(db,dto,doc_id)
    return res

# 拼接文件到正文 content
async def concat_content():
    pass

# 文件处理 -- 字段存储
async def pg_file_save(file_data):

    cfg = {
        'title':file_data.get('key'),
        'status':0,
        'content':file_data.get('data').get('text')
    }
    async with SessionLocal() as session:
        await create_kh_doc(session, cfg)

