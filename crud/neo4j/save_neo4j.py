from fastapi import HTTPException
from neo4j import AsyncDriver
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import SessionLocal
from models import GraphDocModel
from schemas.graph import GraphDocCreate, GraphDocOut
from .entityAndrelationship import get_entity_relationship



# -------------------------- 建表 --------------------------
async def _get_doc_or_none(session: AsyncSession, doc_id: int) -> GraphDocModel | None:
    stmt = select(GraphDocModel).where(GraphDocModel.doc_id == doc_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def graph_doc_exists(doc_id: int) -> bool:
    async with SessionLocal() as session:
        return await _get_doc_or_none(session, doc_id) is not None


async def create_graph_doc(doc_id: int, neo_driver: AsyncDriver | None = None) -> GraphDocModel:

    if await graph_doc_exists(doc_id):
        raise HTTPException(status_code=409, detail=f"doc_id {doc_id} already exists")
    item = await get_entity_relationship(doc_id)

    async with SessionLocal() as session:
        db_record = GraphDocModel(
            doc_id=doc_id,
            entities=item.entities,
            relationships=item.relationships,
            query_cypher=item.query_cypher,
            cypher=item.cypher,
        )
        session.add(db_record)
        try:
            await session.commit()
        except IntegrityError:
            raise HTTPException(status_code=409, detail=f"doc_id {doc_id} already exists")
        await session.refresh(db_record)

    if neo_driver is not None:
        try:
            await neo_driver.execute_query(item.cypher)
        except Exception as e:
            # 图写入失败则回删元数据，保证PG与Neo4j两边状态一致
            async with SessionLocal() as session:
                stale = await _get_doc_or_none(session, doc_id)
                if stale:
                    await session.delete(stale)
                    await session.commit()
            raise HTTPException(status_code=500, detail=f"Neo4j cypher execute error: {str(e)}")

    return db_record


async def get_graph_doc(doc_id: int) -> GraphDocModel:
    async with SessionLocal() as session:
        doc = await _get_doc_or_none(session, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"doc_id {doc_id} not found")
        return doc


async def delete_graph_doc(doc_id: int):
    async with SessionLocal() as session:
        doc = await _get_doc_or_none(session, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"doc_id {doc_id} not found")
        await session.delete(doc)
        await session.commit()
    return {"msg": f"doc_id {doc_id} deleted"}
