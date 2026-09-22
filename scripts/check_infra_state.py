"""Probe current state of all backends without modifying anything."""
import asyncio
import json
import sys
from pathlib import Path

if sys.platform == 'win32':
    # psycopg 异步模式不支持 Windows 默认的 ProactorEventLoop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.database import engine
from clients.es_client import init_es, close_es
from clients.milvus_client import milvus_client


async def main():
    # PG tables
    from sqlalchemy import text
    async with engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        ))
        pg_tables = [r[0] for r in res.fetchall()]
    print("PG tables:", pg_tables)

    # ES indices
    es = await init_es()
    indices = await es.indices.get_alias(index="*")
    print("ES indices:", sorted(indices.keys()))
    await close_es()

    # Milvus collections
    colls = await milvus_client.list_collections()
    print("Milvus collections:", colls)

    # Mongo collections
    from pymongo import AsyncMongoClient
    client = AsyncMongoClient(settings.MONGO_URI)
    names = await client[settings.DB_NAME].list_collection_names()
    print("Mongo collections:", names)

    # Neo4j node counts
    import clients.neo4j_client as nc
    await nc.init_neo4j_driver()
    records, _, _ = await nc.driver.execute_query("MATCH (n) RETURN labels(n) AS labels, count(*) AS cnt ORDER BY labels")
    print("Neo4j nodes:", [(r["labels"], r["cnt"]) for r in records])
    await nc.close_neo4j_driver()


asyncio.run(main())
