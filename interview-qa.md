# 企业知识库系统（Knowledge Agent）面试问答

> 基于本项目真实架构与技术实现整理。项目 = FastAPI + PostgreSQL + MongoDB + Elasticsearch + Milvus + Neo4j + RabbitMQ + Qwen LLM 的 RAG 知识库系统。

## 0. 项目介绍模板（1~2 分钟）

"这是一个企业级知识库系统，支持文档发布、多路检索和智能问答。后端基于 FastAPI 全异步架构，存储层按数据特征做了异构选型：PostgreSQL 存文档元数据、MongoDB 存正文、Elasticsearch 做关键词全文检索（IK 中文分词）、Milvus 做向量语义检索、Neo4j 存知识图谱。文档发布后通过 RabbitMQ 异步分发到三个消费链路：ES 索引构建、RAG 切片向量化、大模型抽取实体关系写图。问答走 RAG 流程：ES + Milvus 双路召回 → RRF 粗融合 → Rerank 模型精排 top-k → 大模型带引用生成答案。我负责检索链路、MQ 可靠性和知识图谱模块，期间解决过同步调用阻塞事件循环、ES 中文分词失配、死信队列缺失等问题。"

---

## 一、架构与选型

### Q1. 为什么存储层要用这么多数据库，而不是统一用一个？

**答**：按数据访问模式做异构选型，各自发挥所长：

| 存储 | 存什么 | 选型理由 |
|---|---|---|
| PostgreSQL | 文档元数据（标题、状态、发布时间） | 结构化数据、事务、状态管理 |
| MongoDB | 文档正文 | 大文本、schema 灵活、按文档 ID 整取 |
| Elasticsearch | 关键词倒排索引 | 全文检索、IK 中文分词、高亮 |
| Milvus | 向量（分片级 embedding） | 专用向量库，ANN 近似检索快 |
| Neo4j | 知识图谱（实体-关系） | 图查询，多跳关系遍历用关系库表达最自然 |
| RabbitMQ | 异步任务队列 | 发布后索引构建、向量化、图谱抽取都是耗时任务，解耦削峰 |

一个库全干这些活理论上可行，但每种数据结构的查询模式完全不同，专用系统在各自领域性能有数量级优势。代价是运维复杂度，所以用 docker-compose 统一编排。

### Q2. 文档发布为什么走消息队列，而不是同步做？

**答**：发布一次文档要触发三件事：ES 建索引、切片 + embedding 向量化写 Milvus、大模型抽取实体关系写 Neo4j。其中向量化和 LLM 抽取是秒级~分钟级的耗时操作，同步做会让发布接口长时间阻塞，用户体验差；而且任一环节失败不应导致发布失败。引入 RabbitMQ 后：发布接口只负责改状态 + 投递消息（毫秒级返回），三个消费者异步消费各自的队列，天然解耦、削峰，失败的消息进死信队列可重试。

### Q3. 为什么整个后端全异步（async）？有什么代价？

**答**：这个系统的瓶颈几乎全在 I/O：数据库、ES、Milvus、Neo4j、RabbitMQ、LLM HTTP 调用。FastAPI + asyncio 单线程事件循环即可承载大量并发 I/O，不需要为每个请求开线程。代价是**整个调用链必须全程无同步阻塞**——这是本项目踩过的真实大坑：同步调用（如 `embed_query`）会冻结事件循环，一个慢请求拖垮所有接口。另外 Windows 上 psycopg 异步模式与默认 ProactorEventLoop 不兼容，需要在 main.py 里切 SelectorEventLoop。

---

## 二、RAG 检索链路（核心）

### Q4. 完整描述一次问答请求的流程

**答**：`POST /ai/invoke`，共五步：

1. **双路召回**：Milvus 向量召回（query 向量化 → ANN 检索 top-10 分片）+ ES 关键词召回（multi_match，title^3/summary^2/content 加权，IK 分词）
2. **RRF 粗融合**：两路结果按文档 ID 对齐合并，`score = Σ 1/(60 + rank)`，产出文档级统一排序
3. **Rerank 精排**：粗融合结果抽正文，调重排模型（qwen3.7-text-rerank）算 query-doc 相关性分，取 top-k
4. **上下文拼接**：top-k 的文本拼成检索资料
5. **LLM 生成**：带系统提示词约束（只依据资料回答、句末标引用编号【1】【2】、不足时明确说不知道），由 qwen3.8-max 生成答案

### Q5. RRF 的原理是什么？k=60 有什么含义？

