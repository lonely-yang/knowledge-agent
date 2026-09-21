from pydantic_settings import BaseSettings, SettingsConfigDict

# ========== 配置类 ==========
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    NEO4J_URI : str
    NEO4J_USER : str
    NEO4J_PASSWORD : str
    MAX_CONN_POOL_SIZE : int = 50

    QWEN_API_KEY:str
    QWEN_BASE_URL:str
    QWEN_MODEL_NAME:str

    POSTGRES_USER:str = "postgres"
    POSTGRES_PASSWORD:str = "lyp82nlfxxlE"
    POSTGRES_HOST:str = "localhost"
    POSTGRES_PORT:int = 5433
    POSTGRES_DB:str = "aiagent"

settings = Settings()
