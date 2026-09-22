from datetime import datetime

from beanie import Document


# Beanie Document 模型（映射Mongo集合）
class KHDocument(Document):
    id:int
    document_id:int
    content:str
    content_len:int
    content_summary:str
    create_at:datetime
    update_at:datetime

    class Settings:
        # 对应mongo集合名称
        name = "document_content"
