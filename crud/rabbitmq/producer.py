import json
import aio_pika
from aio_pika import Message
from .connection import rmq_manager
from .config import settings

async def publish_index(meta: dict, content: str):
    """INDEX队列：整篇元数据+正文，使用channel_index"""
    payload = {
        "meta": meta,
        "content": content
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    msg = Message(body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
    await rmq_manager.channel_index.default_exchange.publish(
        msg, routing_key=settings.QUEUE_INDEX
    )

async def publish_rag(doc_id: int,meta:dict):
    """BY_DOC_IDS队列：文档ID，使用channel_rag"""
    payload = {"doc_id": doc_id,'meta':meta}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    msg = Message(body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
    await rmq_manager.channel_rag.default_exchange.publish(
        msg, routing_key=settings.QUEUE_RAG
    )

async def publish_kg(doc_id: int, content: str):
    """BUILD_BY_DOC_IDS队列：文档ID，使用channel_kg"""
    payload = {"doc_id": doc_id, "content": content}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    msg = Message(body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
    await rmq_manager.channel_kg.default_exchange.publish(
        msg, routing_key=settings.QUEUE_KG
    )
