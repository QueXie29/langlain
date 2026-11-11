# 知屿：LangChain + 千问 + Django + Vue 3

本目录 `langlain/` 是 LangChain 版本。三个模型已经接入实际流程：1

| 用途 | 模型 | 接入方式 |
| --- | --- | --- |
| 大语言模型 | `qwen3.8-flash` | LangChain `BaseChatModel`，使用示例中的 DashScope 多模态生成接口 |
| 向量模型 | `qwen3.7-text-embedding-flash` | LangChain `Embeddings` 接口 + DashScope，默认 1024 维 |
| 重排序模型 | `qwen3.7-text-rerank` | DashScope 原生文本排序接口 |

上传文件保存在本机 `backend/media/`，用户、文档记录及向量保存在 Docker 中的 PostgreSQL + pgvector；文档文本、问题和检索片段会发送至配置的千问服务。前端不读取 API Key。

问答顺序：问题向量化 → 按用户和当前向量模型检索最多 20 个片段 → 重排序取前 5 个 → 生成带引用的答案。没有合格片段时直接拒答；重排序失败会返回明确错误。

## 目录与运行方式

```text
langlain/
  docker-compose.yml      仅启动 PostgreSQL + pgvector
  .env                    本机配置与 API Key
  .env.example            不含 Key 的配置模板
  backend/                本地 Django 后端、迁移和测试
    .venv/                本地 Python 依赖环境
    media/                用户上传的源文件（上传后生成）
  frontend/               本地 Vue + Vite 前端
    package-lock.json     前端依赖锁文件
    node_modules/         本地前端依赖
  docs/                   架构说明
```

已移除前后端容器部署文件、无对应 `package.json` 的根层空锁文件及旧缓存。`.venv`、`node_modules` 用于本地运行，前端锁文件用于 `npm ci`，均需保留。`__pycache__` 和 `frontend/dist` 是可再生成的文件，不影响源码运行。

## Windows 运行步骤：数据库 Docker，前后端本地

准备 Python 3.11+、Node.js 22.12+ 和 Docker Desktop（Linux containers）。先打开 Docker Desktop，等待引擎启动。以下路径对应当前工作区；换电脑后修改路径即可。

### 1. 检查配置

```powershell
cd 'D:\AI-learning\rag历届项目\RAG-Vue-\langlain'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

本次已将你提供的 Key 写入本机 `.env`。复制项目到其他位置时，需自行填写 `DASHSCOPE_API_KEY`。`.env` 已在 `.gitignore` 中排除，模板不包含 Key。

```dotenv
DASHSCOPE_API_KEY=填入你的API_Key
DASHSCOPE_BASE_URL=https://maas.qianwenaiapi.com/api/v1
QWEN_CHAT_MODEL=qwen3.8-flash
QWEN_EMBED_MODEL=qwen3.7-text-embedding-flash
QWEN_RERANK_MODEL=qwen3.7-text-rerank
EMBEDDING_DIMENSION=1024
POSTGRES_HOST=localhost
POSTGRES_PORT=5434
POSTGRES_HOST_PORT=5434
```

接口地址与你提供的三个示例一致。大语言模型使用 `MultiModalConversation` 对应的 HTTP 接口，向量和重排序也使用 DashScope 原生接口；项目通过 HTTPX 发送请求，无需安装 DashScope SDK。当前知识库传入文本消息，不新增图片上传功能。如需切换地域或业务空间，修改 `DASHSCOPE_BASE_URL`，Key 也必须属于对应服务。不要在 Base URL 后手动追加模型的具体调用路径。

### 2. 只启动数据库

```powershell
cd 'D:\AI-learning\rag历届项目\RAG-Vue-\langlain'
docker compose up -d --wait db
docker compose ps
```

数据库名默认 `rag_knowledge_langchain`，账户默认 `rag_user`，密码见 `.env`，本机连接端口 **5434**，容器内部端口 5432。数据保存在命名卷中。`docker-compose.yml` 仅包含 `db` 服务；前端和后端均在本地启动。

### 3. 启动本地后端（终端一）

无需激活虚拟环境，直接使用它的 Python，避免 PowerShell 激活脚本策略问题：

```powershell
cd 'D:\AI-learning\rag历届项目\RAG-Vue-\langlain\backend'
if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py check_qwen
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

`check_qwen` 使用固定测试文本检查文档向量、查询向量、重排序及聊天，验证实际返回的向量维度；不读取用户文档，不连接数据库，会产生少量 API 用量。所有检查成功后再上传资料。如果默认 pip 镜像无法连接，可将安装命令改为 `python -m pip install -r requirements.txt --index-url https://pypi.org/simple`（仍使用上述虚拟环境的 Python）。

### 4. 启动本地前端（终端二）

```powershell
cd 'D:\AI-learning\rag历届项目\RAG-Vue-\langlain\frontend'
npm.cmd ci
npm.cmd run dev
```

浏览器访问 **http://localhost:5174**，注册账号后上传文档。Vite 将 `/api` 请求转发到本地后端 **http://127.0.0.1:8001**。

### 5. 从旧 Ollama 版本切换时

旧向量与千问向量即使同为 1024 维，也不能混用。新片段会记录 `embedding_model` 和 `embedding_dimension`；检索只使用匹配当前配置的片段，未标记的旧片段不会参与回答。

如果之前已上传过文档，在 `backend/` 下执行一次（保留用户、文档记录与源文件，替换向量；会产生 API 用量）：

```powershell
.\.venv\Scripts\python.exe manage.py reindex_documents
# 或只重建某位用户：
.\.venv\Scripts\python.exe manage.py reindex_documents --user-id 1
```

