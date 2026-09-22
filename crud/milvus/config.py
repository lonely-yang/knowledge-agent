from pymilvus import AsyncMilvusClient

from core.config import settings

# 创建 集合
milvus_client = AsyncMilvusClient(
    uri=settings.MILVUS_URL,
    token=settings.MILVUS_TOKEN,
    db_name=settings.DB_NAME
)