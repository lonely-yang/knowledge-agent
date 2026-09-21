import json
import asyncio
from aio_pika.abc import AbstractIncomingMessage
from .config import settings
from crud.rabbitmq.connection import rmq_manager
from crud.es.create import add_data,KnowledgeDoc
from crud.mongodb import get_mongo_doc_api
from crud.neo4j.create import insert_neo4j_table
from utils.split_file import split_doc
# ---------------------- Handler ----------------------
async def handle_index_msg(message: AbstractIncomingMessage):
    async with message.process():
        payload = json.loads(message.body.decode("utf-8"))
        meta = payload["meta"]
        content = payload["content"]
        # TODO: 索引业务
        # pg 的 tags 是逗号分隔字符串，ES 的 tags 是 keyword 数组
        if meta.get('tags'):
            meta['tags'] = [t for t in meta['tags'].split(',') if t]
        docs = KnowledgeDoc(**meta, content=content)
        doc_id = meta.get('id')
        await add_data(docs, doc_id)

async def handle_rag_msg(message: AbstractIncomingMessage):
    async with message.process():
        payload = json.loads(message.body.decode("utf-8"))
        doc_id = payload["doc_id"]
        meta = payload["meta"]
        # TODO: RAG切片、向量化
        doc = await get_mongo_doc_api(doc_id)
        await split_doc(doc_id,meta,doc)


async def handle_kg_msg(message: AbstractIncomingMessage):
    async with message.process():
        payload = json.loads(message.body.decode("utf-8"))
        doc_id = payload["doc_id"]
        content = payload["content"]
        # TODO: KG抽取
        doc = await insert_neo4j_table(doc_id)



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

