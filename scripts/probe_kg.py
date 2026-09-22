"""Probe RabbitMQ queues/DLQ and graph_doc table to diagnose KG consumer."""
import asyncio
import sys
from pathlib import Path

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main():
    import aio_pika
    from core.config import settings

    conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    ch = await conn.channel()
    for q in (settings.QUEUE_INDEX, settings.QUEUE_RAG, settings.QUEUE_KG):
        for suffix in ('', '.dlq'):
            name = q + suffix
            try:
                qobj = await ch.declare_queue(name, durable=True, passive=True)
                print(f'{name}: {qobj.declaration_result.message_count} messages')
            except Exception as e:
                print(f'{name}: {type(e).__name__}')
    await conn.close()

    # graph_doc 表行数
    from sqlalchemy import URL, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    url = URL.create(
        drivername="postgresql+psycopg",
        username=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT, database=settings.POSTGRES_DB,
    )
    eng = create_async_engine(url, pool_pre_ping=True)
    maker = async_sessionmaker(eng, expire_on_commit=False)
    async with maker() as s:
        res = await s.execute(text('SELECT doc_id, length(cypher) FROM graph_doc ORDER BY doc_id'))
        print('graph_doc rows:', res.fetchall())
    await eng.dispose()


asyncio.run(main())
