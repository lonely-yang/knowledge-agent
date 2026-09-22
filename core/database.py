from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings

PGSQL_URL = URL.create(
    drivername="postgresql+psycopg",
    username=settings.POSTGRES_USER,
    password=settings.POSTGRES_PASSWORD,
    host=settings.POSTGRES_HOST,
    port=settings.POSTGRES_PORT,
    database=settings.POSTGRES_DB,
)
engine = create_async_engine(PGSQL_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


async def create_pg_tables(tables=None):
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all, tables=tables)
            return {'msg': 'pg 建表成功'}
        except Exception as e:
            return {'msg': 'pg 建表失败', 'data': str(e)}


async def drop_pg_tables(tables=None):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all, tables=tables)
        return {'msg': 'pg 删表成功'}
    except Exception as e:
        return {'msg': 'pg 删表失败', 'data': str(e)}
