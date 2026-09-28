# knowledge-agent 腾讯云部署文档

目标：一台全新的高配腾讯云服务器（CVM），用 **Docker Compose** 同时拉起后端应用 + 全部中间件，前端构建产物 + **Nginx** 做 HTTPS 与 `/api` 反向代理，绑定域名。

适用版本：后端 `main` 分支（结构重构后）、前端 `kh_frondend`。

---

## 0. 架构总览

```
                    用户浏览器 (https://your-domain.com)
                              │
                    ┌─────────▼─────────┐
                    │   CVM (腾讯云)     │
                    │                   │
                    │  ┌─────────────┐  │   /            → 前端静态文件 (nginx)
                    │  │  nginx :443 │──┼──┤
                    │  │   :80→443   │  │   /api/*       → 后端 :8000 (剥掉 /api 前缀)
                    │  └─────────────┘  │
                    │        │          │
                    │  ┌─────▼───────┐  │
                    │  │ aiagent-api │  │  FastAPI + MQ 消费者(同进程)
                    │  │   :8000     │  │
                    │  └──┬───┬───┬──┘  │
                    │  postgres  mongodb │
                    │  milvus    elasticsearch
                    │  neo4j     rabbitmq
                    │  rustfs  (+etcd/minio 供 Milvus)
                    └───────────────────┘
```

要点：
- 后端 `main.py` 的 lifespan 里 `init_mq()` 会启动 3 个 MQ 消费协程，**API 容器同时就是 worker**，不需要独立的 consumer 服务。
- 只有 `80/443`（和限源 IP 的 `22`）对外，所有中间件端口**不映射公网**或仅内网。

---

## 1. 前置条件

| 项 | 要求 |
|---|---|
| 服务器 | CVM，**8C16G 起**（Milvus+ES+Neo4j+PG+Mongo+RustFS 同机，4G 不够），系统盘 ≥ 100G，Ubuntu 22.04 LTS |
| 安全组 | 入方向放行 `22`(限你自己的 IP)、`80`、`443`。**不要**放行 8000/5432/9200/19530/7474/15672/9000 等 |
| 域名 | 一条 A 记录指向服务器公网 IP，如 `kh.your-domain.com`；已在腾讯云申请/下载对应 SSL 证书 |
| 软件 | Docker Engine ≥ 24、Docker Compose plugin v2：`curl -fsSL https://get.docker.com \| sudo sh` 后 `sudo usermod -aG docker $USER` 重登 |
| 密钥/Token | 通义千问 `QWEN_API_KEY`、Bocha `BOCHAAI_KEY`（联网兜底） |

```bash
# 服务器初始化
sudo apt update && sudo apt -y upgrade
sudo apt install -y git nginx
docker --version && docker compose version
```

---

## 2. ⚠️ 现有工程必须先修的 4 件事

直接 `docker compose up` 起不来，原因如下，部署前务必处理：

1. **根目录 `Dockerfile` 是 Elasticsearch+IK 分词的镜像，不是 Python 应用镜像。**
   → 本方案把 IK 那个移到 `elasticsearch/Dockerfile`，应用另写 `Dockerfile.app`（见 §4、§5）。

2. **`docker-compose.yml` 残留旧的 MySQL 配置**（`aiagent-end` 里 `DB_HOST=mysql`、`depends_on: mysql`，且代码根本用 PostgreSQL+psycopg）。
   → 用本方案 §6 的 compose 整体替换。

3. **`requirements.txt` 不完整**：venv 里装了但没记录至少 `aio_pika`、`neo4j`、`python-docx`、`python-pptx`、`openpyxl`、`psycopg`、对象存储客户端、PDF 解析库等。Docker 构建 `pip install -r requirements.txt` 会缺包运行即崩。
   → 按 §8 从可用 venv 重新冻结。

