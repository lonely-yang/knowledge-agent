"""Runtime regression for the refactored app (services must be up).

Covers: user/role flow, PG+Mongo dual write/delete, ES/Milvus/Neo4j checks,
file upload -> MQ consume -> retrieval full chain, lifespan shutdown.
"""
import asyncio
import sys
import time
from pathlib import Path

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from main import app

_run_ts = int(time.time())
TEST_USER = f'refactor_reg_user_{_run_ts}'
TEST_EMAIL = f'refactor_reg_user_{_run_ts}@test.local'
TEST_PW = 'refactor123'
TEST_ROLE = f'REFACTOR_REG_ROLE_{_run_ts}'
ES_TEST_ID = 987654321

results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print(('PASS ' if cond else 'FAIL '), name, detail)


with TestClient(app, raise_server_exceptions=False) as client:
    r = client.get('/openapi.json')
    check('openapi.json 200', r.status_code == 200, f'status={r.status_code}')

    # ---------- 用户/角色全流程 ----------
    r = client.post('/user/register', json={'username': TEST_USER, 'password': TEST_PW, 'email': TEST_EMAIL})
    check('register', r.status_code == 200, f'status={r.status_code}')
    user_id = r.json().get('id') if r.status_code == 200 else None

    r = client.post('/user/register', json={'username': TEST_USER, 'password': TEST_PW, 'email': TEST_EMAIL})
    check('register 重复 400', r.status_code == 400, f'status={r.status_code}')

    r = client.post('/user/login', json={'username': TEST_USER, 'password': TEST_PW})
    check('login', r.status_code == 200, f'status={r.status_code}')
    token = r.json().get('token', '') if r.status_code == 200 else ''
    refresh_token = r.json().get('refresh_token', '') if r.status_code == 200 else ''
    H = {'Authorization': f'Bearer {token}'}

    r = client.post('/user/refresh', json={'refresh_token': refresh_token})
    check('refresh', r.status_code == 200, f'status={r.status_code}')

    r = client.get('/user/create_table')
    check('user create_table no-op', r.status_code == 200, f'status={r.status_code}')

    r = client.post('/role/add_role', json={'role_name': '回归测试角色', 'role_code': TEST_ROLE, 'description': 'refactor regression'}, headers=H)
    check('add_role', r.status_code == 200, f'status={r.status_code}')
    role_id = r.json().get('id') if r.status_code == 200 else None

    r = client.post('/role/bind_role', json={'user_id': user_id, 'role_id': role_id}, headers=H)
    check('bind_role', r.status_code == 200, f'status={r.status_code}')
    r = client.post('/role/bind_role', json={'user_id': user_id, 'role_id': role_id}, headers=H)
    check('bind_role 重复 400', r.status_code == 400, f'status={r.status_code}')

    r = client.delete(f'/role/unbind_role?user_id={user_id}&role_id={role_id}', headers=H)
    check('unbind_role', r.status_code == 200, f'status={r.status_code}')

    r = client.put(f'/user/update_user?user_id={user_id}', json={'email': f'refactor_reg_user2_{_run_ts}@test.local'}, headers=H)
    check('update_user', r.status_code == 200, f'status={r.status_code}')

    r = client.delete(f'/role/del_role?role_id={role_id}', headers=H)
    check('del_role', r.status_code == 200, f'status={r.status_code}')

    r = client.delete(f'/user/del_user?user_id={user_id}', headers=H)
    check('del_user', r.status_code == 200, f'status={r.status_code}')

    # ---------- PG+Mongo 双写双删(DTO 路径:基线即有 500,验证行为未变) ----------
    r = client.post('/pg/add_doc', json={'id': 999998, 'title': 'refactor-dto-doc', 'content': 'hello content body'})
    check('pg/add_doc DTO 路径(基线同款 500)', r.status_code == 500, f'status={r.status_code}')

    # ---------- ES 建查 ----------
    r = client.post(f'/es/insert?doc_id={ES_TEST_ID}', json={'title': 'es-regression-doc', 'content': 'es regression content'})
    check('es insert', r.status_code == 200, f'status={r.status_code}')
    r = client.get(f'/es/check?doc_id={ES_TEST_ID}')
    check('es check', r.status_code == 200, f'status={r.status_code}')
    time.sleep(2)  # ES 写入后需等 refresh 才能 search(get 是实时的,search 不是)
    r = client.get('/es/query?query=es-regression-doc')
    ok = r.status_code == 200 and any(h.get('_id') == str(ES_TEST_ID) for h in r.json().get('data', []))
    check('es query 命中', ok, f'status={r.status_code}')

    # ---------- Milvus 查询(不调 create_table:会 drop 现有 collection) ----------
    r = client.post('/milvus/search?query=PostgreSQL')
    check('milvus search', r.status_code == 200, f'status={r.status_code}')

    # ---------- Neo4j 建查 ----------
    r = client.get('/neo4j/create_neo4j_table')
    check('neo4j create_table no-op', r.status_code == 200, f'status={r.status_code}')
    r = client.get('/neo4j/check_neo4j_table', params={'doc_id': 1})
    check('neo4j check', r.status_code == 200, f'status={r.status_code}')

    # ---------- 全链路:上传 → 发布 → MQ 消费 → ES/Milvus/KG ----------
    import pymupdf
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), 'PostgreSQL 是关系型数据库，用于存储文档元数据。Milvus 是向量数据库，用于相似度检索。')
    pdf_bytes = pdf.tobytes()
    pdf.close()

    r = client.post('/restfs/upload', files={'file': ('regression-test.pdf', pdf_bytes, 'application/pdf')})
    check('restfs upload', r.status_code == 200, f'status={r.status_code}')
    upload_doc_id = None
    if r.status_code == 200:
        key = r.json().get('key')
        r2 = client.get('/pg/check_all')
        for d in (r2.json() or []):
            if d.get('title') == key:
                upload_doc_id = d['id']
                break
    check('upload → PG 落库', upload_doc_id is not None, f'doc_id={upload_doc_id}')

    if upload_doc_id is not None:
        r = client.get(f'/pg/check?id={upload_doc_id}')
        check('upload → PG check', r.status_code == 200, f'status={r.status_code}')
        r = client.get(f'/mongo/check?doc_id={upload_doc_id}')
        check('upload → Mongo 双写', r.status_code == 200, f'status={r.status_code}')

        r = client.post(f'/knowledge_doc/publish?doc_id={upload_doc_id}')
        check('publish', r.status_code == 200, f'status={r.status_code}')

        # 等 MQ 消费(消费者是本进程 lifespan 起的后台任务)
        deadline = time.time() + 180
        es_ok = kg_ok = False
        while time.time() < deadline:
            if not es_ok:
                r = client.get(f'/es/check?doc_id={upload_doc_id}')
                es_ok = r.status_code == 200
            if not kg_ok:
                r = client.get('/neo4j/check_neo4j_table', params={'doc_id': upload_doc_id})
                kg_ok = r.status_code == 200 and r.json().get('exists')
            if es_ok and kg_ok:
                break
            time.sleep(2)
        check('MQ INDEX 消费 → ES', es_ok)
        check('MQ KG 消费 → graph_doc', kg_ok)

        r = client.post('/milvus/search?query=向量数据库')
        check('MQ RAG 消费后 Milvus 可查', r.status_code == 200, f'status={r.status_code}')

        # ---------- AI 检索全链路 ----------
        r = client.post('/ai/invoke?query=PostgreSQL&top_n=3')
        check('ai invoke', r.status_code == 200, f'status={r.status_code}')
        if r.status_code == 200:
            txt = str(r.json().get('content', ''))
            check('ai invoke 返回正文', len(txt) > 0)

        # ---------- 清理:PG+Mongo(接口路径) ----------
        r = client.delete(f'/pg/del_doc?doc_id={upload_doc_id}')
        check('清理 PG+Mongo(del_doc)', r.status_code == 200, f'status={r.status_code}')
        r = client.get(f'/mongo/check?doc_id={upload_doc_id}')
        check('清理后 Mongo 404', r.status_code == 404, f'status={r.status_code}')

    print('--- exiting TestClient (lifespan shutdown) ---')

