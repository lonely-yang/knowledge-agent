from fastapi import APIRouter
from neo4j import AsyncDriver, AsyncGraphDatabase

from .config import settings
from .entityAndrelationship import get_entity_relationship
from .save_neo4j import create_graph_doc, graph_doc_exists
from core.database import create_pg_tables
from models import GraphDocModel
from schemas.graph import GraphDocOut

neo4j_router = APIRouter(prefix='/neo4j', tags=['Neo4j'])

# ========== Neo4j 驱动管理 ==========
driver: AsyncDriver | None = None


async def init_neo4j_driver() -> AsyncDriver:
    global driver
    driver = AsyncGraphDatabase.driver(
        uri=settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        max_connection_pool_size=settings.MAX_CONN_POOL_SIZE,
    )
    await driver.verify_connectivity()
    print('创建neo4j服务成功')
    return driver


async def close_neo4j_driver():
    global driver
    if driver is not None:
        await driver.close()
        driver = None
        print('关闭neo4j链接')


@neo4j_router.get('/create_neo4j_table')
async def create_neo4j_table():
    return await create_pg_tables(tables=[GraphDocModel.__table__])


@neo4j_router.get('/check_neo4j_table')
async def check_neo4j_table(doc_id: int):
    return {"doc_id": doc_id, "exists": await graph_doc_exists(doc_id)}


@neo4j_router.post('/insert_neo4j_table', response_model=GraphDocOut)
async def insert_neo4j_table(doc_id: int):
    return await create_graph_doc(doc_id, neo_driver=driver)

@neo4j_router.get('/entity_relationship')
async def entity_relationship(doc_id: int):
    item = await get_entity_relationship(doc_id)
    return item.model_dump()