4. **`.env` 写死了默认弱口令和 `localhost` host**（PG/Redis/Mongo 密码 `lyp82nlfxxlE`、`JWT_SECRET_KEY` 还是 dev 值、Neo4j `neo4j123456`、MinIO/RustFS `admin` 等）。容器内 host 也必须是 **compose 服务名**，不能是 localhost。
   → 用 §7 的 `.env.docker` 模板，**逐项改掉口令**。

> 另：`main.py` 的 CORS 目前只允许 `http://localhost:5173`。生产走 nginx 同源（前端和 `/api` 同域名），浏览器不发跨域请求，**通常无需改 CORS**。若前端与 API 不同源，需把生产域名加入 `allow_origins` 并重新构建镜像。

---

## 3. 目录准备

```bash
mkdir -p ~/deploy/knowledge-agent
cd ~/deploy/knowledge-agent

# 拉取代码(用你自己的仓库地址;若无远端仓库,用 git bundle / rsync 上传)
git clone <你的仓库地址> backend
git clone <前端仓库地址> frontend || true   # kh_frondend 若未 git,用 scp/rsync 上传

mkdir -p elasticsearch nginx/ssl
# 把腾讯云下载的证书放 nginx/ssl/: your-domain.com_bundle.crt + your-domain.com.key
```

需要放到 `backend/` 下的新文件：`Dockerfile.app`、`.env.docker`、修正的 `docker-compose.yml`、`elasticsearch/Dockerfile`。

---

## 4. 应用镜像 `backend/Dockerfile.app`

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 系统依赖:psycopg 二进制、PDF/Office 解析、构建 wheel
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq5 curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# Linux 下不需要 run_uvicorn.py(那是 Windows 的 ProactorEventLoop 补丁),直接 uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
```

构建期若 `psycopg` 报缺 `libpq`,改用 `psycopg[binary]`（§8 冻结时确认）。

---

## 5. ES 分词镜像 `backend/elasticsearch/Dockerfile`

把现有根目录 `Dockerfile` 内容移到这里（版本必须与 ES 一致）：

```dockerfile
FROM elasticsearch:8.17.0
RUN elasticsearch-plugin install --batch \
  https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-8.17.0.zip
