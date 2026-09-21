from pydantic_settings import BaseSettings, SettingsConfigDict
from pymilvus import AsyncMilvusClient
# ========== 配置类 ==========
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    COLLECTION_NAME: str
    DIMENSIONS:int
    EMBEDDINGS_MODEL_NAME:str
    QWEN_API_KEY:str
    QWEN_BASE_URL:str
    MILVUS_URL:str
    TOKEN:str
    DB_NAME:str
settings = Settings()

# 创建 集合
milvus_client = AsyncMilvusClient(
    uri=settings.MILVUS_URL,
    token=settings.TOKEN,
    db_name=settings.DB_NAME
)