print('--- TestClient exited cleanly, lifespan shutdown OK ---')

# ---------- 客户端级清理:ES 测试文档 / graph_doc 行 / Milvus 向量 ----------
async def cleanup():
    from sqlalchemy import delete as sa_delete
    from sqlalchemy import URL
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from core.config import settings
    from models import GraphDocModel

    # ES 测试文档
    from elasticsearch import AsyncElasticsearch
    es = AsyncElasticsearch(settings.ES_HOST, basic_auth=("elastic", settings.ES_BASIC_AUTH))
    try:
        await es.delete(index=settings.INDEX_NAME, id=str(ES_TEST_ID), refresh=True)
        print('cleanup: ES test doc deleted')
    except Exception as e:
        print('cleanup: ES delete skipped:', type(e).__name__)
    await es.close()

    # 全链路文档的 ES 记录 + Milvus 向量(若消费成功过)
    if upload_doc_id:
        uid = upload_doc_id
        es2 = AsyncElasticsearch(settings.ES_HOST, basic_auth=("elastic", settings.ES_BASIC_AUTH))
        try:
            await es2.delete(index=settings.INDEX_NAME, id=str(uid), refresh=True)
            print('cleanup: fullchain ES doc deleted')
        except Exception:
            pass
        await es2.close()

        from pymilvus import AsyncMilvusClient
        mc = AsyncMilvusClient(uri=settings.MILVUS_URL, token=settings.MILVUS_TOKEN, db_name=settings.DB_NAME)
        try:
            await mc.delete(collection_name=settings.COLLECTION_NAME, filter=f'content_id like "{uid}-%"')
            await mc.flush(collection_name=settings.COLLECTION_NAME)
            print('cleanup: Milvus vectors deleted')
        except Exception as e:
            print('cleanup: Milvus delete skipped:', type(e).__name__)
        await mc.close()

    # graph_doc 元数据行(独立新 engine,避免跨事件循环复用)
    if upload_doc_id:
        url = URL.create(
            drivername="postgresql+psycopg",
            username=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
            host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT, database=settings.POSTGRES_DB,
        )
        eng = create_async_engine(url, pool_pre_ping=True)
        maker = async_sessionmaker(eng, expire_on_commit=False)
        async with maker() as s:
            await s.execute(sa_delete(GraphDocModel).where(GraphDocModel.doc_id == upload_doc_id))
            await s.commit()
        await eng.dispose()
        print(f'cleanup: graph_doc row for {upload_doc_id} deleted')


asyncio.run(cleanup())

print()
failed = [n for n, ok, d in results if not ok]
print(f'===== {len(results) - len(failed)}/{len(results)} PASS =====')
if failed:
    print('FAILED:', failed)
    sys.exit(1)