```

> compose 里 ES 的 `build: ./elasticsearch` 即指向此目录。若嫌拉 IK 慢,可先本地构建推到你自己的镜像仓库再改 image。

---

## 6. 生产 `docker-compose.yml`

放到 `backend/` 下。**替换原有那份**。中间件 host 一律用服务名,内部端口(5432/9200/27017…)不做公网映射或只映射给本机调试。

```yaml
services:
  # ---------------- 后端应用(同时是 MQ 消费者) ----------------
  aiagent-api:
    build:
      context: .
      dockerfile: Dockerfile.app
    image: aiagent-api:latest
    container_name: aiagent-api
    env_file: .env.docker          # 全部指向下方服务名
    depends_on:
      postgres:     { condition: service_healthy }
      mongodb:      { condition: service_healthy }
      elasticsearch:{ condition: service_started }
      milvus:       { condition: service_started }
      neo4j:        { condition: service_healthy }
      rabbitmq:     { condition: service_healthy }
      rustfs:       { condition: service_healthy }
    ports:
      - "127.0.0.1:8000:8000"      # 只绑本机,由 nginx 反代,不公网暴露
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped

  # ---------------- PostgreSQL(含 pgvector) ----------------
  postgres:
    image: pgvector/pgvector:pg17
    container_name: aiagent-postgres
    environment:
      - POSTGRES_USER=${PG_USER:?}
      - POSTGRES_PASSWORD=${PG_PW:?}
      - POSTGRES_DB=${PG_DB:?}
      - TZ=Asia/Shanghai
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${PG_USER:?} -d ${PG_DB:?}"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 20s
    restart: unless-stopped

  # ---------------- MongoDB ----------------
  mongodb:
    image: mongo:8.0
    container_name: aiagent-mongodb
    environment:
      - MONGO_INITDB_ROOT_USERNAME=${MONGO_USER:?}
      - MONGO_INITDB_ROOT_PASSWORD=${MONGO_PW:?}
      - TZ=Asia/Shanghai
    volumes:
      - mongodb_data:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "-u", "${MONGO_USER:?}", "-p", "${MONGO_PW:?}",
             "--authenticationDatabase", "admin", "--quiet", "--eval", "db.adminCommand('ping').ok"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s
    restart: unless-stopped

  # ---------------- Elasticsearch(+IK) ----------------
  elasticsearch:
    build: ./elasticsearch
    container_name: aiagent-elasticsearch
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=true
      - ELASTIC_PASSWORD=${ES_PASSWORD:?}
      - ingest.geoip.downloader.enabled=false
      - ES_JAVA_OPTS=-Xms1g -Xmx1g
      - cluster.name=aiagent-es
      - node.name=es-node-1
    ulimits:
      memlock: { soft: -1, hard: -1 }
    volumes:
      - es_data:/usr/share/elasticsearch/data
    # 不映射 9200 到公网;如需本机排错:ports: ["127.0.0.1:9200:9200"]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf -u elastic:${ES_PASSWORD:?} http://localhost:9200/_cluster/health || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 10
      start_period: 40s
    restart: unless-stopped

  # ---------------- Milvus(依赖 etcd + minio) ----------------
  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    container_name: aiagent-etcd
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
      - ETCD_SNAPSHOT_COUNT=50000
    volumes:
      - etcd_data:/etcd
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    restart: unless-stopped

  minio:
    image: quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z
    container_name: aiagent-minio
    environment:
      - MINIO_ROOT_USER=${MINIO_USER:?}
      - MINIO_ROOT_PASSWORD=${MINIO_PW:?}
    volumes:
      - minio_data:/minio_data
    command: server /minio_data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  milvus:
    image: milvusdb/milvus:v2.4.0
    container_name: aiagent-milvus
    command: ["milvus", "run", "standalone"]
    environment:
      - ETCD_ENDPOINTS=etcd:2379
      - MINIO_ADDRESS=minio:9000
    volumes:
      - milvus_data:/var/lib/milvus
    depends_on:
      - etcd
      - minio
    restart: unless-stopped

  # ---------------- Neo4j ----------------
  neo4j:
    image: neo4j:5.26.0
    container_name: aiagent-neo4j
    environment:
      - NEO4J_AUTH=${NEO4J_USER:?}/${NEO4J_PW:?}
      - NEO4J_server_memory_heap_initial__size=1g
      - NEO4J_server_memory_heap_max__size=1g
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u ${NEO4J_USER:?} -p ${NEO4J_PW:?} 'RETURN 1' || exit 1"]
      interval: 10s
      timeout: 10s
      retries: 10
      start_period: 30s
    restart: unless-stopped

  # ---------------- RabbitMQ ----------------
  rabbitmq:
    image: rabbitmq:4-management
    container_name: aiagent-rabbitmq
    environment:
      - RABBITMQ_DEFAULT_USER=${RABBITMQ_USER:?}
      - RABBITMQ_DEFAULT_PASS=${RABBITMQ_PW:?}
      - RABBITMQ_DEFAULT_VHOST=${RABBITMQ_VHOST:?}
      - TZ=Asia/Shanghai
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
    restart: unless-stopped

  # ---------------- RustFS(S3 兼容对象存储) ----------------
  rustfs:
    image: rustfs/rustfs:latest
    container_name: aiagent-rustfs
    environment:
      - RUSTFS_ACCESS_KEY=${RUSTFS_AK:?}
      - RUSTFS_SECRET_KEY=${RUSTFS_SK:?}
    volumes:
      - rustfs_data:/data
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:9000/health"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 10s
    restart: unless-stopped

  # ---------------- 前端静态 + Nginx(HTTPS/反代/SSE) ----------------
  web:
    image: nginx:1.27-alpine
    container_name: aiagent-web
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ../frontend/dist:/usr/share/nginx/html:ro
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - aiagent-api
    restart: unless-stopped