**答**：Reciprocal Rank Fusion，把多个召回源的排名融合成统一排序，公式 `score(d) = Σ 1/(k + rank_d)`，k 是平滑常数（本项目 60）。特点：

- **只依赖排名不依赖分数**：ES 的 BM25 分和 Milvus 的余弦距离量纲完全不同，直接加权比较没有意义；RRF 把两边都归一化为"排名的倒数"，天然可加
- **k 的作用**：k 越小，排名靠前的结果优势越明显；k=60 是论文经验值，让不同召回源的排名差异被适度压缩
- 相比线性加权归一化分数，RRF 对分数分布的极端值不敏感，实现简单且效果稳定

实现细节：本项目 ES 的 `_id` 就是文档 ID，Milvus 的 `content_id` 是 `{doc_id}-{chunk_index}`，按这个键做文档级对齐；同一文档多个分片命中时**只取排名最靠前的分片计分**，避免长文档因分片多被重复加权。

### Q6. 有了召回融合，为什么还要 Rerank 精排？

**答**：粗排和精排解决的问题不同。粗排（ES/Milvus）要快，用倒排索引和 ANN 近似检索在毫秒级从全库捞候选，代价是相关性判断粗糙（BM25 只看词频、双塔 embedding 只看向量相似度）。Rerank 是 cross-encoder，把 query 和候选文档**拼在一起**过 Transformer，做真正的逐 token 交互，相关性判断准得多，但慢——所以只对粗排后的少量候选（本项目是融合后的全部候选，通常 ≤20 条）精排。这是"召回-精排"两级漏斗的经典设计：粗排保召回率，精排保准确率。

### Q7. Milvus 向量检索的原理和关键参数？

**答**：分片文本经 text-embedding-v3 转成 1024 维向量存 Milvus。检索时把 query 同样向量化，按 `COSINE` 度量做 ANN 检索，`nprobe=16` 控制 IVF 索引搜索的聚类单元数量：nprobe 越大召回越准但越慢，是召回率-延迟的权衡。注意两个工程点：embedding 调用必须用异步版（`aembed_documents`），且 Qwen 接口单次有文本条数上限，本项目按每批 10 条分批向量化。

### Q8. ES 中文检索遇到过什么问题？

**答**：踩过"索引有数据但查不出来"的经典坑：建索引时 mapping 里 `title/summary/content` 没指定 analyzer，ES 默认用 standard 分词器把中文切成**单字**；而查询侧指定了 `analyzer: ik_smart`（按词切分）。"企业知识库"在 ik_smart 下是一个词 token，在单字索引里永远匹配不到 → 0 命中。修复：mapping 里给文本字段显式指定 `"analyzer": "ik_smart"`，索引与查询分词一致。教训：**中文场景必须索引侧和查询侧使用同一套 IK 分词器**；改 mapping 必须删索引重建，所以上线前要把 mapping 定稿。

### Q9. 文档分块（chunking）怎么做？参数怎么定？

**答**：用 `RecursiveCharacterTextSplitter`，分隔符按句级优先（。！？；\n），`chunk_size=200`、`chunk_overlap=50`。分块原因：长文档整体 embedding 会稀释语义，LLM 上下文也放不下；检索粒度到分片更精准。参数权衡：chunk 太小语义碎片化、太大检索粒度粗；overlap 防止关键信息被切在边界上。Milvus 存的 `content_id` 形如 `{doc_id}-{chunk_index}`，检索后能回溯到所属文档。

### Q10. 为什么双路召回比单路好？

**答**：关键词检索和语义检索互补。ES 对专有名词、精确术语（如 "Milvus 报错 xxx"）强，但换种说法就检索不到；向量检索理解语义（"怎么备份"能命中"数据持久化"），但对生僻词、数字、代码不敏感。双路召回 + RRF 融合取并集，对两种 query 形态都稳。本项目还规划了第三路：Neo4j 图谱的实体关联，属于结构化知识补充。

---

## 三、知识图谱

### Q11. 实体关系抽取是怎么做的？

**答**：发布文档后 KG 消费者从 MongoDB 取正文，用 qwen3.8-max 的 `with_structured_output` 做抽取。关键在 prompt 设计：

- **输出约束**：严格 JSON，只有 entities/relationships/cypher 三个顶层字段
- **Schema 约束**：实体 = label（大驼峰）+ name + properties；关系 = 起终点 + 关系类型（英文大写下划线）
- **防幻觉约束**：只保留原文出现的信息、禁止编造关联；实体标签限定复用固定体系（Enterprise、TechComponent、Fault 等 9 类）
- **直接生成 Cypher**：要求用 MERGE（以 name 为唯一键）去重，先建节点再建关系

