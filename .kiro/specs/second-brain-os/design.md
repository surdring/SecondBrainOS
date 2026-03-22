# SecondBrainOS 技术设计文档

## 概述

SecondBrainOS 是一个主动的、具备时间感知的"数字外脑"系统，采用分层记忆架构和异步巩固机制，实现无摩擦信息录入、智能记忆管理和时间感知推理。

### 设计目标

- **无摩擦录入**：支持多模态输入（语音、文字、图片），降低记录门槛
- **智能记忆管理**：自动结构化信息，处理记忆冲突，维护用户数字画像
- **时间感知推理**：理解时间概念，支持跨时间维度的复杂查询
- **主动服务**：基于情境和时间主动提供提醒和建议

### 核心特性

- 分层记忆架构（工作记忆、语义记忆、情景记忆）
- 异步巩固任务处理
- GraphRAG 知识图谱构建
- Agentic Memory 自适应记忆层
- 多模态输入处理
- 时间感知查询引擎

## 架构

### 系统边界与职责

SecondBrainOS 的设计遵循“事实源 + 派生物可重建”的核心原则，并明确区分不同入口的职责边界。

#### 边界划分

- **SecondBrainOS Core（权威事实源）**
  - 负责：`raw_events` 落库、异步巩固编排、分层记忆存储、检索与证据组装、擦除权与审计、健康检查。
  - 输出：对外提供稳定 REST API（供 Web App 与可选 OpenClaw Adapter 调用）。
- **Web App（独立应用入口）**
  - 负责：采集输入、展示时间线/档案/证据、发起查询与擦除。
  - 不负责：直接调用 embeddings/LLM 等含密钥能力。
- **OpenClaw（可选控制平面/多渠道入口）**
  - 负责：多渠道接入与消息路由、会话隔离与安全策略、Skills/Tools 编排、运维控制台。
  - 与 Core 的关系：可频繁升级；Core API 契约保持稳定。

### 整体架构

SecondBrainOS 采用微服务架构，核心组件包括：

- **输入层**：Web App、OpenClaw、其它渠道适配器统一调用 SecondBrainOS Core API。
- **Core 层**：FastAPI 提供同步 REST API；异步处理通过 Redis Queue + RQ Worker 执行。
- **存储层**：Postgres（含 pgvector）用于事实源与索引；Redis 用于缓存与队列。
- **外部服务**：embeddings（SiliconFlow）与大模型服务仅由 Core/worker 调用，密钥不下发至前端或 OpenClaw。
- **Episodic Memory（外部引擎）**：通过 HTTP REST API 集成 WeKnora，承担文档解析、分块、索引与混合检索；可选启用 GraphRAG 增强。

### 分层记忆架构

#### 工作记忆（Working Memory）
- **技术实现**：Context Window + Prompt Caching (CAG)
- **存储范围**：最近 1-7 天的对话上下文
- **响应特性**：极速响应，< 1 秒
- **用途**：快速对话交互，临时上下文维护

#### 语义记忆（Semantic/Agentic Memory）
- **技术实现**：Redis + PostgreSQL，基于 Mem0 架构
- **存储内容**：用户核心事实、状态、偏好
- **建议字段（概念模型）**：
  - `user_id`
  - `facts`（稳定事实，如证件号、重要账号信息等）
  - `preferences`（可变偏好，如饮食、工作习惯等）
  - `constraints`（约束/禁忌，如忌口、时间限制等）
  - `version`（档案版本号，用于冲突解决后的版本化）
  - `updated_at`

#### 情景记忆（Episodic Memory）
- **技术实现**：以 WeKnora 作为"检索与理解层"（文档解析/分块/索引/混合检索/可选 GraphRAG 增强）
- **存储内容**：海量日志、历史文档、会议记录、对话归档摘要等
- **职责边界**：
  - WeKnora：文档解析、分块、混合检索、可选 GraphRAG 增强（包括 Neo4j 图谱构建）
  - SBO：检索编排、时间权重重排、证据模型统一、权限隔离与审计
- **查询能力**：支持文档级/片段级检索，必要时通过 WeKnora GraphRAG profile 启用增强以支持更强的关系推理
- **集成原则**：SBO Core 不重复实现文档解析/分块/混合检索功能，所有 Episodic Memory 能力通过 WeKnora 提供

