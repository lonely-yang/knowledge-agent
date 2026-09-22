from fastapi import APIRouter

from clients.neo4j_client import driver
from .entityAndrelationship import get_entity_relationship
from .save_neo4j import create_graph_doc, graph_doc_exists
from core.database import create_pg_tables
from models import GraphDocModel
from schemas.graph import GraphDocOut

neo4j_router = APIRouter(prefix='/neo4j', tags=['Neo4j'])


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
