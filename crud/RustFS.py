from pydantic_settings import BaseSettings, SettingsConfigDict
import aioboto3
from botocore.client import Config
from botocore.exceptions import ClientError
# ========== 配置类 ==========
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    RUSTFS_ENDPOINT: str
    RUSTFS_ACCESS_KEY: str
    RUSTFS_SECRET_KEY: str
    RUSTFS_BUCKET: str
    PRESIGNED_EXPIRE: int = 3600  # 预签名链接有效期，单位秒

settings = Settings()

# ========== 异步S3客户端依赖 ==========
async def get_s3_client():
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=settings.RUSTFS_ENDPOINT,
        aws_access_key_id=settings.RUSTFS_ACCESS_KEY,
        aws_secret_access_key=settings.RUSTFS_SECRET_KEY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"}
        ),
    ) as client:
        yield client

async def init_rustfs_bucket():
    """RustFS桶初始化函数，可以被main.py的lifespan调用"""
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=settings.RUSTFS_ENDPOINT,
        aws_access_key_id=settings.RUSTFS_ACCESS_KEY,
        aws_secret_access_key=settings.RUSTFS_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    ) as s3:
        try:
            await s3.head_bucket(Bucket=settings.RUSTFS_BUCKET)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                await s3.create_bucket(Bucket=settings.RUSTFS_BUCKET)
            else:
                raise