##### 【修改】Cross-Encoder 重排与降级策略（适用于 deep 或需要高质量答案的场景）

**独立性要求**：
- 重排 provider 不得成为 `/query` 的强依赖；不得因重排超时导致整体超时
- 重排必须有独立超时与并发控制

**失败降级**：
- 重排失败时必须降级回 fusion 排序，并在响应或审计日志中记录降级原因（如 timeout/5xx）

**混合评分**：
- rerank 分数不应完全覆盖原始相关性，推荐加权融合

**符号查询保护**：
- 对高 BM25/lexical 命中设置保底阈值，避免 cross-encoder 错杀

### 异步巩固架构

- 用户输入到达 FastAPI 后，立即写入 `raw_events` 并入队巩固任务，然后返回“快速确认”。
- Redis Queue 将任务分发给 RQ Worker。
- Worker 按作业拆分执行：结构化抽取、档案更新与版本化、embeddings 生成（失败不阻塞）；可选启用图谱增强相关作业（阶段 2 或启用 WeKnora GraphRAG profile 时）。
- Worker 也可执行 Episodic 写入相关作业：将文档/URL/对话摘要归档为 Knowledge 写入 WeKnora，并持久化导入作业状态以便查询与审计。

## 核心工作流与关键策略

### 写入工作流（Capture -> Consolidation）

目标：确保用户侧“快确认”体验不被巩固阻塞，同时保证所有输入可回放与可审计。

1. **入口接收**：Web App/OpenClaw 将输入统一提交到 `POST /ingest` 或 `POST /chat`。
2. **事实源落库（必须先落 raw）**：写入 `raw_events`，作为唯一事实源（append-only，支持软删字段）。
3. **快速确认**：在不等待抽取/embedding/图谱写入完成的情况下返回确认（与需求性能指标对齐）。
4. **异步巩固入队**：将 `consolidate_event(event_id)` 等作业入队，由 worker 在后台完成。
5. **派生物更新**：抽取写入 `extractions`；档案 upsert + history；embedding 写入向量索引；Neo4j 子图 MERGE。

### 多模态输入设计（语音 / 图片 / OCR）

多模态能力的设计原则是：**输入先落 raw，解析与抽取全部异步化**，避免影响“快确认”。

- **语音输入**：
  - 客户端可上传音频或先本地转写后提交文本；无论哪种方式，Core 都以 `raw_events.content` 持久化原始输入与必要元数据。
  - 若由 Core/worker 执行转写：转写任务必须进入异步队列；`POST /ingest`/`POST /chat` 不等待转写完成。
- **图片输入（upload）**：
  - `POST /upload` 仅负责接收文件、生成 file_id/引用，并将“图片解析/OCR/关键信息抽取”入队。
  - OCR 结果与抽取结果必须可追溯到 `source_event_id` 或 file_id，并可用于 evidence 召回。
- **失败策略**：
  - OCR/转写失败不得影响 raw 落库；失败必须记录可审计状态，并可重试。

### 读取工作流（Question -> Retrieval -> Evidence）

目标：后端只负责“证据召回与组装”，最终答案可由上游（Web App 或 OpenClaw）生成并展示证据。

1. 调用 `POST /query`，携带 `mode=fast|deep` 与可选 `time_range`。
2. **shouldSkipRetrieval（召回护栏）**：先于 WeKnora 调用进行判定，避免不必要的外部请求与延迟
   - **【修改】跳过 Deep Retrieval 的典型输入**：问候语/寒暄/简单确认（"好""OK""收到"）、emoji 或短无信息输入、纯命令/斜杠指令
   - **【修改】强制 Deep Retrieval 的典型输入**：包含"记得/之前/上次/回顾/根据文档/查历史/会议纪要/制度/日志"等记忆或证据意图
   - **【修改】CJK 特性**：中文短 query 常见，采用独立的最短长度/阈值策略
   - **【修改】可配置**：阈值、关键词列表、最短长度、跳过规则必须配置化
3. 多路召回：
   - 工作记忆（近 1-7 天对话上下文）
   - 语义记忆（profile facts/preferences/constraints）
   - 向量召回（pgvector）
   - deep 模式下并发调用 WeKnora（混合检索 + 可选 GraphRAG），并对结果进行时间权重重排
