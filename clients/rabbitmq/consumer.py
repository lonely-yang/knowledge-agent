import json
import asyncio
from aio_pika.abc import AbstractIncomingMessage
from core.config import settings
from core.database import SessionLocal
from clients.es_client import add_data
from clients.neo4j_client import driver
from clients.rabbitmq.connection import rmq_manager
from schemas.search import KnowledgeDoc
from services.content_service import get_mongo_doc
from services.document_service import update_flow_status
from services.graph_service import create_graph_doc
from utils.split_file import split_doc


async def _write_flow(doc_id, flow: str, status: int):
    """回写单个 MQ 流程结果到 kh_document;doc_id 为空则跳过"""
    if not doc_id:
        return
    async with SessionLocal() as session:
        await update_flow_status(session, int(doc_id), flow, status)

# ---------------------- Handler ----------------------
async def handle_index_msg(message: AbstractIncomingMessage):
    async with message.process():
        payload = json.loads(message.body.decode("utf-8"))
        meta = payload["meta"]
        content = payload["content"]
        doc_id = meta.get('id')
        try:
            # pg 的 tags 是逗号分隔字符串，ES 的 tags 是 keyword 数组
            if meta.get('tags'):
                meta['tags'] = [t for t in meta['tags'].split(',') if t]
            docs = KnowledgeDoc(**meta, content=content)
            await add_data(docs, doc_id)
        except Exception:
            await _write_flow(doc_id, 'index', 2)
            raise
        await _write_flow(doc_id, 'index', 1)

async def handle_rag_msg(message: AbstractIncomingMessage):
    async with message.process():
        payload = json.loads(message.body.decode("utf-8"))
        doc_id = payload["doc_id"]
        meta = payload["meta"]
        try:
            # RAG切片、向量化
            doc = await get_mongo_doc(doc_id)
            await split_doc(doc_id,meta,doc)
        except Exception:
            await _write_flow(doc_id, 'rag', 2)
            raise
        await _write_flow(doc_id, 'rag', 1)


async def handle_kg_msg(message: AbstractIncomingMessage):
    async with message.process():
        payload = json.loads(message.body.decode("utf-8"))
        doc_id = payload["doc_id"]
        try:
            # KG抽取
            await create_graph_doc(doc_id, neo_driver=driver)
        except Exception:
            await _write_flow(doc_id, 'kg', 2)
            raise
        await _write_flow(doc_id, 'kg', 1)



# ---------------------- Consumer 协程 ----------------------
async def consume_index():
    # 使用独立 channel_index
    queue = await rmq_manager.declare_work_queue(rmq_manager.channel_index, settings.QUEUE_INDEX)
    while True:
        try:
            await queue.consume(handle_index_msg)
            await asyncio.Future()
        except Exception as e:
            await asyncio.sleep(2)

async def consume_rag():
    queue = await rmq_manager.declare_work_queue(rmq_manager.channel_rag, settings.QUEUE_RAG)
    while True:
        try:
            await queue.consume(handle_rag_msg)
            await asyncio.Future()
        except Exception as e:
            await asyncio.sleep(2)

async def consume_kg():
    queue = await rmq_manager.declare_work_queue(rmq_manager.channel_kg, settings.QUEUE_KG)
    while True:
        try:
            await queue.consume(handle_kg_msg)
            await asyncio.Future()
        except Exception as e:
            await asyncio.sleep(2)
