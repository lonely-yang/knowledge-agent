import asyncio
import sys
from contextlib import asynccontextmanager
from crud.RustFS import init_rustfs_bucket
from crud.mongodb import init_mongodb
from crud.rabbitmq.rabbitms import init_mq,close_mq
from crud.es.create import init_es,close_es
from crud.neo4j.create import init_neo4j_driver, close_neo4j_driver

if sys.platform == 'win32':
    # psycopg 异步模式不支持 Windows 默认的 ProactorEventLoop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models.restfs_file import restFS_router
from models.publish_doc import publish_router
from crud.postgre import pg_router
from crud.mongodb import mongo_router
from crud.es.create import es_router
from crud.milvus.create import milvus_router
from crud.neo4j.create import neo4j_router
from models.aiinvoke import ai_router
from crud.user.create import user_router, role_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在main的lifespan里调用抽出去的初始化函数
    await init_rustfs_bucket()
    await init_mongodb()
    await init_mq()
    await init_es()
    await init_neo4j_driver()
    yield
    await close_mq()
    await close_es()
    await close_neo4j_driver()
    print("App shutdown")

app = FastAPI(title="Knowledge",lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(user_router)
app.include_router(role_router)
app.include_router(ai_router)
app.include_router(neo4j_router)
app.include_router(milvus_router)
app.include_router(es_router)
app.include_router(pg_router)
app.include_router(mongo_router)
app.include_router(restFS_router)
app.include_router(publish_router)

