"""
审核之后。文件就发布，概念状态为已发布
1.使用RabbitMQ 进行异步队列操作
    - Search 队列：INDEX （整篇元数据 + 正文）
    - RAG 队列： BY_DOC_IDS （文档ID列表）
    - KG 队列：BUILD_BY_DOC_IDS （文档 ID）
"""
from datetime import datetime

from crud.mongodb import get_mongo_doc_api
from crud.postgre import update_kh_doc,KhDocumentRespDTOUpdate
from fastapi import APIRouter
from core.database import SessionLocal
from crud.rabbitmq.producer import publish_index,publish_rag,publish_kg
publish_router = APIRouter(prefix='/knowledge_doc',tags=['发布文档'])

@publish_router.post('/publish')
async def publish_api(doc_id:int):
    #改变pg 中文档的状态
    dto = KhDocumentRespDTOUpdate(status=1)
    async with SessionLocal() as session:
        pg_data = await update_kh_doc(session,dto,doc_id)
        mondb_data = await get_mongo_doc_api(doc_id)
        # 审核 发布成功
        # 存入 es 模块
        meta = {c.name: getattr(pg_data, c.name) for c in pg_data.__table__.columns}
        meta = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in meta.items()}
        await mq_publish_es(doc_id,meta, mondb_data.content)

        return {
            'status':1,
            'meta':meta,
            'mondb_data':mondb_data,
            'msg':'文档发布成功！'
        }

async def mq_publish_es(doc_id,meta,content):
    await publish_index(meta, content)
    await publish_rag(doc_id, meta)
    await publish_kg(doc_id,content)

