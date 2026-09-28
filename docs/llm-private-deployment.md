# 大模型私有化部署方案

> 目标:把本项目的 LLM 能力(对话、知识图谱抽取、Embedding、Rerank)从阿里云 DashScope 公网 API
> 迁移到自建/内网的 OpenAI 兼容推理服务,数据不出内网。
> 编写时间:2026-09。

## 1. 现状分析

### 1.1 LLM 调用点清单

| # | 用途 | 代码位置 | 调用方式 | 当前模型 |
|---|---|---|---|---|
| 1 | 智能问答(最终生成) | `api/ai.py` | `ChatOpenAI`(langchain,OpenAI 兼容) | `QWEN_MODEL_NAME` = qwen3.8-max |
| 2 | 知识图谱实体/关系抽取 | `services/llm_service.py` | `ChatOpenAI` + `with_structured_output(Neo4jSchema)` | 同上 |
| 3 | 向量化(入库与查询) | `clients/milvus_client.py` | `OpenAIEmbeddings`(OpenAI 兼容,`dimensions=1024`) | `EMBEDDINGS_MODEL_NAME` = text-embedding-v3 |
| 4 | 检索结果重排 | `api/ai.py::rerank_call` | `httpx` 直连 **DashScope 专有 rerank 接口** | `RERANK_MODEL_NAME` = qwen3.7-text-rerank |

`.env` 中的 `QWEN_IMAGE_MODEL/QWEN_IMAGE_URL`(多模态)当前**未被任何代码使用**,迁移时可忽略。

### 1.2 关键结论

- 调用点 1/2/3 走 **OpenAI 兼容协议**,换成任何 OpenAI 兼容私有推理服务后**代码零改动**,只改 `.env`;
- 调用点 4 是 DashScope 专有格式,**需要小改 `api/ai.py::rerank_call`**(适配代码见 §5.2);
- 换 Embedding 模型后,**Milvus 存量向量必须全量重建**(维度与语义空间不同,见 §5.3)。

## 2. 总体方案

### 2.1 目标架构

```
┌───────────────┐        ┌─────────────────────────────────────┐
│  FastAPI 应用  │        │  内网 GPU 服务器(一台或多台)          │
│               │        │  ┌──────────┐ ┌──────────────────┐  │
│ QWEN_BASE_URL─┼───────►│  │ nginx/   │ │  vLLM #1: LLM    │  │
│               │        │  │ 网关分流  │→│  Qwen3-8B/14B/32B│  │
│ RERANK_URL────┼───────►│  │ :8009    │ │  :8010           │  │
│               │        │  │          │→│  vLLM #2: Embed  │  │
│               │        │  │          │ │  Qwen3-Emb-0.6B  │  │
│               │        │  │          │→│  vLLM #3: Rerank │  │
│               │        │  │          │ │  Qwen3-Rerank-*  │  │
│               │        │  └──────────┘ └──────────────────┘  │
└───────────────┘        └─────────────────────────────────────┘
```

说明:vLLM **单个实例只能跑一种任务**(generate/embed/score),LLM、Embedding、Rerank 需分别起实例;
用 nginx 网关按请求路径分流,应用侧 `QWEN_BASE_URL` 指向网关即可**不改一行代码**。

### 2.2 推理框架选型

| 框架 | LLM 生成 | Embedding | Rerank | 生产成熟度 | 备注 |
|---|---|---|---|---|---|
| **vLLM**(推荐) | ✅ | ✅ `/v1/embeddings` | ✅ `/v1/rerank`、`/score` | 高,社区最活跃 | PagedAttention、连续批处理、量化、structured output |
| SGLang | ✅ | ✅ | 部分 | 高 | 与 vLLM 同级别,团队熟悉可替换 |
| TEI(HuggingFace) | ❌ | ✅ | ✅ | 高 | 只做 Embedding/Rerank,接口与 vLLM 不同(需改代码) |
| Ollama | ✅ | ✅(部分) | ❌ | 中 | 轻量但吞吐低,适合开发机,不适合生产并发 |
| Xinference | ✅ | ✅ | ✅ | 中 | 全栈但运维复杂度高 |

**推荐组合:统一 vLLM(≥ 0.11 稳定版),三实例分别跑三类任务,前端加 nginx 网关。**

## 3. 模型选型与硬件规划

### 3.1 模型选型

| 角色 | 推荐模型 | 备选 | 说明 |
|---|---|---|---|
| 对话 + KG 抽取 | **Qwen3-8B / 14B / 32B**(按 GPU 预算选) | Qwen3-4B(轻量) | 需支持 function calling(vLLM 原生支持,`with_structured_output` 可用) |
| Embedding | **Qwen3-Embedding-0.6B** | bge-m3 | 0.6B 输出维度 **1024**,与当前 `.env` 的 `DIMENSIONS=1024` 完全一致,零改动 |
| Rerank | **Qwen3-Reranker-0.6B / 4B** | bge-reranker-v2-m3 | 0.6B 足够本项目 top_n≤20 的场景 |

