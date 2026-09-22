from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, HTTPException,Depends

from core.config import settings
from schemas.search import KnowledgeDoc

es_router = APIRouter(prefix='/es',tags=['ES 全文检索'])

es = None

async def init_es():
    global es
    es = AsyncElasticsearch(
        settings.ES_HOST,
        basic_auth=("elastic", settings.ES_BASIC_AUTH)
    )
    # 测试连通性
    if not await es.ping():
        raise RuntimeError("ES 连接失败！")
    print("✅ ES 连接成功")
    return es

async def get_es():
    global es
    if es is None:
        await init_es()
    return es

async def close_es():
    # 服务关闭，释放连接
    await es.close()


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


# es 新增
async def add_data(docs:KnowledgeDoc,doc_id,es=None):
    if es is None:
        es = await get_es()
    new_docs = docs.model_dump()
    res = await es.index(
        index=settings.INDEX_NAME,
        id=doc_id,
        document=new_docs
    )
    return res
@es_router.post('/insert')
async def es_add(docs:KnowledgeDoc,doc_id:int,es:AsyncElasticsearch = Depends(init_es)):
    res = await add_data(docs,doc_id,es)
    return res

async def check_data(doc_id,es):
    res = await es.get(index=settings.INDEX_NAME,id=doc_id)
    return res

@es_router.get('/check')
async def es_check(doc_id:int,es:AsyncElasticsearch = Depends(init_es)):
    res = await check_data(doc_id,es)
    return res

# 查询数据
@es_router.get('/query')
async def search_data(query:str,es:AsyncElasticsearch = Depends(init_es)):
    res = await es.search(
        index=settings.INDEX_NAME,
        query={
           "multi_match": {
                "query": query,
                "analyzer": "ik_smart",
                "fields": ["title^3","summary^2", "content"],
                "type": "best_fields"
            }
        }
    )
    hits = res['hits']['hits']

    new_hits = []
    for h in hits:
        _id = h.get('_id')
        content = h.get('_source').get('content')
        new_hits.append({'_id':_id,'content':content})

    #
    return {
        'msg': '查询成功',
        'data':new_hits
    }

@es_router.get('/hightlight_query')
async def search_hightlight_data(query:str,es:AsyncElasticsearch = Depends(init_es)):
    res = await es.search(
        index=settings.INDEX_NAME,
        query={
            "multi_match": {
                "query": query,
                "analyzer": "ik_smart",
                "fields": ["title^3", "summary^2","content"], # title^3 标题权重3倍高于content
                "type": "best_fields"
            }
        },
        # ========= 新增高亮配置 =========
        highlight={
            "pre_tags": ['<span style="background-color: #ffe600;">'], # 黄色底色，和截图一致
            "post_tags": ['</span>'],
            "fields": {
                "content": {
                    "fragment_size": 180,        # 摘要片段长度，控制预览文字长短
                    "number_of_fragments": 1,    # 只返回1段摘要（列表预览只需要一段）
                    "no_match_size": 150         # 如果无高亮，截取原文前150字
                }
            }
        }
    )
    hits = res['hits']['hits']

    new_hits = []
    for h in hits:
        _id = h.get('_id')
        # 优先取高亮片段，没有高亮就用原文content
        highlight_content = h.get("highlight", {}).get("content")
        title = h.get('_source').get('title')
        if highlight_content:
            content = highlight_content[0] # 取出第一段高亮摘要
        else:
            content = h.get('_source').get('content')
        new_hits.append({
            'title':title,
            '_id':_id,
            'summary':content
        })
    return new_hits


# 查询全部数据
@es_router.get('/query_all')
async def search_all_data(es:AsyncElasticsearch = Depends(init_es)):
    res = await es.search(
        index=settings.INDEX_NAME,
        query={'match_all': {}},
        size=10000  # ES 默认只返回10条，需要显式调大
    )
    hits = res['hits']['hits']
    new_hits = []
    for h in hits:
        new_hits.append({'_id': h.get('_id'), **h.get('_source', {})})
    return new_hits


# 删除全部数据（保留索引结构）
@es_router.delete('/delete_all')
async def delete_all_data(es:AsyncElasticsearch = Depends(init_es)):
    res = await es.delete_by_query(
        index=settings.INDEX_NAME,
        query={'match_all': {}},
        refresh=True
    )
    return {
        'msg': '删除成功',
        'deleted': res.get('deleted', 0)
    }

