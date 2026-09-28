"""Chat 模块回归:建表(FK 级联)、会话 CRUD、删会话级联删消息、归属校验。"""
import asyncio
import sys
import time
from pathlib import Path

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
from fastapi.testclient import TestClient

from core.config import settings
from main import app

_ts = int(time.time())
USER_A = f'chat_test_a_{_ts}'
USER_B = f'chat_test_b_{_ts}'
EMAIL_A = f'{USER_A}@test.local'
EMAIL_B = f'{USER_B}@test.local'
PW = 'chat12345'

results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print(('PASS ' if cond else 'FAIL '), name, detail)


def pg_conn():
    return psycopg.connect(
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT,
        dbname=settings.POSTGRES_DB, user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD, autocommit=True,
    )


with TestClient(app, raise_server_exceptions=False) as client:
    # 建表(带外键级联 DDL)
    r = client.get('/chat/create_chat_table')
    check('create_chat_table', r.status_code == 200, f'status={r.status_code}')

    # 两个用户
    r = client.post('/user/register', json={'username': USER_A, 'password': PW, 'email': EMAIL_A})
    user_a = r.json().get('id') if r.status_code == 200 else None
    check('register A', r.status_code == 200, f'status={r.status_code}')
    r = client.post('/user/register', json={'username': USER_B, 'password': PW, 'email': EMAIL_B})
    user_b = r.json().get('id') if r.status_code == 200 else None
    check('register B', r.status_code == 200, f'status={r.status_code}')

    r = client.post('/user/login', json={'username': USER_A, 'password': PW})
    ha = {'Authorization': f"Bearer {r.json().get('token')}"}
    r = client.post('/user/login', json={'username': USER_B, 'password': PW})
    hb = {'Authorization': f"Bearer {r.json().get('token')}"}

    # 会话创建(同一用户建两个,验证 unique 已去)
    r = client.post('/chat/session', json={'title': '会话一'}, headers=ha)
    check('create session 1', r.status_code == 200, f'status={r.status_code}')
    s1 = r.json().get('id') if r.status_code == 200 else None

    r = client.post('/chat/session', json={'title': '会话二'}, headers=ha)
    check('create session 2(同用户)', r.status_code == 200, f'status={r.status_code}')
    s2 = r.json().get('id') if r.status_code == 200 else None

    r = client.post('/chat/session', json={'title': '  '}, headers=ha)
    check('create 空标题 400', r.status_code == 400, f'status={r.status_code}')

    r = client.post('/chat/session', json={'title': '用户B的会话'}, headers=hb)
    check('create session B', r.status_code == 200, f'status={r.status_code}')
    sb = r.json().get('id') if r.status_code == 200 else None

    # 列表(只含自己的)
    r = client.get('/chat/session', headers=ha)
    ids = [d['id'] for d in (r.json() or [])]
    check('list A 含自己的两个', r.status_code == 200 and s1 in ids and s2 in ids and sb not in ids, f'ids={ids}')

    # 查询单个 + 归属校验
    r = client.get(f'/chat/session/{s1}', headers=ha)
    check('get session 1', r.status_code == 200, f'status={r.status_code}')

    r = client.get(f'/chat/session/{s1}', headers=hb)
    check('他人会话 404(不泄露存在性)', r.status_code == 404, f'status={r.status_code}')

    r = client.get('/chat/session/999999', headers=ha)
    check('不存在会话 404', r.status_code == 404, f'status={r.status_code}')

    # 更新标题
    r = client.put(f'/chat/session/{s1}', json={'title': '会话一改'}, headers=ha)
    check('update title', r.status_code == 200 and r.json().get('title') == '会话一改', f'status={r.status_code}')

    r = client.put(f'/chat/session/{s1}', json={'title': ''}, headers=ha)
    check('update 空标题 400', r.status_code == 400, f'status={r.status_code}')

    # 外键级联:插入消息后删会话
    conn = pg_conn()
    conn.execute(
        'INSERT INTO kh_ai_message (session_id, role, content, sources, create_at) VALUES (%s, %s, %s, %s, now())',
        (s1, 'user', 'hello', '{}'),
    )
    conn.execute(
        'INSERT INTO kh_ai_message (session_id, role, content, sources, create_at) VALUES (%s, %s, %s, %s, now())',
        (s1, 'assistant', '你好', '{}'),
    )
    cnt = conn.execute('SELECT count(*) FROM kh_ai_message WHERE session_id = %s', (s1,)).fetchone()[0]
    check('消息已插入 2 条', cnt == 2, f'count={cnt}')

    r = client.delete(f'/chat/session/{s1}', headers=ha)
    check('delete session', r.status_code == 200, f'status={r.status_code}')

    cnt = conn.execute('SELECT count(*) FROM kh_ai_message WHERE session_id = %s', (s1,)).fetchone()[0]
    check('删会话后消息级联删除', cnt == 0, f'count={cnt}')

    cnt = conn.execute('SELECT count(*) FROM kh_ai_session WHERE id = %s', (s1,)).fetchone()[0]
    check('会话行已删除', cnt == 0, f'count={cnt}')

    r = client.delete(f'/chat/session/{s1}', headers=ha)
    check('重复删除 404', r.status_code == 404, f'status={r.status_code}')

    r = client.delete(f'/chat/session/{s2}', headers=ha)
    check('delete session 2', r.status_code == 200, f'status={r.status_code}')
    r = client.delete(f'/chat/session/{sb}', headers=hb)
    check('delete session B', r.status_code == 200, f'status={r.status_code}')

    # 清理用户
    r = client.delete(f'/user/del_user?user_id={user_a}', headers=ha)
    check('del_user A', r.status_code == 200, f'status={r.status_code}')
    r = client.delete(f'/user/del_user?user_id={user_b}', headers=hb)
    check('del_user B', r.status_code == 200, f'status={r.status_code}')
    conn.close()

print()
failed = [n for n, ok, d in results if not ok]
print(f'===== {len(results) - len(failed)}/{len(results)} PASS =====')
if failed:
    print('FAILED:', failed)
    sys.exit(1)
