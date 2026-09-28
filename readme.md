# Knowledge Agent

基于 FastAPI 的企业知识库后端服务：文档解析入库、RAG 检索问答、知识图谱构建、团队权限管理，以及语音识别/合成（ASR/TTS）能力。

## 技术栈

| 类别 | 技术 |
|---|---|
| Web 框架 | FastAPI + Uvicorn（异步） |
| 关系库 | PostgreSQL（SQLAlchemy 2.0 async） |
| 文档库 | MongoDB（Beanie ODM） |
| 向量检索 | Milvus |
| 全文检索 | Elasticsearch 8（IK 分词） |
| 知识图谱 | Neo4j |
| 消息队列 | RabbitMQ（aio_pika） |
| 对象存储 | RustFS（S3 兼容，预签名 URL） |
| LLM | 通义千问（Qwen，OpenAI 兼容接口）+ LangChain / LangGraph |
| Embedding / Rerank | 独立 embedding 模型 + rerank 服务 |
| 语音 | 腾讯云 ASR / TTS（WebSocket 流式） |
| 联网搜索 | BochaAI（知识库相关性不足时兜底） |
| 鉴权 | JWT（access + refresh）+ bcrypt |

## 项目结构（2026-09 重构后）

```
core/      config.py(统一 Settings)、database.py(统一 PG engine/Base)、security.py(鉴权依赖)
models/    纯 ORM：user、document、graph_document、content(Beanie)、team、permission、review、chat
schemas/   Pydantic DTO：user、document、content、graph、search、team、permission、review、chat
api/       全部路由：user、role、team、permission、review、document、mongo、file、publish、
           es、milvus、neo4j、ai、chat、voice
services/  document_service、content_service、graph_service、llm_service
clients/   rustfs、es_client、milvus_client、neo4j_client、rabbitmq/、tencent_speech、web_search
utils/     auth、hashing、split_file、parsers/(pdf、docx、xlsx、epub 等)
scripts/   基础设施检查、OpenAPI 导出、全链路/回归/语音测试脚本
main.py    路由挂载 + lifespan 初始化（RustFS bucket、Mongo、MQ、ES、Neo4j）
```

## 核心流程

```
上传文件(/restfs) → 解析切片 → 保存草稿(PG + Mongo)
→ 发布(/publish) → RabbitMQ 三条队列:
     INDEX        → Elasticsearch 全文索引
     BY_DOC_IDS   → Embedding → Milvus 向量入库
     BUILD_BY_DOC_IDS → LLM 抽取实体关系 → Neo4j 知识图谱
→ 问答(/ai、/chat) → ES + Milvus(+ 图谱) 混合检索 → Rerank → LLM 生成
     知识库最高相关分低于 WEB_SEARCH_MIN_SCORE 时联网搜索兜底
```

各流程结果回写 `kh_document` 的 flow 状态字段，便于追踪发布进度。

## 路由前缀

| 模块 | 前缀 | 说明 |
|---|---|---|
| 认证/用户 | `/user`、`/role` | 登录、JWT、用户与角色 |
| 组织 | `/team`、`/permission` | 团队、权限 |
| 内容 | `/knowledge_doc`、`/pg`、`/mongo` | 文档 CRUD、解析状态 |
| 文件 | `/restfs` | 上传/下载/预签名 URL |
| 发布 | `/publish` | 触发 MQ 入库流水线 |
| 检索 | `/es`、`/milvus`、`/neo` | 全文 / 向量 / 图谱 |
| AI | `/ai`、`/chat` | 问答调用、会话管理 |
| 审核 | `/review` | 内容审核流 |
| 语音 | `/voice` | TTS(HTTP/WS)、STT(WS)，WS 鉴权走 query token |

> 重构变更：`/restFS/* → /restfs/*`、`/Milvus/* → /milvus/*`，前端需同步。
> Vite 代理的 rewrite 对 WebSocket upgrade 不生效，`/voice` 额外挂了 `/api/voice` 前缀别名。

## 快速开始

### 环境要求

- Python 3.11+（Windows 下已自动切换 SelectorEventLoop，psycopg 异步必需）
- Docker / Docker Compose（中间件全家桶）

### 1. 配置环境变量

