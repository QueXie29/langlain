# 面向初级 AI / Python 岗位的 RAG 升级：证据与设计建议

核对日期：2026-11-11。本文依据当前仓库代码与官方文档，不代表应用已实现下列建议，也不代表完成后保证获得录用。本轮仅检查代码与资料，未运行真实模型调用或系统性能评测。

## 1. 当前能力：已有的部分不应重复建设

- [retrieval.py](../backend/knowledge/services/retrieval.py) 已按登录用户、文档状态、向量模型和维度过滤，做余弦距离召回，并调用重排序；默认候选 20 条、最终 5 条。
- [rag.py](../backend/knowledge/services/rag.py) 已使用 LangChain Prompt / ChatModel 链，约束资料内回答，检查引用编号，返回实际引用的来源。编号合法不能证明每个事实受到原文支持。
- [ingestion.py](../backend/knowledge/services/ingestion.py) 已分批向量化，并在事务中替换片段；重建成功前不会先删除旧片段。
- [parsers.py](../backend/knowledge/services/parsers.py) 将 PDF 多页合成字符串，DOCX 表格放到段落之后；缺少可用于精确溯源的页码、章节、表格结构等元数据。
- [README](../README.md) 明确：同步上传索引、单轮问答、页面内临时聊天记录、未集成 OCR，Compose 仅启动数据库。
- [qwen.py](../backend/knowledge/services/qwen.py) 的聊天适配器目前只处理纯文本 system/human/ai 消息，没有工具绑定、工具结果消息或流式生成实现。依赖仅包含 `langchain-core` 和 `langchain-text-splitters`，没有完整 `langchain` / `langgraph`。

以上是静态代码核对，不等同于真实服务可用性或效果验证。特别是默认服务地址属于配置的中转服务，不能根据另一家服务的官方文档推断其模型名、工具调用或流式能力。

## 2. 首先补效果评测，而不是先增加框架