> Embedding 若选 4B(输出 2560 维)或 8B(4096 维),必须同步改 `DIMENSIONS` 并重建 Milvus collection
> (collection 的向量维度建后不可改),性价比上 0.6B 是最优解。

### 3.2 显存需求速查(FP16 权重 + KV Cache + 开销)

| 模型 | FP16/BF16 | FP8 | INT4/AWQ | 上下文 |
|---|---|---|---|---|
| Qwen3-8B | ~16 GB | ~8 GB | ~4 GB | 128K(实际受 KV 预算限制) |
| Qwen3-14B | ~28 GB | ~14 GB | ~7 GB | 同上 |
| Qwen3-32B | ~64 GB | ~32 GB | ~16 GB | 同上 |
| Qwen3-Embedding-0.6B | ~2 GB | — | — | 32K |
| Qwen3-Reranker-0.6B / 4B | ~2 GB / ~8 GB | — | — | 32K |

### 3.3 三档硬件方案

| 档位 | GPU | 部署内容 | 适用场景 |
|---|---|---|---|
| 入门 | 单卡 24 GB(RTX 4090 / 3090) | Qwen3-8B(FP8)+ Embedding-0.6B + Reranker-0.6B 共卡分时或 2 卡 | 开发/试点,并发 < 10 |
| 均衡(推荐) | 单卡 48 GB(L40S)或 2×24 GB | Qwen3-14B(FP8)+ Embedding-0.6B + Reranker-0.6B | 正式生产,并发 20~50 |
| 高性能 | 单卡 80 GB(H100/H200/A100) | Qwen3-32B(FP8)+ Embedding-0.6B + Reranker-4B | 高并发/高质量要求 |

> 并发参考:8B@4090 FP8 ≈ 85~100 tok/s(单流);vLLM 连续批处理下单卡可支撑 50~100 并发
> (实际以压测为准)。RAG 场景瓶颈通常先在 Embedding/Rerank 实例,注意给它们留独立显存。

## 4. 部署实施(vLLM)

### 4.1 前置条件

- 宿主机:NVIDIA 驱动 ≥ 535(CUDA 12.2+)、`nvidia-container-toolkit` 已装
- vLLM 镜像:`vllm/vllm-openai:latest`(或固定到你们验证过的版本)
- 模型下载:国内建议 ModelScope(`pip install modelscope && modelscope download --model Qwen/Qwen3-8B --local_dir /data/models/Qwen3-8B`),HuggingFace 用 `HF_ENDPOINT=https://hf-mirror.com`

### 4.2 docker-compose 示例(单机三实例 + 网关)

```yaml
# /data/llm/docker-compose.yml
services:
  # 1) 对话/KG 抽取
  vllm-llm:
    image: vllm/vllm-openai:latest
    ipc: host
    shm_size: 8g
    command: >
      --model /models/Qwen3-8B
      --served-model-name qwen3-8b
      --quantization fp8            # 无 FP8 硬件的卡(A100/3090)改为 awq 或去掉此行用 BF16
      --gpu-memory-utilization 0.9
      --max-model-len 32768         # 按业务上下文定,越大 KV Cache 占用越多
      --enable-prefix-caching
      --api-key ${VLLM_API_KEY}
      --port 8000
    volumes:
      - /data/models:/models
    ports: ["8010:8000"]
    environment:
      - NVIDIA_VISIBLE_DEVICES=0
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped

  # 2) Embedding
  vllm-embed:
    image: vllm/vllm-openai:latest
    ipc: host
    command: >
      --model /models/Qwen3-Embedding-0.6B
      --served-model-name qwen3-embedding
      --task embed
      --dtype half
      --gpu-memory-utilization 0.5
      --max-model-len 8192
      --api-key ${VLLM_API_KEY}
      --port 8000
    volumes:
      - /data/models:/models
    ports: ["8011:8000"]
    environment:
      - NVIDIA_VISIBLE_DEVICES=1
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped

  # 3) Rerank
  vllm-rerank:
    image: vllm/vllm-openai:latest
    ipc: host
    command: >
      --model /models/Qwen3-Reranker-0.6B
      --served-model-name qwen3-reranker
      --task score
      --dtype half
      --gpu-memory-utilization 0.3
      --max-model-len 4096
      --hf-overrides '{"architectures": ["Qwen3ForSequenceClassification"], "classifier_from_token": ["no", "yes"], "is_original_qwen3_reranker": true}'
      --api-key ${VLLM_API_KEY}
      --port 8000
    volumes:
      - /data/models:/models
    ports: ["8012:8000"]
    environment:
      - NVIDIA_VISIBLE_DEVICES=1
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped

  # 4) 网关:按路径分流,应用只配一个地址
  gateway:
    image: nginx:alpine
    ports: ["8009:80"]
    volumes:
      - /data/llm/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    restart: unless-stopped
```

