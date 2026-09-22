"""
1. 通过id 从mongoDB中获取 正文信息
2. 正文信息split分割存入milvus向量数据库中
"""
from clients.milvus_client import milvus_insert
from langchain_text_splitters import RecursiveCharacterTextSplitter
async def split_doc(doc_id,meta,doc):
    doc_data = doc.dict()
    content = doc_data.get('content')
    splitter = RecursiveCharacterTextSplitter(
        separators=['。', '！', '？', '；', ';', '\n'],
        chunk_size=200,
        chunk_overlap=50
    )
    chunks = splitter.split_text(content.strip())
    await milvus_insert(doc_id,meta,chunks)