4. **【修改】检索排序管线处理**：
   - 候选召回（可并行）
   - 融合（dense 为主，lexical/BM25 保底）
   - 可选 rerank（cross-encoder，失败降级到 fusion）
   - 归一化与过滤（length normalization + hardMinScore）
   - 时间与生命周期重排（time-decay）
   - 噪声过滤与多样性（noise filter + MMR diversity）
5. 统一排序与裁剪：按时间优先与置信度阈值过滤，返回 top-N（建议 3~8）。
6. 返回 `evidence[]`：每条证据包含类型、文本、发生时间、来源、置信度、引用信息与评分详情。

### 擦除工作流（Forget / Erase）

目标：满足“记忆擦除权”，同时保留可审计的作业轨迹。

1. 调用 `POST /forget`，按 `time_range/tags/event_ids` 选择范围。
2. 返回 `erase_job_id`，并以异步作业执行擦除。
3. 通过 `GET /forget/{erase_job_id}` 查询状态（queued/running/succeeded/failed）与影响范围摘要。
4. 擦除策略：
   - **软删除**：对 `raw_events` 标记软删字段；派生物按引用回收或标记失效。
   - **硬删除**：按策略执行物理删除（需明确审计与回执策略）。

### 自动召回护栏（性能/噪音/降级）

- **阈值过滤**：按 `confidence` 过滤低质量证据。
- **证据数量上限**：默认仅返回 top-N，避免上下文注入噪音。
- **短窗口缓存**：同一会话/相近 query 在短窗口内复用召回结果。
- **失败降级**：当 SecondBrainOS 不可用或超时，入口（尤其 OpenClaw）应直接走普通对话路径，避免阻断用户体验。

### embeddings 接入与失败策略

- **接入边界**：embeddings 作为 Core 内部能力，前端与 OpenClaw 不得直接持有相关密钥。
- **失败不阻塞**：embedding 失败不得影响 `raw_events` 落库与其它抽取步骤。
- **可回放重建**：支持从 `raw_events` 回放批量重跑 embedding，并具备可重试与可审计性。

### 配置管理与校验（统一约束）

所有配置必须外部化（环境变量/配置文件），禁止硬编码；并且必须在启动时完成“必需项存在性 + 类型/格式”校验，校验失败必须阻止服务启动。

- **后端（SecondBrainOS Core / worker）**：使用 Pydantic Settings 作为单一事实源（Single Source of Truth）。
- **前端（Web App）**：使用 Zod 对运行时配置（如 baseUrl、功能开关）做加载校验，并从 schema 推导类型。

最低配置集（按 `requirements.md` 对齐，作为设计约束）：

- **LLM / Provider（推理与路由）**
  - `LLM_LLAMA_BASE_URL`
  - `LLM_LLAMA_API_KEY`
  - `LLM_LLAMA_MODEL_ID`
  - `PROVIDER_API_KEY`
  - `PROVIDER_BASE_URL`
  - `PROVIDER_MODEL_ID`
- **Embeddings（SiliconFlow）**
  - `SILICONFLOW_API_KEY`
  - `SILICONFLOW_BASE_URL`
  - `SILICONFLOW_EMBEDDING_MODEL`
- **WeKnora（Episodic Memory）**
  - `WEKNORA_BASE_URL`
  - `WEKNORA_API_KEY`
  - `WEKNORA_REQUEST_TIMEOUT_MS`
  - `WEKNORA_RETRIEVAL_TOP_K`
  - `WEKNORA_RETRIEVAL_THRESHOLD`（可选）
  - `WEKNORA_TIME_DECAY_RATE`
  - `WEKNORA_SEMANTIC_WEIGHT`
  - `WEKNORA_TIME_WEIGHT`

### 幂等、去重与审计日志（统一约束）

- **幂等性**：`POST /ingest` 必须支持 `idempotency_key` 幂等写入；当客户端离线补发时必须优先使用该能力避免重复落库。
- **来源去重**：若无 `idempotency_key`，应至少支持以 `(source, source_message_id)` 作为去重键（当该字段存在时）。
- **审计日志（结构化）**：以下操作必须写入结构化审计日志并可追溯：
  - `POST /forget` 与擦除作业执行（含影响范围摘要）
  - `PUT /profile`（含变更摘要与触发来源）
  - `POST /feedback`（含 evidence 标识、反馈类型与可选 session_id）
  - 所有对外部依赖（WeKnora/embeddings/LLM provider）的调用结果（成功/失败/降级）
