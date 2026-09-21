from .insert import embedding_text
from .config import milvus_client,settings
# 从向量数据库中进行查询相似度最接近的数据

async def search_milvus_data(query:str):
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
        output_fields=["id",'title','content_id','content']  # 指定返回的标量字段
    )
    return {
        'msg':'向量查询成功',
        'data':res[0]
    }