from pymilvus import AsyncMilvusClient
from langchain_openai import OpenAIEmbeddings

from core.config import settings

# 创建 集合
milvus_client = AsyncMilvusClient(
    uri=settings.MILVUS_URL,
    token=settings.MILVUS_TOKEN,
    db_name=settings.DB_NAME
)

# content 内容转向量
embddings_model = OpenAIEmbeddings(
    model=settings.EMBEDDINGS_MODEL_NAME,
    api_key=settings.QWEN_API_KEY,
    base_url=settings.QWEN_BASE_URL,
    dimensions=settings.DIMENSIONS,
    check_embedding_ctx_length=False
)

async def embedding_text(txt:str):
    # 必须用异步版本，同步 embed_query 会阻塞整个事件循环
    return await embddings_model.aembed_query(txt)

async def milvus_insert(doc_id,meta,chunks):
    # 集合 id 是 auto_id，插入时不能带主键字段
    meta = dict(meta)
    meta.pop('id', None)

    # Qwen embedding 接口单次请求有文本条数上限，按批请求
    batch_size = 10
    vectors = []
    for i in range(0, len(chunks), batch_size):
        vectors.extend(await embddings_model.aembed_documents(chunks[i:i + batch_size]))

    table_data = [
        {
            'title': meta.get('title'),
            'content_id': f'{doc_id}-{index}',
            'content': chunk,
            'vector': vector,
        }
        for index, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]

    await milvus_client.insert(
        collection_name=settings.COLLECTION_NAME,
        data=table_data
    )
    await milvus_client.flush(collection_name=settings.COLLECTION_NAME)
    print('milvus 向量数据库新增数据成功！')


# 从向量数据库中进行查询相似度最接近的数据
async def search_milvus_data(query: str, doc_ids: list[int] | None = None):
    """向量召回;doc_ids 为可见文档ID列表(None=不过滤,空列表=直接返回空)"""
    if doc_ids is not None and not doc_ids:
        return {'msg': '向量查询成功', 'data': []}
    filter_expr = None
    if doc_ids:
        # content_id 形如 "{doc_id}-{chunk_index}",按前缀匹配限定可见文档
        filter_expr = ' or '.join(f'(content_id like "{d}-%")' for d in doc_ids)
    vector_query = await embedding_text(query)
    res = await milvus_client.search(
        collection_name=settings.COLLECTION_NAME,
        data=[vector_query],  # 查询向量
        anns_field="vector",  # 向量字段名
        search_params={
            "metric_type": "COSINE",  # 度量类型应与创建索引时一致
            "params": {"nprobe": 16}  # 搜索时考虑的聚类数量
        },
        limit=10,  # 返回 Top-10 最相似的结果
        output_fields=["id",'title','content_id','content'],  # 指定返回的标量字段
        filter=filter_expr,
    )
    return {
        'msg':'向量查询成功',
        'data':res[0]
    }
