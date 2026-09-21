from pydantic_settings import BaseSettings, SettingsConfigDict
# ========== 配置类 ==========
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    QUEUE_INDEX: str = "INDEX"
    QUEUE_RAG: str = "BY_DOC_IDS"
    QUEUE_KG: str = "BUILD_BY_DOC_IDS"
    RABBITMQ_URL:str = "amqp://user:lyp82nlfxxlE@127.0.0.1:5672/aiagent"

settings = Settings()