网关分流配置 `/data/llm/nginx.conf`:

```nginx
server {
    listen 80;

    # /v1/embeddings → Embedding 实例
    location = /v1/embeddings {
        proxy_pass http://vllm-embed:8000;
        proxy_read_timeout 120s;
    }
    # /v1/rerank、/score → Rerank 实例
    location ~ ^/(v1/)?(rerank|score) {
        proxy_pass http://vllm-rerank:8000;
        proxy_read_timeout 120s;
    }
    # 其余(chat/completions、models 等)→ LLM 实例
    location / {
        proxy_pass http://vllm-llm:8000;
        proxy_read_timeout 300s;
    }
}
```

> 注:Qwen3-Reranker 在 vLLM 中必须带 `--task score` 和上面的 `--hf-overrides`
> (注入序列分类架构与 yes/no 分类 token),否则无法按 rerank 模型加载。
> 如遇 embedding/rerank 在 V1 引擎异常,加 `VLLM_USE_V1=0` 回退 V0 引擎。

### 4.3 多卡/多机

- 单模型跨卡:`--tensor-parallel-size 2`(如 2×24 GB 跑 14B FP16);注意多卡无 NVLink 时吞吐有折损,优先选"单卡能装下"的档位
- 三类模型可分布到多台机器,nginx 网关的 `proxy_pass` 指向对应主机 IP 即可
- 大模型 + 长上下文同时吃紧时,优先压 `--max-model-len`,不要盲目加大模型

## 5. 应用侧改造

### 5.1 `.env` 配置变更

| 键 | 现值(云上) | 私有化后 |
|---|---|---|
| `QWEN_API_KEY` | 阿里云 key | 与 `VLLM_API_KEY` 一致(网关/实例启用了鉴权时) |
| `QWEN_BASE_URL` | `https://…maas.aliyuncs.com/compatible-mode/v1` | `http://<网关>:8009/v1`(LLM 与 Embedding 共用网关) |
| `QWEN_MODEL_NAME` | `qwen3.8-max` | `qwen3-8b`(即 `--served-model-name`) |
| `EMBEDDINGS_MODEL_NAME` | `text-embedding-v3` | `qwen3-embedding` |
| `RERANK_MODEL_NAME` | `qwen3.7-text-rerank` | `qwen3-reranker` |
| `RERANK_URL` | DashScope rerank 地址 | `http://<网关>:8009/v1/rerank` |
| `DIMENSIONS` | 1024 | 保持 1024(与 Qwen3-Embedding-0.6B 输出一致) |

若不想起网关,也可给 `core/config.py` 新增独立的 `EMBEDDINGS_BASE_URL` 并在
`clients/milvus_client.py` 里使用(小改动,约 3 行)。

### 5.2 `api/ai.py::rerank_call` 适配(必须改)

现状是 DashScope 专有格式;vLLM 的 `/v1/rerank` 是 Cohere 风格(请求 `{model, query, documents, top_n}`,
响应 `{"results": [{"index", "relevance_score"}]}`)。改造方案:新增配置开关,兼容两种后端:

```python
# core/config.py 新增一行
RERANK_API_STYLE: str = "openai"   # "dashscope"=云上专有格式 / "openai"=私有化 vLLM 格式
```

```python
# api/ai.py 中的 rerank_call 改造后
async def rerank_call(query: str, rrf_items: list[dict], top_n: int) -> list[dict]:
    items = [(item, _hit_text(item['hit'])) for item in rrf_items]
    items = [(item, text) for item, text in items if text]
    if not items:
        return []

    if settings.RERANK_API_STYLE == "dashscope":
        # 原云上格式(保留,便于回滚)
        payload = {
            'model': settings.RERANK_MODEL_NAME,
            'input': {'query': query, 'documents': [text for _, text in items]},
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
    else:
        # 私有化 vLLM /v1/rerank(Cohere 风格)
        payload = {
            'model': settings.RERANK_MODEL_NAME,
            'query': query,
            'documents': [text for _, text in items],
            'top_n': top_n,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                settings.RERANK_URL,
                headers={'Authorization': f'Bearer {settings.QWEN_API_KEY}'},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        results = data['results']

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
```

### 5.3 存量数据迁移(重要)

