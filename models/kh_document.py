"""
使用sqlalchemy 创建pg的文档元数据表
"""
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
import os
from dotenv import load_dotenv
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, BigInteger, Integer, Text, TIMESTAMP, ForeignKey, text, SmallInteger, Boolean

load_dotenv()

# 创建异步引擎
from sqlalchemy import URL

PGSQL_URL = URL.create(
    drivername="postgresql+psycopg",
    username=os.environ.get('POSTGRES_USER'),
    password=os.environ.get('POSTGRES_PASSWORD'),
    host="localhost",
    port=5433,
    database="aiagent",
)
async_engine = create_async_engine(PGSQL_URL, echo=True, pool_pre_ping=True)
SessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

# ----------------- 文章表，列表展示 -----------
class Base(DeclarativeBase):
    pass
class KhDocument(Base):
    __tablename__ = 'kh_document'
    id = Column(BigInteger,primary_key=True,comment='主键id')
    title=Column(String(50),comment='标题')
    content_id=Column(BigInteger,comment='关联mongoDB document_content_id')
    summary=Column(String,comment='摘要')
    doc_type=Column(String,comment='文件类型')
    status=Column(SmallInteger,comment='状态（0 草稿/ 1 已发布 / 2 已归档）',default=0)
    publish_time=Column(TIMESTAMP,comment='发布时间')
    create_at=Column(TIMESTAMP,comment='创建时间')

# -----------------建表函数 -------------------
async def create_pg_tables():
    async with async_engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
            return {
                'msg':'pg 建表成功'
            }
        except Exception as e:
            return {
                'msg':'pg建表失败',
                'data':str(e)
            }
# -----------------删表函数 -------------------
async def drop_pg_tables():
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        return {
            'msg': 'pg 删表成功'
        }
    except Exception as e:
        return {
            'msg': 'pg删表失败',
            'data': str(e)
        }