结构化输出由 pydantic 模型校验，不合格输出直接报错，比裸文本 + 正则解析可靠得多。

### Q12. 为什么 Cypher 用 MERGE 而不是 CREATE？

**答**：CREATE 无条件新建，同一实体被多篇文档抽取时会生成重复节点，图被污染成"多胞胎"。MERGE 以 name 为匹配键：节点不存在才创建，存在则复用，天然幂等——这意味着同一条消息失败重试也不会产生脏数据。这是"幂等写入"思想在图数据库的体现，和本项目消息队列的重试语义配合。

### Q13. 图谱在知识库里的价值是什么？

**答**：倒排/向量检索都是"相似匹配"，图表达的是**实体间的显式关联**。比如"某故障依赖哪些技术组件""某业务属于哪个部门"这类多跳查询，SQL 要多次 JOIN、向量检索无法表达，Cypher 一条语句即可。图谱补上了知识库的结构化组织能力，与文本检索互补；后续可用实体关系做 query 扩展（问"ETCD"时顺带召回关联组件文档）。

---

## 四、消息队列与可靠性

### Q14. RabbitMQ 消息不丢失靠哪几层保证？

**答**：本项目三层保障：

1. **生产者**：消息 `delivery_mode=PERSISTENT`，落到磁盘
2. **Broker**：队列 `durable=True`，RabbitMQ 重启队列和消息还在
3. **消费者**：手动 ACK（`message.process()` 上下文，处理成功才 ack）；失败 reject 且不 requeue

配套死信机制：主队列声明时绑定 DLX（`x-dead-letter-exchange` + routing-key），handler 抛异常的消息自动进对应 `.dlq` 队列，不丢、可人工重发。关键坑：**给已存在的队列改声明参数会报 PRECONDITION_FAILED**，必须先删队列再重建，这也是本项目实际操作过的。

### Q15. 为什么每个队列用独立 channel？

**答**：RabbitMQ 的 channel 是轻量连接内的逻辑通道。独立 channel 的好处：某个消费链路的 channel 因异常关闭（如网络抖动、队列声明冲突）不影响其他链路；各队列的消费速率差异不会互相阻塞（慢的 LLM 抽取不会挡住快的 ES 索引）。代价只是多维护几个 channel 对象，用全局 manager 单例统一管理。

### Q16. 消息重复消费和积压怎么处理？

**答**：

- **重复消费**：投递至少一次语义下无法完全避免。本项目用两层幂等：业务上 KG 写 Neo4j 用 MERGE（天然幂等）、ES 按 doc_id 作为文档 `_id` 写入（覆盖即幂等）、PG 元数据表 doc_id 唯一约束 + 存在性检查返回 409
- **积压**：监控 DLQ 和主队列深度；消费者是常驻协程，处理慢的瓶颈（如逐条 embedding）通过批量化解决；必要时可水平扩展消费实例（RabbitMQ 自动轮询分发）
- 死信消息支持从管理界面重新发布回原队列

### Q17. 为什么消费失败直接进死信，而不是无限重试？

**答**：当前设计是"快速失败 + 死信人工介入"。无限自动重试有两个问题：瞬时故障和永久故障无法区分（如消息 payload 格式错了，重试一万次也没用）；重试会占用消费能力，压垮正常消息处理。更完善的方案是延迟重试 N 次再进死信（用 TTL 重试队列 + x-death 计数），但复杂度更高，当前阶段人工从 DLQ 重发成本更低、行为更可控。

---

## 五、异步、性能与工程踩坑（重点，面试加分项）

### Q18. 遇到过"MQ 一跑任务，所有接口全部无响应"的问题，怎么排查的？

**答**：这是本项目真实事故。现象：只要 RAG 消费任务执行，其他 API 全部卡死。排查思路：

1. 先确认不是数据库/网络问题——各存储本身响应正常
2. 怀疑事件循环被阻塞：asyncio 是单线程协作式调度，**任何一个协程里出现同步阻塞调用，整个循环冻结**，所有请求都排队
3. 逐段审查三个消费链路的调用：ES 用 AsyncElasticsearch（OK）、PG/Mongo/Milvus/Neo4j 都是异步客户端（OK），最终定位到 `embedding_text` 里用了**同步的** `embeddings_model.embed_query()`——每个分片一次同步 HTTP 请求，几十个分片就是几十秒循环冻结
4. 修复：换成异步 `aembed_documents` 并按批（10 条/批）请求