| 数据 | 是否必须重建 | 原因与操作 |
|---|---|---|
| **Milvus 向量** | ✅ 必须全量重建 | 旧向量由 text-embedding-v3 生成,语义空间与新模型不同,混合检索会错乱。操作:先备好重建脚本,对新 embedding 服务跑一遍全量文档重向量化(复用 `clients/milvus_client.py::milvus_insert` 或对每个 doc_id 重新发布触发 RAG 消费),再整体切换 |
| **ES 索引** | ❌ 不用动 | 与 LLM 无关 |
| **PG/Mongo 正文** | ❌ 不用动 | 原始数据不动 |
| **知识图谱(Neo4j/graph_doc)** | 可选 | 换 LLM 后抽取风格会变;存量图可保留,新文档按新模型抽取即可;若追求一致性可清空重建 |
| **Milvus collection schema** | 视情况 | 若 Embedding 维度不变(1024→1024),collection 可以原地清空重灌;若换维度,必须删 collection 重建(现有 `/milvus/create_table` 会先 drop 再建,**注意先备份**) |

> 重建期间建议灰度:新向量写进**新建的 collection**、验证检索效果后再切换 `COLLECTION_NAME`,
> 避免把线上唯一的一份向量冲掉。

## 6. 安全与网络

- 推理服务只绑定内网(compose 端口仅暴露给网关,应用层不要直连 8010/8011/8012)
- vLLM 统一设 `--api-key`,应用 `.env` 里 `QWEN_API_KEY` 改为相同值(代码已自动带上)
- 网关层按需加 HTTPS/客户端证书;GPU 服务器防火墙只放行应用网段
- 模型权重目录 `/data/models` 按敏感资产管理,控制只读挂载
- 若涉及保密语料微调,另做数据脱敏评审(本方案默认不微调,直接用开源权重)

## 7. 监控与高可用

- vLLM 自带 `/metrics`(Prometheus),监控项:排队延迟、批大小、KV Cache 使用率、GPU 显存/利用率
- 健康检查:`GET /v1/models` 或 `/health`;compose 已配 `restart: unless-stopped`,生产可上双实例 + 网关负载均衡
- 日志:容器 stdout 采集;应用侧 `api/ai.py` 建议把每次 `ai_invoke` 的耗时/模型名打进日志,便于对比云上与私有的质量差异

## 8. 迁移 checklist 与回滚

| 步骤 | 操作 | 验证 |
|---|---|---|
| 1 | 部署三实例 + 网关,模型下载完成 | `curl http://网关/v1/models` 返回三个模型 |
| 2 | 新起测试 collection,跑重向量化脚本 | 抽样检索与云上结果对比 |
| 3 | 改 `.env` 六项 + `RERANK_API_STYLE=openai`,重启应用 | `/ai/invoke` 通、KG 消费正常、日志无 4xx/5xx |
| 4 | 灰度:切 10% 流量或仅内部用户 | 观察 1~3 天,对比回答质量/延迟 |
| 5 | 全量切换,下线 DashScope | 云上账单归零 |

**回滚**:`.env` 改回云上六项 + `RERANK_API_STYLE=dashscope`,重启应用即可(代码已双格式兼容);
Milvus 若已全量重建为新模型向量,回滚云上 embedding 后需再跑一次反向重建或直接保留
(0.6B 与 text-embedding-v3 均 1024 维,但语义空间不同,建议重建)。

## 9. 验收标准

功能验收(私有化 vs 云上,各抽 20 个真实 query):

- [ ] Embedding:`/v1/embeddings` 返回维度 = 1024;Milvus 检索 Top-10 与云上重合率 ≥ 70%
- [ ] Rerank:相关性分数排序与云上一致率 ≥ 80%(允许分数绝对值不同,看序)
- [ ] KG 抽取:20 篇文档结构化输出(JSON schema)成功率 100%,实体/关系合理
- [ ] `/ai/invoke`:端到端回答可用(引文标注【n】正确),无编造
- [ ] 性能:单流首 token 延迟 < 3s,总时延 < 60s;10 并发下错误率 < 1%
- [ ] 稳定性:压测 2 小时无 OOM/崩溃,GPU 显存水位 < 90%

## 10. 参考

- vLLM 官方文档(Online Serving / OpenAI-Compatible Server):https://docs.vllm.ai/en/latest/serving/online_serving/
- Qwen3 系列权重:https://huggingface.co/Qwen (ModelScope:https://modelscope.cn/organization/qwen)
- vLLM 部署 Qwen3-Embedding/Reranker 实践:
  https://github.com/hiennguyen9874/vllm-serving/blob/master/Qwen3-Embedding/QWEN3_EMBEDDING.md
- Qwen3 显存与 GPU 选型参考:https://www.spheron.network/blog/run-qwen3-locally-gpu-requirements-2026/