volumes:
  postgres_data:
  mongodb_data:
  es_data:
  etcd_data:
  minio_data:
  milvus_data:
  neo4j_data:
  rabbitmq_data:
  rustfs_data:
```

> 说明：原 compose 里的 `mysql`、`redis`、`redisinsight`、`pgadmin`、`mongo-express`、`kibana` **代码没用到或只是本机 GUI**。生产一律不上；确需排错再单独临时起，且绝不公网暴露管理界面。

---

## 7. 环境变量 `backend/.env.docker`

给 compose 的 `${VAR:?}` 用的"基础设施口令"，以及喂给容器的 `Settings` 字段。pydantic-settings 直接读这个文件里的 **大写变量名**（与 `core/config.py` 一一对应）。

```dotenv
# ===== 供 docker-compose 服务定义插值(必须非空,否则 compose 报错) =====
PG_USER=kh_app
PG_PW=<强口令>
PG_DB=aiagent
MONGO_USER=root
MONGO_PW=<强口令>
ES_PASSWORD=<强口令>
MINIO_USER=<改>
MINIO_PW=<强口令,≥8>
NEO4J_USER=neo4j
NEO4J_PW=<强口令>
RABBITMQ_USER=kh
RABBITMQ_PW=<强口令>
RABBITMQ_VHOST=aiagent
RUSTFS_AK=<改>
RUSTFS_SK=<强口令,≥8>

# ===== 供后端 Settings(core/config.py 读取,host 用服务名) =====
# QWEN / 嵌入 / 重排
QWEN_API_KEY=<你的 key>
QWEN_BASE_URL=<...>
QWEN_MODEL_NAME=<...>
EMBEDDINGS_MODEL_NAME=<...>
RERANK_MODEL_NAME=<...>
RERANK_URL=<...>

# PostgreSQL
POSTGRES_USER=${PG_USER}
POSTGRES_PASSWORD=${PG_PW}
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=${PG_DB}

# MongoDB
MONGO_URI=mongodb://${MONGO_USER}:${MONGO_PW}@mongodb:27017/?authSource=admin
DB_NAME=aiagent

# RustFS(容器内走服务名 9000)
RUSTFS_ENDPOINT=http://rustfs:9000
RUSTFS_ACCESS_KEY=${RUSTFS_AK}
RUSTFS_SECRET_KEY=${RUSTFS_SK}
RUSTFS_BUCKET=aiagent
PRESIGNED_EXPIRE=3600

# RabbitMQ(注意 vhost 需与 RABBITMQ_DEFAULT_VHOST 一致)
RABBITMQ_URL=amqp://${RABBITMQ_USER}:${RABBITMQ_PW}@rabbitmq:5672/${RABBITMQ_VHOST}
QUEUE_INDEX=INDEX
QUEUE_RAG=BY_DOC_IDS
QUEUE_KG=BUILD_BY_DOC_IDS

# Elasticsearch
INDEX_NAME=knowledge-es
ES_HOST=http://elasticsearch:9200
ES_BASIC_AUTH=${ES_PASSWORD}

# Milvus
COLLECTION_NAME=<与开发一致>
DIMENSIONS=<嵌入模型维度,如 1536/1024>
MILVUS_URL=http://milvus:19530
MILVUS_TOKEN=<如有,否则留占位>

# Neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=${NEO4J_USER}
NEO4J_PASSWORD=${NEO4J_PW}
MAX_CONN_POOL_SIZE=50

# JWT —— 生产必须换新随机值
JWT_SECRET_KEY=<openssl rand -hex 32 生成>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
JWT_REFRESH_EXPIRE_MINUTES=10080

