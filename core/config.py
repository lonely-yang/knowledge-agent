from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # QWEN / 嵌入 / 重排
    QWEN_API_KEY: str
    QWEN_BASE_URL: str
    QWEN_MODEL_NAME: str
    EMBEDDINGS_MODEL_NAME: str
    RERANK_MODEL_NAME: str
    RERANK_URL: str

    # PostgreSQL
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "lyp82nlfxxlE"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    POSTGRES_DB: str = "aiagent"

    # MongoDB(与 Milvus 共用 DB_NAME)
    MONGO_URI: str
    DB_NAME: str

    # RustFS
    RUSTFS_ENDPOINT: str
    RUSTFS_ACCESS_KEY: str
    RUSTFS_SECRET_KEY: str
    RUSTFS_BUCKET: str
    PRESIGNED_EXPIRE: int = 3600  # 预签名链接有效期，单位秒

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:lyp82nlfxxlE@127.0.0.1:5672/aiagent"
    QUEUE_INDEX: str = "INDEX"
    QUEUE_RAG: str = "BY_DOC_IDS"
    QUEUE_KG: str = "BUILD_BY_DOC_IDS"

    # Elasticsearch
    INDEX_NAME: str = 'knowledge-es'
    ES_HOST: str = 'http://localhost:9200'
    ES_BASIC_AUTH: str

    # Milvus
    COLLECTION_NAME: str
    DIMENSIONS: int
    MILVUS_URL: str
    MILVUS_TOKEN: str

    # Neo4j
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str
    MAX_CONN_POOL_SIZE: int = 50

    # JWT
    JWT_SECRET_KEY: str = "kh-dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440
    JWT_REFRESH_EXPIRE_MINUTES: int = 10080


settings = Settings()