- **请求关联**：本项目为非 SaaS/单机形态时不强制 `X-Request-ID`；如需要请求追踪，可在对外接口与对外部依赖调用中贯穿 `X-Request-ID`（不存在则生成）。

### WeKnora 集成配置管理与校验

- WeKnora 作为 Episodic Memory 外部服务，配置必须外部化并在启动时校验（缺失配置必须明确报错）。
- 最低配置集建议：
  - `WEKNORA_BASE_URL`
  - `WEKNORA_API_KEY`
  - `WEKNORA_REQUEST_TIMEOUT_MS`
  - `WEKNORA_RETRIEVAL_TOP_K`
  - `WEKNORA_TIME_DECAY_RATE` / `WEKNORA_SEMANTIC_WEIGHT` / `WEKNORA_TIME_WEIGHT`
- 单机形态不强制对外依赖请求携带 `X-Request-ID`；如启用请求追踪，则应携带以便全链路追踪与审计。

#### 【修改】检索与重排审计要求（外部依赖可观测性）

- **rerank 审计**：必须记录本次请求是否执行 rerank、使用的 provider/model/version、以及降级原因（如超时/5xx）
- **Prompt 注入安全**：当注入召回证据到 prompt 时，必须以"不可信数据"语义注入（见安全与隐私部分的 Prompt 注入安全约束）

#### 【修改】生命周期/衰减（分阶段落地约束）

**阶段 1**：
- 仅 time-decay re-ranking（简单、可解释）

**阶段 2**：
- 引入 access_count/last_accessed_at（强化衰减）

**事实源优先**：
- 生命周期字段不得破坏 raw_events 的可回放与派生可重建原则

**写入点约束**：
- 访问计数/最后访问时间的更新必须通过明确写路径（例如 `/query` 返回后异步记录），不得在热路径造成显著延迟

### 错误处理与结构化错误模型（对外契约）

SecondBrainOS Core 的所有对外接口在失败时必须返回结构化错误，以支持前端展示、上游编排（如 OpenClaw）以及可观测性。

- **错误响应最小字段**：`code`、`message`
- **message 语言**：必须为英文（便于日志检索与稳定性）
- **request_id（可选）**：单机形态不强制；如实现请求追踪，可透传或生成并在日志与响应中返回
- **错误码约束**：
  - 与 HTTP 状态码解耦：`code` 为稳定的业务/系统错误标识
  - 对外错误码必须可枚举并可文档化（实现时以仓库契约文档为准，避免契约漂移）

### WeKnora / 外部依赖的失败策略（契约化）

对 WeKnora、embeddings、外部 LLM provider 等外部依赖请求，必须满足以下一致性要求：

- **显式失败或显式降级**：不得静默吞错。
- **mode=fast**：不得依赖 WeKnora。
- **mode=deep**：必须固定为以下二选一（实现选择后保持一致，并对外可观测）：
  - **失败策略**：返回结构化错误（`code/message`）
  - **降级策略**：降级为 `mode=fast`，并在响应中明确标记降级与原因（字段名与结构需契约化）

### WeKnora 不可用时的降级/失败策略

- `mode=fast`：不得依赖 WeKnora，必须在 WeKnora 不可用时仍可工作。
- `mode=deep`：必须采用一致策略（实现时二选一并固化）：
  - **失败策略**：WeKnora 不可用/超时/鉴权失败时，直接返回结构化错误（`code/message`）。
  - **降级策略**：WeKnora 不可用/超时/鉴权失败时，降级为 `mode=fast` 并在响应中明确标记降级与原因，保证可观测。
- `/episodic/*`（KB 管理、导入、导入状态查询）与 `/feedback`：不允许静默成功；失败必须返回结构化错误并落审计日志。

## 鉴权与租户隔离设计

### 鉴权边界

- **OpenClaw -> SecondBrainOS**：采用 `Authorization: Bearer <OPENCLAW_GATEWAY_TOKEN>` 的机器到机器鉴权。
- **SecondBrainOS Web App**：建议使用独立登录/会话，与 OpenClaw token 分离，避免未来扩展时混用。

### 租户隔离