# 联网兜底
BOCHAAI_KEY=<你的 key>
WEB_SEARCH_MIN_SCORE=0.3
WEB_SEARCH_COUNT=5
```

> `DIMENSIONS`、`COLLECTION_NAME`、`MILVUS_TOKEN` 必须与你现在开发环境用的嵌入模型保持一致，否则向量维度对不上写入即失败。`ES_BASIC_AUTH` 是 elastic 用户的密码（代码里写死用户名 `elastic`）。

生成 JWT 密钥：`openssl rand -hex 32`。

`.env` / `.env.docker` 含密钥，**已在 `.gitignore` 内，绝不提交**。

---

## 8. 重新生成 `requirements.txt`（关键）

在你**当前能跑起来的 venv**（Windows 开发机）里冻结，保证镜像构建不缺包：

```powershell
# 开发机 PowerShell,项目根目录
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip freeze > requirements.clean.txt
```

打开 `requirements.clean.txt` 删掉本地噪音后,确认**至少**包含以下代码真正 import 但旧清单缺的包（版本号以你 venv 为准）：

```
psycopg[binary]        # PostgreSQL 异步驱动(代码用 postgresql+psycopg)
aio-pika               # RabbitMQ 异步客户端
neo4j                  # Neo4j driver
aiobotocore            # RustFS/S3 客户端(若 clients/rustfs 用的是它)
python-docx            # docx 解析(from docx)
python-pptx            # pptx 解析(from pptx)
openpyxl               # xlsx 解析
PyMuPDF 或 pdfplumber  # pdf 解析(utils/parsers)
```

用整理好的文件覆盖 `requirements.txt` 上传到服务器。若嫌 `pip freeze` 太杂,可保留现有 `requirements.txt` 再手动 append 上面缺的包。**先在一台机器上 `docker build` 验证能起、能 `/user/login`,再上线。**

---

## 9. 前端构建

本机或 CI 里构建（Node 22）：

```bash
cd frontend
npm ci
npm run build      # 产物在 frontend/dist,生产用 VITE_API_BASE_URL=/api(已在 .env.production)
```

确保 `frontend/dist` 出现在服务器 `~/deploy/knowledge-agent/frontend/dist`（compose 里 `web` 挂载的是 `../frontend/dist`）。

```bash
# 上传方式示例(scp/rsync)
rsync -avz --delete dist/ user@<server-ip>:~/deploy/knowledge-agent/frontend/dist/
```

---

## 10. Nginx 配置 `backend/nginx/nginx.conf`

```nginx
server {
    listen 80;
    server_name kh.your-domain.com;
    # HTTP → HTTPS
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl;
    http2 on;
    server_name kh.your-domain.com;

    ssl_certificate     /etc/nginx/ssl/your-domain.com_bundle.crt;
    ssl_certificate_key /etc/nginx/ssl/your-domain.com.key;
    ssl_protocols       TLSv1.2 TLSv1.3;

    client_max_body_size 100m;      # 上传文档体积,按需要放大

    # 前端 SPA
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 后端 API:剥掉 /api 前缀转发到 aiagent-api:8000
    # 结尾的 "/" 会把 /api/xxx 转成 /xxx,等价于 vite dev 的 rewrite
    location /api/ {
        proxy_pass http://aiagent-api:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 流式问答(/ai/invoke_stream)必须关缓冲、拉长超时、不中转
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        add_header X-Accel-Buffering no;
        chunked_transfer_encoding on;
    }
}
```

> 证书二选一：① 直接下腾讯云 SSL 证书放 `nginx/ssl/`；② 或改用 certbot 签 Let's Encrypt（需另起 certbot 容器/任务，`web` 挂 acme 目录）。上面用的是方式①。

---

## 11. 部署步骤（服务器上按序执行）

```bash
cd ~/deploy/knowledge-agent/backend

# 1) 放好 Dockerfile.app / elasticsearch/Dockerfile / .env.docker / docker-compose.yml / requirements.txt
#    放好 nginx/nginx.conf 与 nginx/ssl/*

