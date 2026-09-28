from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from clients.neo4j_client import driver
from core.database import create_pg_tables, get_db
from core.security import get_current_user
from models import GraphDocModel, KhDocument, UserModel
from schemas.graph import GraphDocOut, GraphOverviewDTO
from services.graph_service import create_graph_doc, graph_doc_exists
from services.llm_service import get_entity_relationship

neo4j_router = APIRouter(prefix='/neo4j', tags=['Neo4j'])


def _visible_docs_stmt(user: UserModel):
    """可见文档过滤:公开或本人"""
    return or_(KhDocument.is_public == 1, KhDocument.author_id == user.id)


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
async def entity_relationship(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    doc = await db.get(KhDocument, doc_id)
    if not doc or (doc.is_public != 1 and doc.author_id != current_user.id):
        raise HTTPException(status_code=403, detail="无权查看该文档")
    item = await get_entity_relationship(doc_id)
    return item.model_dump()


@neo4j_router.get('/overview', response_model=GraphOverviewDTO)
async def graph_overview_api(
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """图谱总览:聚合当前用户可见文档(公开或本人)的实体与关系"""
    rows = (
        await db.execute(
            select(GraphDocModel)
            .join(KhDocument, KhDocument.id == GraphDocModel.doc_id)
            .where(_visible_docs_stmt(current_user))
            .order_by(GraphDocModel.doc_id)
        )
    ).scalars().all()
    titles: dict[int, str] = {}
    if rows:
        doc_ids = [r.doc_id for r in rows]
        titles = {
            d.id: (d.title or f'文档{d.id}')
            for d in (await db.execute(select(KhDocument).where(KhDocument.id.in_(doc_ids)))).scalars().all()
        }

    nodes: list[dict] = []
    edges: list[dict] = []
    type_count: dict[str, int] = {}
    degree: dict[str, int] = {}
    entity_label: dict[str, str] = {}

    for row in rows:
        doc_title = titles.get(row.doc_id, f'文档{row.doc_id}')
        nodes.append({
            'id': f'doc-{row.doc_id}', 'name': doc_title, 'kind': 'document',
            'type': None, 'documentId': str(row.doc_id), 'updatedAt': None, 'description': None,
        })
        name_map: dict[str, str] = {}
        for i, ent in enumerate(row.entities or []):
            if not isinstance(ent, dict):
                continue
            name = str(ent.get('name', f'实体{i}'))
            label = str(ent.get('label', 'Entity'))
            node_id = f'ent-{row.doc_id}-{i}'
            if name not in name_map:
                name_map[name] = node_id
                nodes.append({
                    'id': node_id, 'name': name, 'kind': 'entity', 'type': label,
                    'documentId': str(row.doc_id), 'updatedAt': None, 'description': None,
                })
                type_count[label] = type_count.get(label, 0) + 1
                entity_label[name] = label
                degree.setdefault(name, 0)
        for rel in row.relationships or []:
            if not isinstance(rel, dict):
                continue
            src = str(rel.get('sourceName') or rel.get('source') or '')
            tgt = str(rel.get('targetName') or rel.get('target') or '')
            rel_name = str(rel.get('relName') or rel.get('relation') or 'RELATED_TO')
            if not src or not tgt:
                continue
            src_id = name_map.get(src, src)
            tgt_id = name_map.get(tgt, tgt)
            edges.append({'source': src_id, 'target': tgt_id, 'relation': rel_name, 'kind': 'mentions'})
            degree[src] = degree.get(src, 0) + 1
            degree[tgt] = degree.get(tgt, 0) + 1

    top_entities = [
        {'name': name, 'type': entity_label.get(name), 'degree': d}
        for name, d in sorted(degree.items(), key=lambda x: -x[1])[:5]
    ]
    recent_docs = sorted(rows, key=lambda r: -r.doc_id)[:10]
    return {
        'nodes': nodes,
        'edges': edges,
        'stats': {
            'node_count': len(nodes),
            'edge_count': len(edges),
            'document_count': len(rows),
            'entity_count': sum(type_count.values()),
            'tag_count': 0,
            'mention_count': len(edges),
            'related_count': 0,
            'entity_types': [{'type': k, 'count': v} for k, v in sorted(type_count.items(), key=lambda x: -x[1])],
        },
        'top_entities': top_entities,
        'recent_nodes': [
            {'id': f'doc-{r.doc_id}', 'name': titles.get(r.doc_id, f'文档{r.doc_id}'), 'kind': 'document', 'updated_at': None}
            for r in recent_docs
        ],
        'entity_types': sorted(type_count.keys()),
    }
