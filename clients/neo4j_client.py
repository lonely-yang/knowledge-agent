from neo4j import AsyncDriver, AsyncGraphDatabase

from core.config import settings

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