- 本项目为非 SaaS/单机单用户形态时不需要租户隔离。

## 运维与数据韧性

### 健康检查（/health）

- 必须检查：Postgres、Redis（含队列）、Neo4j 连通性。
- 必须暴露：队列积压/延迟等可用于告警的指标级信息。

### 性能与可观测性指标（含 WeKnora）

- WeKnora 作为外部 Episodic 服务，必须纳入核心可观测指标体系，以便定位“外部依赖导致的延迟/失败/降级”。
- 建议指标（按 endpoint 与 mode 维度打点）：
  - WeKnora 请求延迟：P50/P95/P99（按 `mode=deep`、检索/导入/状态查询分别统计）
  - WeKnora 请求成功率：成功/失败计数与比率（按错误类型：超时/鉴权失败/5xx 等）
  - 降级频率：`mode=deep` 触发降级到 `mode=fast` 的次数与比例（若实现选择降级策略）
  - 熔断/限流触发次数：用于识别外部依赖抖动与保护策略是否生效
- 告警建议：
  - 连续失败或成功率低于阈值触发告警
  - P95/P99 延迟持续超过阈值触发告警
  - 降级频率异常升高触发告警（可能意味着 WeKnora 不可用或性能退化）

### 迁移与回滚

- Postgres schema 变更必须使用迁移工具管理。
- `raw_events` 为事实源（append-only），其余派生物必须可重建；迁移设计需避免破坏事实源可回放能力。

### 备份策略

- 必须定期备份 Postgres（至少包含 `raw_events`、profile/事实与必要元数据）。
- Neo4j 可选择备份或“可重建策略”，但需要明确并可验证。

## 非功能性需求的设计映射

本节将 `requirements.md` 中的非功能性要求映射为可实现、可验证的设计约束。

### 性能目标与关键路径

- **文本响应时间 < 1.5s**：
  - `POST /chat` 与 `POST /query (mode=fast)` 必须以“召回 + 证据组装”为主路径，避免同步阻塞在抽取/embedding/导入等耗时任务上。
  - 所有长耗时任务进入 RQ 异步队列（`consolidate_event/embed_event/...`）。
- **记忆入库延迟 < 10s（异步）**：
  - 以 worker 的 SLA 形式定义：队列等待时间 + 执行时间合计受监控并告警。
- **并发用户 ≥ 1000**：
  - Core API 无状态化（除外：短期 working memory 缓存可由 Redis 承载），支持水平扩展。
  - Postgres/Redis 连接池参数与队列并发度需可配置并纳入压测基线。

### 安全与隐私

- **密钥边界**：embeddings/LLM/WeKnora API key 仅存在于 Core/worker 的服务端环境变量中，前端与 OpenClaw 不得持有。
- **传输加密**：对外 HTTP 必须支持 TLS（部署层约束）；服务间调用同样建议 TLS。
- **存储加密**：对存储介质启用加密（部署层约束）；应用层需避免在日志中输出敏感原文。
- **RBAC（预留）**：单机单用户形态不需要；如未来演进为多用户/多租户，则引入 RBAC 并补齐对应的数据访问控制边界。

#### 【修改】Scope/Namespace 隔离模型

**统一 scope 形态（内部可等价映射）**：
- `global`：全局共享
- `user:<user_id>`：用户级别隔离
- `agent:<agent_id>`：代理级别隔离
- `project:<project_id>`：项目级别隔离
- `custom:<name>`：自定义命名空间

**硬隔离要求**：
- scope 过滤必须在检索/融合之前执行，禁止"先检索再过滤导致泄露"
- 所有 evidence（来自 Postgres/WeKnora/Neo4j）必须携带 user_id/project_id（按适用性）与 scope

**二次校验（多用户/多租户形态适用）**：
- 对外部系统返回结果（如 WeKnora）必须校验其携带的隔离标识与当前请求一致

#### 【修改】Prompt 注入安全约束

**不可信数据标记**：
- 任何 evidence 注入到大模型上下文时必须标记为 `[UNTRUSTED DATA]`（或等价语义）
- 提示模型仅作参考而非指令

**注入数量控制**：
- 默认注入数量必须有上限（top-N）
- 允许按阈值过滤
- 上限与阈值必须可配置

### 合规与用户权利