**通用结论**：async 项目里排查"全员卡死"，第一嫌疑永远是同步 I/O 或 CPU 密集操作混进了协程。

### Q19. 怎么判断一个函数该写成 async 还是同步？

**答**：看它是 I/O 密集还是 CPU 密集。async 的价值是**等待 I/O 时让出控制权**；纯计算函数（如本项目的 RRF 融合，几十条数据的排序）写成 async 没有任何收益，await 一个没有 await 点的协程和同步调用执行方式完全一样。反过来，如果同步函数计算量很大（如大数组排序），正确做法不是包 async，而是 `asyncio.to_thread` 丢线程池。判断标准一句话：**async 解决的是等待问题，不是计算问题**。

### Q20. FastAPI 的 Depends 有什么坑？

**答**：`Depends` 是 FastAPI 的依赖注入标记，**只有经由 FastAPI 请求处理时才被解析**。本项目踩过：`create_graph_doc(doc_id, db: AsyncSession = Depends(get_db))` 被其他模块当普通函数直接调用时，`db` 拿到的是 `Depends` 对象而不是 session，调用必炸。解法：业务函数不写 Depends 默认参数，session 由函数内部自行创建（短会话），或者由调用方显式传入。这也引出了分层原则：**被复用的业务函数不要和路由层耦合**。

### Q21. 两个模块互相 import 导致循环导入，怎么解？

**答**：本项目的 storage 模块和 router 模块曾互相引用（save_neo4j 从 create 导入，create 又从 save_neo4j 导入），启动即 ImportError 或行为不稳定。解法是**让依赖单向**：把被双方依赖的逻辑下沉到独立底层模块（抽取逻辑移到 entityAndrelationship 模块），router → storage → extraction 单向引用。通用手段：抽公共模块、延迟导入、依赖注入，但最根本的是先理清模块分层再写 import。

### Q22. 调第三方 HTTP 服务（如 rerank）为什么用 httpx 而不是官方 SDK？

**答**：三点考虑：

1. **异步**：官方 SDK 大多是同步实现，在 async 服务里直接调会阻塞事件循环（与 Q18 同一个坑）
2. **依赖轻**：httpx 项目本来就有，官方 SDK 多引入一个依赖树；SDK 只是 HTTP 的封装，协议简单时直接调 REST 更透明
3. **可控**：超时、重试、错误处理自己掌控；SDK 的返回对象往往是自定义类型，FastAPI 无法直接序列化，还要手动转换

当然，协议复杂的服务（如 Milvus gRPC）该用 SDK 还是用 SDK。

### Q23. 为什么 LLM 返回要用结构化输出（structured output）？

**答**：让大模型输出"能被程序消费"的结果。实体关系抽取用 pydantic 的 `Neo4jSchema` 做 JSON Schema 约束，输出直接通过模型校验，非法输出当场报错重试，而不是拿正则从自由文本里扣字段。这是 LLM 应用工程化的基本手段之一，另外还有：输出格式约束写进 prompt、温度设 0 降低随机性（本项目抽取和问答都 `temperature=0`）。

### Q24. 如果要上线，检索链路还要补什么？

**答**：结合本项目现状：LLM/embedding/rerank 调用需要重试与降级（API 限流时目前会失败）；召回结果需要缓存（热门 query）；加评测集做检索质量回归（命中率、MRR）；日志从 print 换结构化 logging 并接入监控；按访问量给 Milvus 换索引类型、ES 调优分片；图谱检索链路（第三路召回）接入 RRF；Rerank 的 key 与端点兼容性验证。再往上：回答生成可加流式输出（SSE）和多轮对话历史。

---

## 附：可能被追问的快速问答

- **为什么 ES 用 multi_match 的 best_fields？** 希望命中权重最高的字段（标题）作为文档分，而不是跨字段叠加（most_fields）
- **COSINE 度量的前提？** 向量归一化，embedding 模型输出已归一化
- **RRF 和 learning-to-rank 的区别？** RRF 无监督、无需训练数据；LTR 需要标注数据，效果上限更高
- **为什么 PG 存元数据而 Mongo 存正文？** 元数据需要事务与强 schema（状态流转），正文是整存整取的大对象，文档模型更合适
- **Windows 上 psycopg async 的坑？** ProactorEventLoop 不支持 psycopg3 异步，需 SelectorEventLoop；Linux 部署无此问题
- **消息 ack 时机？** 处理成功才 ack（process 上下文），失败 reject 进 DLQ；防止 ack 太早消息丢失、太晚重复消费
