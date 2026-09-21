# 向量数据库中插入数据
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from .config import settings,milvus_client
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