源文件必须仍在 `backend/media/` 中。若旧版后端在 Docker 中运行，源文件可能在 `media_data` 卷里，需要先将其复制到本机 `backend/media/` 后再重建。失败文档会显示错误，可修复后重新运行。重建期间先暂停上传和问答。

本次保持数据库迁移中的 1024 维，因此不需要改表。以后改用其他维度时，必须新建迁移并重新索引，不能只改 `.env`。

### 停止与再次启动

前后端终端分别按 `Ctrl+C`；数据库执行 `docker compose stop db`。下次数据库执行 `docker compose up -d --wait db`，前后端重新执行各自的启动命令即可。无需重新安装依赖或重建向量。不要使用 `docker compose down -v`，它会删除数据库卷。

## 常用配置

前端端口在 `frontend/vite.config.js` 的 `server.port` 配置（5174），后端由 `runserver 127.0.0.1:8001` 指定；修改时同步调整 Vite 的 `/api` 代理地址和 `CORS_ALLOWED_ORIGINS`。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DASHSCOPE_API_KEY` | 空，必须填写 | 后端 API 凭据 |
| `DASHSCOPE_BASE_URL` | `https://maas.qianwenaiapi.com/api/v1` | 三个模型共用的原生 API Base URL |
| `QWEN_TIMEOUT` | 120 | 模型请求超时秒数 |
| `QWEN_TRUST_ENV` | false | 千问请求默认直连；true 时读取代理及 CA 环境变量，证书校验始终开启 |
| `QWEN_MAX_TOKENS` | 700 | 回答输出 Token 上限，关闭思考模式 |
| `EMBEDDING_DIMENSION` | 1024 | 须与数据库字段维度一致 |
| `RAG_RETRIEVAL_K` | 20 | 向量召回候选数量（至少为 `RAG_TOP_K`） |
| `RAG_TOP_K` | 5 | 重排序后送入大模型的片段数 |
| `RAG_MIN_SIMILARITY` | 0.45 | 向量召回最低余弦相似度，需要按新模型实际效果调节 |
| `RAG_CHUNK_SIZE` | 800 | 每块最多字符数 |
| `RAG_CHUNK_OVERLAP` | 120 | 目标重叠字符数 |
| `MAX_UPLOAD_SIZE_MB` | 20 | 文件大小上限 |
| `MAX_EXTRACTED_CHARS` | 1000000 | 单文档提取文本字符上限 |

重排序分数与余弦相似度分别保存在 `sources[].rerank_score` 和 `sources[].similarity`。页面显示排序分；它不是回答正确率，也不用于跨问题比较。

## 常见问题

- **Docker 无法连接引擎**：先启动 Docker Desktop，等待 `docker info` 能返回服务端信息。
- **数据库连接失败**：确认 `docker compose ps` 中 `db` 为 healthy，本地后端使用 `localhost:5434`，不要使用容器服务名 `db`。
- **5434 被占用**：同时修改 `.env` 的 `POSTGRES_HOST_PORT` 和 `POSTGRES_PORT`，再重新启动数据库容器。
- **HTTP 401/403**：核对 Key、服务地址的地域/业务空间以及模型权限和额度。
- **HTTP 404/400**：核对 Base URL、三个模型名称与对应服务的支持情况。
- **连接失败 / TLS EOF**：本机代理可能中断千问的 HTTPS 握手。当前配置 `QWEN_TRUST_ENV=false`，仅让项目的千问请求直连；不会更改系统代理。若网络必须通过代理或需要自定义 CA 环境变量，再设为 `true` 并确认代理能访问该接口。
- **一直拒答**：先确认文档上传成功；旧文档先执行重新索引。再用文档中明确存在的事实提问，必要时调低 `RAG_MIN_SIMILARITY`。
- **修改数据库密码后认证失败**：已有卷仍保存初始化时的数据库密码；仅修改 `.env` 不会修改数据库用户密码。使用原密码连接或在数据库中主动修改，不要通过删除数据卷修复。

## 测试与构建

以下测试使用模拟模型 HTTP 响应和临时 SQLite，不消耗真实 API 额度。SQLite 测试不能替代 PostgreSQL/pgvector 集成验证。

```powershell
cd 'D:\AI-learning\rag历届项目\RAG-Vue-\langlain\backend'
$env:DATABASE_ENGINE='sqlite'
.\.venv\Scripts\python.exe manage.py test knowledge.tests
Remove-Item Env:DATABASE_ENGINE
.\.venv\Scripts\python.exe -m pip check

cd ..\frontend
npm.cmd run build
```

已保留 JWT、用户隔离、PDF/DOCX/TXT/Markdown 解析、失败上传记录与引用校验。扫描 PDF 仍需先 OCR。引用检查不能保证每个事实都正确，请核对展示的原文。

数据库已启动时，也可不设置 `DATABASE_ENGINE`，直接运行 `manage.py test knowledge.tests`。Django 会创建独立测试数据库，并额外验证真实 pgvector 距离计算和数据库过滤。

当前验证：Compose 仅含 `db`，本地前后端与数据库链路、前端构建已通过验证；PostgreSQL 模式下 46 项后端测试通过。千问连接问题已修复：原先请求经过本机 `127.0.0.1:7897` 代理时 TLS 握手失败，改为项目内直连后恢复；同时兼容了向量响应中的 `index` 字段。`manage.py check_qwen` 已真实验证文档向量、查询向量、重排序和聊天全部成功，向量为 1024 维。

技术说明见 [LangChain 改造说明](docs/LANGCHAIN_CHANGES.md)。接口依据：[千问多模态生成](https://help.aliyun.com/zh/model-studio/vision)、[文本向量](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api)、[文本排序](https://help.aliyun.com/zh/model-studio/text-rerank-api)、[LangChain 模型接口](https://docs.langchain.com/oss/python/langchain/models)。
