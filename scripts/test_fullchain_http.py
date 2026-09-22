"""Full-chain E2E against a running uvicorn (port 8000): upload → publish → MQ → ES/Milvus/KG → ai invoke."""
import asyncio
import sys
import time
from pathlib import Path

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BASE = 'http://127.0.0.1:8000'
results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print(('PASS ' if cond else 'FAIL '), name, detail)


def main():
    client = httpx.Client(timeout=120)

    # 等应用就绪
    for _ in range(60):
        try:
            if client.get(BASE + '/openapi.json').status_code == 200:
                break
        except Exception:
            pass
        time.sleep(2)

    # 上传
    import pymupdf
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), 'PostgreSQL 是关系型数据库，用于存储文档元数据。Milvus 是向量数据库，用于相似度检索。')
    pdf_bytes = pdf.tobytes()
    pdf.close()

    r = client.post(BASE + '/restfs/upload', files={'file': ('fullchain-e2e.pdf', pdf_bytes, 'application/pdf')})
    check('upload', r.status_code == 200, f'status={r.status_code}')
    doc_id = None
    if r.status_code == 200:
        key = r.json().get('key')
        docs = client.get(BASE + '/pg/check_all').json() or []
        for d in docs:
            if d.get('title') == key:
                doc_id = d['id']
                break
    check('upload → PG 落库', doc_id is not None, f'doc_id={doc_id}')

    # 发布 → MQ
    r = client.post(f'{BASE}/knowledge_doc/publish?doc_id={doc_id}')
    check('publish', r.status_code == 200, f'status={r.status_code}')

    # 等三个消费者
    deadline = time.time() + 300
    es_ok = kg_ok = rag_ok = False
    while time.time() < deadline:
        if not es_ok:
            r = client.get(f'{BASE}/es/check?doc_id={doc_id}')
            es_ok = r.status_code == 200
        if not kg_ok:
            r = client.get(f'{BASE}/neo4j/check_neo4j_table', params={'doc_id': doc_id})
            kg_ok = r.status_code == 200 and r.json().get('exists')
        if not rag_ok:
            r = client.post(f'{BASE}/milvus/search?query=向量数据库')
            if r.status_code == 200:
                data = r.json().get('data') or []
                rag_ok = any(str(doc_id) in str(h.get('entity', {}).get('content_id', '') or h.get('content_id', '')) for h in data)
        if es_ok and kg_ok and rag_ok:
            break
        time.sleep(3)
    check('INDEX 消费 → ES', es_ok)
    check('KG 消费 → graph_doc', kg_ok)
    check('RAG 消费 → Milvus 含测试文档', rag_ok)

    # AI 检索
    r = client.post(f'{BASE}/ai/invoke?query=PostgreSQL&top_n=3')
    check('ai invoke', r.status_code == 200, f'status={r.status_code}')
    if r.status_code == 200:
        check('ai invoke 返回正文', len(str(r.json().get('content', ''))) > 0)

    # 清理 PG + Mongo
    r = client.delete(f'{BASE}/pg/del_doc?doc_id={doc_id}')
    check('清理 PG+Mongo', r.status_code == 200, f'status={r.status_code}')

    client.close()
    return doc_id


doc_id = main()

# 客户端级清理:ES / Milvus / graph_doc
async def cleanup(uid):
    from sqlalchemy import URL, delete as sa_delete, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from core.config import settings
    from models import GraphDocModel

    from elasticsearch import AsyncElasticsearch
    es = AsyncElasticsearch(settings.ES_HOST, basic_auth=("elastic", settings.ES_BASIC_AUTH))
    try:
        await es.delete(index=settings.INDEX_NAME, id=str(uid), refresh=True)
        print('cleanup: ES doc deleted')
    except Exception:
        pass
    await es.close()

    from pymilvus import AsyncMilvusClient
    mc = AsyncMilvusClient(uri=settings.MILVUS_URL, token=settings.MILVUS_TOKEN, db_name=settings.DB_NAME)
    try:
        await mc.delete(collection_name=settings.COLLECTION_NAME, filter=f'content_id like "{uid}-%"')
        await mc.flush(collection_name=settings.COLLECTION_NAME)
        print('cleanup: Milvus vectors deleted')
    except Exception as e:
        print('cleanup: Milvus skipped', type(e).__name__)
    await mc.close()

    url = URL.create(
        drivername="postgresql+psycopg",
        username=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT, database=settings.POSTGRES_DB,
    )
    eng = create_async_engine(url, pool_pre_ping=True)
    maker = async_sessionmaker(eng, expire_on_commit=False)
    async with maker() as s:
        await s.execute(sa_delete(GraphDocModel).where(GraphDocModel.doc_id == uid))
        await s.commit()
    await eng.dispose()
    print(f'cleanup: graph_doc row for {uid} deleted')


if doc_id:
    asyncio.run(cleanup(doc_id))

print()
failed = [n for n, ok, d in results if not ok]
print(f'===== {len(results) - len(failed)}/{len(results)} PASS =====')
if failed:
    print('FAILED:', failed)
    sys.exit(1)