# 2) ES 需要的内核参数(单次即可,否则 ES 起不来)
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf

# 3) 构建并后台拉起
docker compose up -d --build

# 4) 观察启动(等中间件健康后再看 api)
docker compose ps
docker compose logs -f aiagent-api
```

看到日志里 `✅ ES 连接成功`、`RabbitMQ 连接成功` 且无 traceback 即算起来。

---

## 12. 首次初始化 / 引导数据

代码里表/索引**不是**启动自动建的（lifespan 只 ping/连不建 schema）。按下面顺序做一次：

```bash
API=http://127.0.0.1:8000   # 服务器上本机访问;或经 nginx https://域名/api

# 1) PG 建表(走应用 create_all;注意 create_all 不会给"已存在表"加新列)
curl -X POST $API/pg/create_table
#    若从旧库迁移:kh_document 的 parse_status 等列需手动 ALTER,参考 scripts/migrate_add_parse_status.sql

# 2) ES 索引 / Milvus 集合 / Neo4j:调用各自 create 路由
#    实际路径以运行实例为准,先查:
curl -s $API/openapi.json | python -c "import sys,json;[print(p) for p in json.load(sys.stdin)['paths'] if 'create' in p or 'init' in p]"
#    然后按需 curl 创建 ES 索引、Milvus collection(维度必须等于 EMBEDDINGS_MODEL_NAME 的维度)

# 3) 建初始管理员 + 角色/权限种子
#    角色种子在 api/permission.py SEED_PERMISSIONS;用户注册首账号后用管理接口授予 ROLE_ADMIN