**官方依据：** LangChain 的 RAG 评测教程采用问题与参考答案数据集，分别评估正确性、相关性、检索相关性，以及回答是否受到检索资料支持；评测模式不限定应用必须使用同一框架。[LangChain：Evaluate a RAG application](https://docs.langchain.com/langsmith/evaluate-rag-tutorial)

**本项目设计建议：** 从一个真实场景起步，例如校内办事指南或公开的软件产品手册。先人工审核 60～100 道题作为小型起始集合，数量是项目建议，不是岗位门槛。覆盖事实查找、同义改写、编号和专有名词、跨段落问题、资料外问题，以及权限隔离。分开保留调参集和最终测试集。

每条保存问题、参考答案、是否应拒答、证据文档版本、页码/章节与原文范围。比较切块方法时不要只把旧 chunk ID 当真值，否则切块变化会使真值失效。

建议输出四组指标及逐题结果：

| 层次 | 指标 | 计算边界 |
| --- | --- | --- |
| 初步召回 | Hit@K、Recall@K | 在可回答问题上计算；Recall 需要尽量完整的相关证据标注，Hit 只表示至少找到一项证据 |
| 排序 | MRR@K | 第一个相关结果的倒数排名，找不到计 0；不能反映多证据是否齐全 |
| 回答 | 参考答案正确性、逐事实证据支持率、应拒答问题的正确拒答率 | 正确拒答率分母是应拒答问题数；另看可回答问题的误拒答率 |
| 工程 | 各阶段耗时、端到端 P50/P95、错误率、Token / 请求成本 | 固定语料、模型、配置、并发条件，保存原始结果 |

Ragas 提供上下文召回、精度、faithfulness 等指标；其中部分指标会调用裁判模型。它也区分基于文本/事实的召回和基于上下文 ID 的召回，不能混成同一个指标。先做可核对的标注与人工抽查，再考虑接入评测框架。[Ragas：指标列表](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/)、[Ragas：Context Recall](https://github.com/vibrantlabsai/ragas/blob/main/docs/concepts/metrics/available_metrics/context_recall.md)

## 3. 检索升级：保留现有重排序，增加一条词面召回

**官方依据：** pgvector 支持与 PostgreSQL 全文检索结合，并给出 RRF 融合及 cross-encoder 示例。因此当前项目可以沿用 PostgreSQL，不必为了混合检索再引入独立搜索集群。[pgvector：Hybrid Search](https://github.com/pgvector/pgvector#hybrid-search)、[pgvector-python：RRF 示例](https://github.com/pgvector/pgvector-python/blob/master/examples/hybrid_search/rrf.py)

**本项目设计建议：** `向量召回 + 关键词召回 → 按 chunk ID 去重 → RRF → 现有 rerank → 上下文预算控制`。所有分支都沿用当前 owner / ready / 模型版本过滤，不能只在最终答案处做权限处理。记录每条候选来自哪些分支，才能定位漏召回。

需要澄清两个细节：

- PostgreSQL 原生 `ts_rank` / `ts_rank_cd` 是全文检索排序函数，不应在简历中直接称为 BM25。[PostgreSQL 16：Ranking Search Results](https://www.postgresql.org/docs/16/textsearch-controls.html#TEXTSEARCH-RANKING)
- 官方 RRF 示例使用 `english`；中文语料需先选好并验证分词路径。PostgreSQL 的 parser 和 dictionary 可配置，但不能由示例推断原样适合中文。小规模起步可在用户隔离的片段上使用明确的中文分词与 BM25 实现，再用相同评测集决定是否迁移索引方案。[PostgreSQL 16：Parsers](https://www.postgresql.org/docs/16/textsearch-parsers.html)

重排序只能重排已经召回的候选，不能找回候选集外的证据；这也是先分别评测召回和排序的原因。两阶段检索的职责可参考 [Sentence Transformers：Retrieve & Re-Rank](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html)。

## 4. 文档入库升级：异步任务与可恢复处理

**官方依据：** Celery 原生支持 Django，文档特别说明任务应在数据库事务提交后发出；`delay_on_commit()` 是该模式的快捷方法，而且不会直接返回 task ID。[Celery：First steps with Django](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html)

**本项目设计建议：** 用 Celery + Redis 承接现有 `ingest_document`，上传返回 202 和业务任务 ID，状态保存在数据库，页面轮询。增加 queued / parsing / embedding / ready / failed 状态、处理进度、有限重试和人工重试。Redis 在这里承担 broker，不要仅为简历关键词加入无实际用途的缓存。

当前开发机为 Windows。Celery 官方 FAQ 明确不支持 Windows，因此建议将 worker 放在 Linux 容器或 WSL2 Linux 环境中，与后端约定一致的数据库连接和上传文件路径；Windows 本地后端继续使用现有方式也可以，但 worker 必须能读取同一份源文件。[Celery FAQ：Does Celery support Windows?](https://docs.celeryq.dev/en/stable/faq.html#does-celery-support-windows)

按用户与文件哈希识别重复上传，按文档版本与索引配置计算任务身份。Worker 重启或同一任务重复投递后，应避免重复片段、旧任务覆盖新版本和重复费用。数据库唯一约束、执行状态检查与原子切换索引需要配合；不能把“配置 retry”写成“实现 exactly once”。Celery 官方说明任务应尽可能幂等，ack / retry 语义不能替代业务幂等。[Celery：Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html)

## 5. Agent 升级：完成一个可测试的工具调用闭环

**官方依据：** LangChain tools 支持参数 schema 和运行时上下文，也提供工具调用次数、模型调用次数限制，以及工具错误处理机制。[LangChain：Tools](https://docs.langchain.com/oss/python/langchain/tools)、[LangChain：Prebuilt middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)

**本项目设计建议：** 选一个知识库关联任务，例如“查报销规则，再按输入金额计算可报销额度”。先只开放知识库搜索与受限计算器两个工具；用户 ID 由后端身份上下文传入，不允许模型自由指定。计算器接受数值和限定运算，不执行任意 Python 字符串。

先验证当前模型服务支持的 tool calling 请求与响应协议，并补 `bind_tools`、`tool_calls`、工具结果消息适配；若改为模型输出结构化路由、后端按白名单执行，则如实称为受控工作流，不能把现有固定 RAG 链称为自主 Agent。

对每次请求限制工具调用数、总超时和 Token 预算，记录工具名称、参数、耗时和结果摘要。用“需要检索”“需要计算”“参数不合法”“工具失败”“超限终止”和“跨用户数据请求”等样例验收。不要直接引入任意 shell、任意 SQL 或外部写操作，避免超出这个演示任务的需要。

## 6. 工程交付：把已有测试变成别人能复现的证据

**官方依据：** Django 部署检查清单包括生产密钥、关闭 DEBUG、ALLOWED_HOSTS、HTTPS，以及数据库和用户上传文件配置；可以运行 `manage.py check --deploy` 辅助检查。[Django 5.2：Deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)

**本项目设计建议：** 提供 Linux 环境启动说明与前后端/worker 完整部署配置；CI 跑现有后端测试、真实 PostgreSQL/pgvector 集成测试和前端构建。当前 SQLite 单测会跳过真实向量检索，不能将其作为 pgvector 正确性的全部证据。

记录贯穿 API、任务与模型请求的 request ID，以及 parse / embed / retrieve / rerank / generate 各阶段耗时。至少写一份真实故障复盘，包含复现步骤、根因、修复与回归验证。

建议展示的最终材料是：可复现 README、架构图、API 示例、评测集与对比报告、部署演示、两个真实排错案例、清楚的 Git 提交。实际效果数字应来自保存的评测结果，不使用预设提升比例。学历、毕业时间和编程基础等岗位条件需要独立核对，不能由项目功能数量替代。
