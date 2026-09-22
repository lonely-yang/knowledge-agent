from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter,Depends

from clients.es_client import (
    add_data as es_add_data,
    check_data as es_check_data,
    delete_all_data as es_delete_all_data,
    init_es,
    search_all_data as es_search_all_data,
    search_data as es_search_data,
    search_hightlight_data as es_search_hightlight_data,
)
from schemas.search import KnowledgeDoc

es_router = APIRouter(prefix='/es',tags=['ES 全文检索'])


@es_router.get('/create_es_index')
async def async_es(index_name:str,es:AsyncElasticsearch = Depends(init_es)):
    # 判断索引是否存在
    exists = await es.indices.exists(index=index_name)
    if exists:
        return {
            'msg': f'索引已存在{index_name}'
        }
    else:
        # 创建索引
        index_mapping = es.indices.create(
            index=index_name,
            mappings={
                "properties": {
                    # ========== 元信息 meta 字段 ==========
                    # 中文文本必须指定 ik 分词器，与查询端 analyzer 一致，否则查不到结果
                    "title": {"type": "text", "analyzer": "ik_smart", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
                    "content_id": {"type": "long"},
                    "summary": {"type": "text", "analyzer": "ik_smart"},
                    "doc_type": {"type": "keyword"},
                    "status": {"type": "byte"},
                    "publish_time": {"type": "date"},
                    "create_at": {"type": "date"},
                    # ========== 正文 content 全文检索 ==========
                    "content": {"type": "text", "analyzer": "ik_smart"}
                }
            }
        )
        return {
            'msg':f'创建索引成功{index_name}'
        }


@es_router.post('/insert')
async def es_add(docs:KnowledgeDoc,doc_id:int,es:AsyncElasticsearch = Depends(init_es)):
    res = await es_add_data(docs,doc_id,es)
    return res

@es_router.get('/check')
async def es_check(doc_id:int,es:AsyncElasticsearch = Depends(init_es)):
    res = await es_check_data(doc_id,es)
    return res

# 查询数据
@es_router.get('/query')
async def search_data(query:str,es:AsyncElasticsearch = Depends(init_es)):
    return await es_search_data(query, es)

@es_router.get('/hightlight_query')
async def search_hightlight_data(query:str,es:AsyncElasticsearch = Depends(init_es)):
    return await es_search_hightlight_data(query, es)


# 查询全部数据
@es_router.get('/query_all')
async def search_all_data(es:AsyncElasticsearch = Depends(init_es)):
    return await es_search_all_data(es)


# 删除全部数据（保留索引结构）
@es_router.delete('/delete_all')
async def delete_all_data(es:AsyncElasticsearch = Depends(init_es)):
    return await es_delete_all_data(es)