- **数据不用于训练**：在设计与实现上禁止任何默认数据上报；如需要遥测，必须只上报脱敏指标。
- **数据导出与删除**：
  - 删除通过 `POST /forget` 走可审计异步作业。
  - 导出能力在实现阶段应提供明确的数据范围与格式。

### 离线能力（基本功能）

- **离线输入缓存**：客户端（Web App 或 OpenClaw 侧）在网络不可用时缓存待发送事件；恢复后按顺序补发。
- **幂等性**：补发必须依赖 `idempotency_key` 或 `(source, source_message_id)` 去重，避免重复落库与重复巩固。
- **离线只保证 capture**：离线期间不要求 deep 检索可用；一旦联网由 Core 进行异步巩固。

## 组件和接口

### 核心 API 接口

#### 数据录入接口

**POST /ingest**
- **功能**：录入原始事件数据
- **请求参数**：
  - `source`: 来源渠道（telegram/webchat/whatsapp等）
  - `source_message_id`: 来源消息ID（可选）
  - `occurred_at`: 发生时间
  - `content`: 原始内容
  - `tags`: 标签（可选）
  - `idempotency_key`: 幂等键（可选）
- **响应数据**：
  - `event_id`: 事件唯一标识
  - `queued_jobs`: 已入队的巩固任务列表

**POST /chat**
- **功能**：对话式交互接口
- **处理流程**：
  1. 写入 raw_events
  2. 自动召回 evidence（fast 模式）
  3. 调用模型生成回复
  4. 返回 assistant_message + evidence[]

**POST /upload**
- **功能**：文件上传接口
- **支持格式**：JPG、PNG、WebP
- **处理能力**：OCR 文字提取、AI 信息抽取

#### 查询检索接口

**POST /query**
- **功能**：智能查询接口
- **请求参数**：
  - `query`: 查询语句
  - `top_k`: 返回结果数量
  - `time_range`: 时间范围（可选）
  - `mode`: 查询模式（fast/deep）
- **响应数据**：
  - `answer_hint`: 答案提示（可选）
  - `evidence[]`: 证据列表
    - `evidence_id`: 证据ID
    - `type`: 证据类型（raw_event/profile_fact/graph_fact）
    - `text`: 证据文本
    - `occurred_at`: 发生时间
    - `source`: 来源
    - `confidence`: 置信度
    - `refs`: 引用信息

##### 【修改】检索排序管线（统一抽象，agent-agnostic）

**候选召回（可并行）**：
- Semantic（pgvector/结构化事实）
- Episodic（WeKnora 混合检索/可选 GraphRAG）
- （可选）Graph（Neo4j 扩展召回）

**融合（fusion）**：
- dense 为主
- lexical/BM25 命中提供奖励/保底（尤其是符号型查询：ID、token、配置项、环境变量等）

**可选 rerank（cross-encoder 或等价重排）**：
- 失败必须降级到 fusion 结果

**归一化与过滤**：
- length normalization
- hardMinScore（硬过滤无关结果）

**时间与生命周期重排**：
- time-decay / recency boost（阶段 1）
- 后续可演进为 reinforcement/tier

**噪声过滤与多样性**：
- noise filter
- MMR diversity（相似项延后而非删除）

##### 【修改】可用性与顺序约束

- **任何上游不可用时的降级**：WeKnora、rerank provider、图谱不可用时，`/query` 必须仍能返回结果（至少走 Semantic/Working Memory 回退路径）
- **过滤顺序**：`hardMinScore` 必须发生在 time-decay/lifecycle 之前，避免衰减项抬高低质结果
- **符号型查询保底**：对高置信 lexical 命中设置 preservation floor，避免被 rerank 轻易淘汰
- **可解释性**：evidence[] 必须携带关键评分信息（至少 final_score；推荐同时包含 dense_score/bm25_score/rerank_score）

**GET /memories**
- **功能**：获取记忆列表（供 Sidebar 展示）
- **返回**：已巩固的记忆摘要

**GET /conversations/{id}/messages**
- **功能**：获取对话历史（供 Chat 展示）
- **返回**：消息列表及相关证据

#### 管理接口

**POST /forget**
- **功能**：记忆擦除接口
- **请求参数**：
  - `time_range`: 时间范围
  - `tags`: 标签过滤
  - `event_ids`: 事件ID列表