# 4) 校验基础设施连通性
python scripts/check_infra_state.py
```

> ⚠️ 生产注意：`/pg/create_table`、`/pg/drop_table`、`/es/*`、`/milvus/*` 这类"建/删表"高危接口应在上线后**关闭路由或加管理员鉴权**，否则任何公网可达的调用都可能破坏 schema。当前 `main.py` 直接 `include_router`,请评估。

---

## 13. 上线验证清单

- [ ] 浏览器 `https://kh.your-domain.com` 打开登录页（HTTP 自动跳 HTTPS，证书有效）。
- [ ] 注册/登录成功；F12 Network 看 `/api/user/login` 返回 token，刷新 token 正常。
- [ ] 文档列表能加载（`/api/pg/check_all`），上传人 / 解析状态两列显示。
- [ ] 上传一个 PDF/DOCX：解析流程走完，`解析状态` 从"解析中"变"解析完成"（验证 MQ 消费者 + PG/Mongo/ES/Milvus/Neo4j 全链路）。
- [ ] 发布/提交审核 → 审核通过 → 文档进 ES/RAG/KG。
- [ ] AI 问答：知识库命中带 `[n]` 引用；命中不到且开"联网兜底"时出现"网页"来源卡。
- [ ] 问答**流式**：正文逐字打字机输出（若一坨蹦出，查 §16 SSE）。
- [ ] 引用卡"下载文件"能下载（验证 `/api/restfs/download` 鉴权 + 可见性）。
- [ ] 非公开文档用另一账号看不到、下载 403。
- [ ] `docker compose ps` 所有服务 `Up (healthy)`。

---

## 14. 运维

```bash
# 更新发版(改了代码/配置)
cd ~/deploy/knowledge-agent/backend
git pull                       # 或重新 rsync 代码
docker compose build aiagent-api
docker compose up -d aiagent-api web

# 日志
docker compose logs -f --tail=200 aiagent-api
docker compose logs -f elasticsearch milvus

# 重启单个服务
docker compose restart aiagent-api

# 全停(数据卷保留)
docker compose down

# 备份数据卷(重要!换口令/迁移前必备份)
docker run --rm -v knowledge-agent_postgres_data:/data -v $PWD:/backup ubuntu \
  tar czf /backup/pg-$(date +%F).tar.gz -C /data .
# Mongo 用 mongodump;Milvus/ES/Neo4j/RustFS 各自快照或对卷打包
```

> 数据都在 named volume（`knowledge-agent_*`）里，别 `docker compose down -v`（会删数据）。

---

## 15. 安全加固 Checklist

- [ ] `.env.docker` 所有 `<强口令>` 全部替换，**不留 `lyp82nlfxxlE` / `admin` / `neo4j123456` / `minioadmin`**。
- [ ] `JWT_SECRET_KEY` 换成 `openssl rand -hex 32` 的新值（默认 dev 值必须弃用）。
- [ ] 安全组仅开 22(限源IP)/80/443；`aiagent-api` 端口只绑 `127.0.0.1`，中间件不映射公网。
- [ ] 生产关闭/加鉴权高危破坏性接口（create_table/drop_table、各中间件裸路由）。
- [ ] Kibana / pgAdmin / mongo-express / RedisInsight / RabbitMQ 管理台不公网暴露。
- [ ] QWEN/BOCHA key 定期轮换；若泄漏立即在对应平台吊销。
- [ ] Nginx 开 HTTPS only（HTTP 301），证书到期前监控（腾讯云证书 1 年）。
- [ ] `.env*`、`nginx/ssl/*`、`logs/` 加入 `.gitignore`，绝不入库。

---

## 16. 常见问题

**Q: 前端问答没有打字机效果，全文一次蹦出。**
先分清是渲染还是链路：
- 前端：已把回答消息用 `reactive()` 放进 `ref` 数组（局部对象绕过代理会导致不逐帧渲染）——确认服务器上的前端是最新 `dist`。
- 链路：F12 Network 看 `invoke_stream` 是否分帧到达。若被整体缓冲，就是 nginx `proxy_buffering off` 没生效——确认 `web` 容器加载的是 §10 的 conf 且已 reload。
- 后端：`/api/ai/invoke_stream` 路由存在吗？`docker compose logs aiagent-api` 里有没有该请求。

**Q: `docker compose up` 后 `aiagent-api` 反复重启，日志 `ModuleNotFoundError: aio_pika/neo4j/docx`。**
`requirements.txt` 没补全（§8）。补齐后 `docker compose build --no-cache aiagent-api`。

**Q: 连 ES 报 `connection error` / 启动失败。**
- IK 插件版本必须等于 ES 版本（都 8.17.0），否则 ES 起不来。
- `vm.max_map_count` 没设（§11 步骤2）。
- `ES_BASIC_AUTH` 与 `ELASTIC_PASSWORD` 不一致。

**Q: Milvus 写入报维度不符。**
`DIMENSIONS` 与实际嵌入模型输出维度不一致；集合是旧的，需重建集合或对齐维度。

**Q: psycopg 在 Linux 报 event loop 问题？**
不会。`main.py` 里的 `WindowsSelectorEventLoopPolicy` 只在 `sys.platform=='win32'` 生效；Linux 用默认 loop，直接 `uvicorn main:app` 即可，**不要用** `scripts/run_uvicorn.py`（那是 Windows 补丁）。

**Q: 大文件上传 413。**
调大 nginx `client_max_body_size`；如经对象存储直传另议。

**Q: 改了 `.env.docker` 不生效。**
`docker compose up -d` 对已存在容器不重注入 env，需 `docker compose up -d --force-recreate aiagent-api`。

---

## 附:需要最终确认的点

1. `docker build` + 起一个 `aiagent-api` 跑通 `/user/login` 后,再上生产 compose 全量拉起——先小步验证,别一次 up 全部再排错。
2. §12 里 ES 索引 / Milvus 集合 / 初始管理员的具体创建接口,用运行实例的 `openapi.json` 核对(代码里 create 路由分散在 `api/es.py`、`api/milvus.py`,以实际为准)。
3. RustFS 若你想换成腾讯云 COS,改 `core/config.py` 的 endpoint/ak/sk 即可(S3 兼容),`rustfs` 服务可去掉。
