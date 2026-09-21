import httpx
from fastapi import APIRouter
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

from crud.milvus.search import search_milvus_data
from crud.es.create import search_data, get_es

ai_router = APIRouter(prefix='/ai', tags=['LLM'])


# ========== 配置类 ==========
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    RERANK_MODEL_NAME: str
    RERANK_URL: str
    QWEN_API_KEY: str
    QWEN_MODEL_NAME:str
    QWEN_BASE_URL:str

settings = Settings()

model = ChatOpenAI(
    model=settings.QWEN_MODEL_NAME,
    api_key=settings.QWEN_API_KEY,
    base_url=settings.QWEN_BASE_URL,
    temperature=0
)

# RRF 常数：k 越大，排名差异对最终分数的影响越小
RRF_K = 60


def _hit_field(hit: dict, field: str):
    """兼容 Milvus 命中结构：字段可能在顶层，也可能嵌套在 entity 中"""
    return hit.get(field) if field in hit else hit.get('entity', {}).get(field)


def rrf_fusion(es_hits: list[dict], milvus_hits: list[dict], k: int = RRF_K) -> list[dict]:
    """RRF 粗融合：合并关键词召回(ES)与向量召回(Milvus)，输出文档级统一排序。

    score(doc) = Σ 1 / (k + rank)，ES 的 _id 与 Milvus content_id 的 doc_id 前缀
    作为文档对齐键；同一文档多个分片命中时只取排名最靠前的一个参与计分。
    """
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}

    # 关键词召回：ES 的 _id 即文档ID
    for rank, hit in enumerate(es_hits):
        doc_id = str(hit.get('_id', ''))
        if not doc_id:
            continue
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
        docs[doc_id] = hit

    # 向量召回：content_id 形如 "{doc_id}-{chunk_index}"
    best_rank: dict[str, int] = {}
    for rank, hit in enumerate(milvus_hits):
        content_id = str(_hit_field(hit, 'content_id') or '')
        doc_id = content_id.split('-')[0] if content_id else ''
        if not doc_id or doc_id in best_rank:
            continue
        best_rank[doc_id] = rank
        docs[doc_id] = hit

    for doc_id, rank in best_rank.items():
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [
        {'doc_id': doc_id, 'rrf_score': round(score, 6), 'hit': docs[doc_id]}
        for doc_id, score in ranked
    ]


def _hit_text(hit: dict) -> str:
    """从融合命中中提取正文：优先 content，其次 summary、title"""
    for field in ('content', 'summary', 'title'):
        text = _hit_field(hit, field)
        if text:
            return str(text)
    return ''


async def rerank_call(query: str, rrf_items: list[dict], top_n: int) -> list[dict]:
    """调用重排模型对粗融合结果精排，返回 top_n 条最相关结果"""
    items = [(item, _hit_text(item['hit'])) for item in rrf_items]
    items = [(item, text) for item, text in items if text]
    if not items:
        return []

    payload = {
        'model': settings.RERANK_MODEL_NAME,
        'input': {
            'query': query,
            'documents': [text for _, text in items],
        },
        # 不要求返回文档原文，按 index 自行映射，节省响应体积
        'parameters': {'top_n': top_n, 'return_documents': False},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            settings.RERANK_URL,
            headers={'Authorization': f'Bearer {settings.QWEN_API_KEY}'},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    results = data['output']['results']
    return [
        {
            'index': r['index'],
            'doc_id': items[r['index']][0]['doc_id'],
            'relevance_score': r['relevance_score'],
            'text': items[r['index']][1],
            'hit': items[r['index']][0]['hit'],
        }
        for r in results
    ]

def build_context(data):
    context = ''
    for d in data:
        context = context + d.get('text')
    return context

# 智能问答
@ai_router.post('/invoke')
async def ai_invoke(query: str, top_n: int = 5):
    # 向量召回
    milvus_data = await search_milvus_data(query)
    # 关键词召回
    es = await get_es()
    es_data = await search_data(query, es)

    milvus_hits = milvus_data.get('data', []) if isinstance(milvus_data, dict) else milvus_data
    es_hits = es_data if isinstance(es_data, list) else es_data.get('data', [])

    # RRF 粗融合
    rrf_data = rrf_fusion(es_hits, milvus_hits)
    # 重排模型精排，取最相关 top_k
    rerank_data = await rerank_call(query, rrf_data, top_n)

    context = build_context(rerank_data)

    response = await model.ainvoke([
        SystemMessage("""
            你是企业知识库助手，只根据【检索资料】回答用户问题。
            若资料不足以回答，明确说不知道，不要编造；
            凡是依据某条资料做出的称述，必须在句末标注对应编号，如【1】，【2】；
            编号必须与资料列表一致，不要标注未使用的编号，不要编造文档标题或链接；
            回答简洁，必要时列出条目
        """),
        HumanMessage(f"检索资料：{context} \n\n 用户问题：{query}")
    ])

    return response