- **响应数据**：
  - `erase_job_id`: 擦除作业ID

**GET /forget/{erase_job_id}**
- **功能**：擦除作业状态查询
- **返回**：作业状态（queued/running/succeeded/failed）和影响范围摘要

**GET /profile**
- **功能**：获取用户档案
- **返回**：用户偏好、事实、约束条件

**PUT /profile**
- **功能**：更新用户档案
- **支持**：手动编辑和确认自动提取的信息

**GET /health**
- **功能**：系统健康检查
- **检查项**：Postgres/Redis/Neo4j 连通性、队列积压情况

**POST /episodic/knowledge-bases**
- **功能**：创建 KnowledgeBase（WeKnora）

**GET /episodic/knowledge-bases**
- **功能**：列出 KnowledgeBase（WeKnora）

**POST /episodic/ingestions**
- **功能**：导入文档/URL/对话摘要到 WeKnora（异步作业）

**GET /episodic/ingestions/{ingestion_job_id}**
- **功能**：导入作业状态查询（queued/running/succeeded/failed）

**POST /feedback**
- **功能**：反馈纠错（关联 WeKnora chunk/knowledge 引用，用于后续降权/过滤）

### 反馈纠错（Feedback）设计

目标：让用户对“被引用的证据”进行可审计反馈，并影响后续检索排序/过滤。

- **反馈对象**：必须至少支持关联 WeKnora 返回的 chunk/knowledge 引用；也可扩展支持 raw_event/profile_fact/graph_fact。
- **反馈类型**：`incorrect` / `outdated` / `incomplete`
- **可选纠正文本**：`user_correction`（可空）
- **审计字段（必须可追溯）**：`session_id`（若有）、提交时间、evidence 标识、原 query（若有）、来源（web/openclaw 等）。
- **影响策略（必须确定性）**：
  - `incorrect/outdated`：后续检索必须降低权重或排除（实现需选择并保持一致）；并确保不会在证据链展示中“被反馈后仍高频出现”。
  - `incomplete`：不一定过滤，但可降低权重并触发异步巩固/归档（例如将纠正文本作为新事件写入 raw_events，再走巩固）。
- **外部依赖失败时的行为**：
  - 若反馈链路需要调用 WeKnora（例如写回其反馈系统或更新其权重）：配置缺失/不可用时必须返回结构化错误（`code/message`），不得静默成功。

### 异步巩固任务

#### 任务类型

**consolidate_event(event_id)**
- **功能**：抽取结构化信息
- **处理内容**：实体、关系、偏好变化、待办事项等
- **输出**：写入 extractions 表

**upsert_profile(extraction_id)**
- **功能**：冲突解决和版本化
- **处理逻辑**：
  1. 检索现有档案
  2. 识别冲突（如偏好变化）
  3. 执行覆写操作
  4. 归档历史版本

**embed_event(event_id)**
- **功能**：生成向量嵌入
- **技术栈**：SiliconFlow API
- **输出**：写入 pgvector

**upsert_graph(extraction_id)**
- **功能**：更新知识图谱
- **操作**：Neo4j MERGE 节点/关系
- **元数据**：带 source_event_id 与时间戳

#### 工作流程

1. **输入与快响应**：用户输入放入工作记忆，瞬间回复确认
2. **后台静默提取**：分类器判断 + 实体抽取 + GraphRAG 处理
3. **记忆冲突解决**：检索旧记录，执行覆写操作，归档历史

### 多路召回机制

#### 召回策略

**Fast 模式**：
- 工作记忆查询（近 1-7 天）
- 语义记忆查询（profile/facts）
- pgvector 向量检索
- 时间优先规则排序

**Deep 模式**：
- 包含 Fast 模式所有功能
- 并发 WeKnora 检索（混合检索 + 可选 GraphRAG）
- 时间权重重排（Time-Decay Re-ranking）与阈值策略
- 更昂贵的推理计算（若需要多轮检索/多工具）

#### 护栏机制

- **阈值过滤**：按 confidence 过滤低质量证据
- **结果限制**：默认返回 top-N（3~8 条）证据
- **缓存复用**：同一会话/相近查询短窗口内复用结果
- **失败降级**：SecondBrainOS 不可用时，系统仍可正常对话

## 数据模型

### 设计原则（数据层）