```bash
cp .env.example .env   # 若无模板则手动创建，见下表必填项
```

### 2. 启动基础设施

```bash
docker compose up -d   # postgres、mongodb、milvus、elasticsearch、neo4j、rabbitmq、rustfs 等
```

> 资源提示：ES + Milvus + Neo4j + PG + Mongo + RabbitMQ + etcd + RustFS 全家桶，建议 16G 内存起。

### 3. 启动应用

```bash
pip install -r requirements.txt
python scripts/run_uvicorn.py     # 或 uvicorn main:app --reload --port 8000
```

启动时 lifespan 自动初始化 RustFS bucket、Mongo 连接、MQ 队列、ES、Neo4j 驱动。

访问 `http://localhost:8000/docs` 查看 OpenAPI 文档。

### 主要环境变量（.env）

| 分组 | 变量 | 说明 |
|---|---|---|
| LLM | `QWEN_API_KEY` `QWEN_BASE_URL` `QWEN_MODEL_NAME` | 通义千问 |
| | `EMBEDDINGS_MODEL_NAME` `RERANK_MODEL_NAME` `RERANK_URL` | 嵌入 / 重排 |
| 存储 | `POSTGRES_*` `MONGO_URI` `DB_NAME` | PG / Mongo |
| | `ES_HOST` `ES_BASIC_AUTH` `INDEX_NAME` | Elasticsearch |
| | `MILVUS_URL` `MILVUS_TOKEN` `COLLECTION_NAME` `DIMENSIONS` | Milvus |
| | `NEO4J_URI` `NEO4J_USER` `NEO4J_PASSWORD` | Neo4j |
| | `RUSTFS_ENDPOINT` `RUSTFS_ACCESS_KEY` `RUSTFS_SECRET_KEY` `RUSTFS_BUCKET` | 对象存储 |
| MQ | `RABBITMQ_URL` `QUEUE_INDEX` `QUEUE_RAG` `QUEUE_KG` | RabbitMQ |
| 鉴权 | `JWT_SECRET_KEY`（生产必改）`JWT_EXPIRE_MINUTES` | JWT |
| 搜索 | `BOCHAAI_KEY` `WEB_SEARCH_MIN_SCORE` `WEB_SEARCH_COUNT` | 联网兜底 |
| 语音 | `TENCENT_SECRET_ID` `TENCENT_SECRET_KEY` `TENCENT_APP_ID` | 留空时语音接口返回明确错误 |

## 开发辅助脚本

```bash
python scripts/check_infra_state.py     # 检查各中间件连通性
python scripts/test_fullchain_http.py   # 发布→MQ→ES/Milvus/KG 全链路测试
python scripts/test_regression.py       # 回归测试
python scripts/dump_openapi.py          # 导出 OpenAPI JSON
python scripts/test_chat.py / test_voice.py
```

## 相关文档

- `docs/deployment-tencent-cloud.md` — 腾讯云部署指南
- `docs/llm-private-deployment.md` — LLM 私有化部署
- 前端工程：`kh_frondend`（Vue3 + TS + ElementPlus，`/api` 代理到本服务）

## 已知问题与技术债

- **密钥硬编码**：`core/config.py` 仍有 PG/RabbitMQ 默认弱密码与 `BOCHAAI_KEY` 兜底值，生产环境必须通过 `.env` 覆盖并轮换
- **CORS 写死** `http://localhost:5173`，上线需换生产域名
- **pymilvus 3.0.1 vs Milvus 镜像 v2.4.0** 版本兼容性未实测
- compose 中 `mysql`、各类管理工具（pgAdmin/RedisInsight/Kibana/Neo4j Browser 等）为残留或仅限开发，生产应移除或不暴露公网
- LLM 调用（rerank/embedding/抽取）无退避重试，限流时会失败

## 建议上线顺序

1. 密钥全部环境变量化 + 换强密码
2. 应用单独 Dockerfile，精简 compose（去管理工具和 mysql 残留）
3. 网关层 HTTPS + CORS 收紧
4. 预发完整跑一遍链路（publish → MQ → ES/Milvus/KG → /ai 问答）
5. 备份方案（volumes 定时备份）+ 监控告警（DLQ 积压、容器健康）