- **事实源优先**：`raw_events` 作为事实源 append-only（支持软删字段）；所有派生数据必须可回放重建。
- **可审计**：所有结构化抽取、档案更新、图谱关系与 embedding 结果需能追溯到 `source_event_id/event_id`。
- **按 user_id 隔离**：单机单用户形态不需要。

### 原始事件（Raw Events）

- **定位**：唯一事实源；写入不应被后续处理阻塞。
- **核心字段**：`event_id`、`source`、`source_message_id(可选)`、`content`、`occurred_at`、`created_at`、`metadata(可选)`、`deleted_at(可选软删)`。
- **索引建议**：`occurred_at` 用于时间线与时间范围查询；`source` 与 `deleted_at` 用于过滤。

### 结构化提取（Extractions）

- **定位**：对 `raw_events` 的抽取产物（实体/关系/偏好变化/待办等）。
- **核心字段**：`extraction_id`、`event_id`、`extraction_type`、`content`、`confidence`、`created_at`。
- **设计要点**：抽取内容以结构化 JSON 表达；任何抽取都必须带置信度与来源引用。

### 用户档案（User Profile + History）

- **定位**：语义记忆的“当前态 + 历史版本”。
- **current**：维护 `current_profile`（包含 facts/preferences/constraints 等）与 `version/updated_at`。
- **history**：每次发生冲突解决或显著更新时写入快照与原因，支持回溯与审计。

### 向量存储（Embeddings / pgvector）

- **定位**：面向 fast 模式检索的向量索引。
- **核心字段**：`embedding_id`、`event_id`、`embedding`、`model_name`、`created_at`。
- **索引建议**：按相似度检索建立向量索引。

### Neo4j 图谱模型（Episodic / GraphRAG）

- **定位**：可选的图谱增强能力（通常由 WeKnora GraphRAG profile 提供）；用于 deep 模式下关系推理与跨实体关联召回。
- **节点类别（示例）**：Person、Event、Location、Thing（可扩展）。
- **关系类别（示例）**：参与、发生于、关联、认识等。
- **关键约束**：关键关系必须记录 `source_event_id` 与时间戳，确保可追溯。

### 前端状态模型（概念）

- **Memory**：`id`、`content`、`type(preference|fact|event)`、`timestamp`、（可选）`confidence/source`。
- **Message**：`id`、`role(user|assistant|system)`、`content`、`timestamp`、（可选）`evidence[]`。
- **Evidence**：`evidence_id`、`type(raw_event|profile_fact|graph_fact)`、`text`、`occurred_at`、`source`、`confidence`、（可选）`refs`。

#### 【修改】Evidence（统一元数据中枢规范，作为跨存储后端的收敛点）

**标识字段**：
- `evidence_id`：证据唯一标识
- `type`：证据类型
- `refs`：引用信息（用于跳转/审计）

**隔离字段**：
- `user_id`：用户标识（单机单用户形态可默认常量）
- `project_id`：项目标识（如适用）
- `scope`：命名空间范围（global、user:<user_id>、agent:<agent_id>、project:<project_id>、custom:<name>）

**时间字段**：
- `occurred_at`：发生时间（优先）
- `created_at`：创建时间（次之）

**质量字段**：
- `confidence`：置信度
- `scores`：评分详情（推荐：dense_score、bm25_score、rerank_score、final_score）

**审计字段**：
- `request_id`：请求标识（可选）
- `retrieval_trace`：检索追踪信息（可选）

## 阶段性能力与开关策略（演进路线图对齐）

### MVP（阶段 1）

- 目标：先实现可用的 capture + 基础语义记忆 + 对话与 fast 检索。
- 能力取舍：
  - 不引入复杂 GraphRAG 深度推理（可保留 Neo4j 作为后续扩展，但不作为关键路径依赖）。
  - 不强制多模态与主动触发（可作为阶段 2/3）。

### 阶段 2（关系推理）

- 引入 Neo4j 与 GraphRAG 流程，完善 deep 模式的图谱扩展召回。
- 增加多模态输入（Vision/OCR）并纳入异步巩固。

### 阶段 3（主动服务）

- 引入定时触发 Agent（Cron Jobs）与情境触发能力。
- 接入日历/GPS/健康数据等外部信号源，形成主动提醒与建议链路。