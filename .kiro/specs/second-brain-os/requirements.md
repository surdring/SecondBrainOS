# SecondBrainOS 需求文档

## 权威文档引用

本文档定义 SecondBrainOS 系统的功能需求、技术约束和验收标准。所有设计决策和实现约束必须以本文档为最高权威依据。

### 约束优先级
1. **本文档**：功能需求、非功能性需求、技术约束、验收标准
2. **设计文档**：基于本文档的技术架构和实现方案
3. **任务文档**：基于本文档和设计文档的具体实施任务

### 关键约束来源
- **WeKnora 集成策略**：3.2.3 节明确 WeKnora 作为 Episodic Memory 的唯一检索与理解层
- **检索排序管线**：3.1.2 节定义完整的 agent-agnostic 检索排序管线
- **召回护栏机制**：5.6 节定义 shouldSkipRetrieval 召回护栏
- **安全与隔离**：5.2 节定义 Scope/Namespace 隔离和 Prompt 注入安全
- **外部依赖策略**：6.4 节统一的失败/降级策略

## 1. 产品概述

### 1.1 产品愿景
SecondBrainOS 是一个主动的、具备时间感知的"数字外脑"系统。它不仅能无摩擦地记录用户的碎片化信息，更能像人类大脑一样，自动将信息结构化、处理矛盾记忆（如用户偏好改变），并通过复杂逻辑推理回答跨越时间维度的提问。

### 1.2 核心价值主张
- **无摩擦录入**：支持语音、文字、图片等多模态输入，降低记录门槛
- **智能记忆管理**：自动结构化信息，处理记忆冲突，维护用户数字画像
- **时间感知推理**：理解时间概念，支持跨时间维度的复杂查询
- **主动服务**：基于情境和时间主动提供提醒和建议

### 1.3 核心痛点与解决方案
- **痛点 1：输入阻力大** → 解决：支持全局语音输入、截图与多渠道转发集成
- **痛点 2：传统搜索像"大海捞针"** → 解决：采用 GraphRAG 构建人物/事件关系图谱，支持逻辑推理问答
- **痛点 3：AI记不住"我是谁"且记忆矛盾** → 解决：采用 Agentic Memory 架构，AI 在后台主动更新、覆写、遗忘用户的状态配置

## 2. 用户故事与验收标准

### 2.1 无摩擦录入模块

#### 用户故事 2.1.1：全局语音速记
**作为** 用户  
**我希望** 能够通过语音快速记录想法和信息  
**以便** 在不中断当前工作的情况下捕获重要信息  

**验收标准：**
- 支持语音输入并自动转录为文字
- 转录准确率 ≥ 95%（中文普通话）
- 语音转录延迟 < 3 秒
- 支持噪音环境下的语音识别
- 自动提取关键信息（人物、地点、时间、事件）
- 系统瞬间回复确认（"好的，记住了"），延迟 < 1 秒

#### 用户故事 2.1.2：多模态解析
**作为** 用户  
**我希望** 能够发送图片或截图让系统自动提取信息  
**以便** 快速记录视觉信息而无需手动输入  

**验收标准：**
- 支持图片上传（JPG、PNG、WebP 格式）
- 自动 OCR 提取图片中的文字信息
- 识别图片中的待办事项、地点、人物信息
- OCR 准确率 ≥ 90%（中英文混合）
- 图片处理时间 < 10 秒
- AI 自动提取画面中的待办、地点或人脉信息

#### 用户故事 2.1.3：多端同步入口
**作为** 用户  
**我希望** 能够从多个渠道输入信息  
**以便** 在任何场景下都能方便地记录信息  

**验收标准：**
- 支持 Web 端直接输入
- 支持微信/Telegram Bot 转发
- 支持浏览器插件划线保存
- 所有渠道的信息能够统一管理
- 支持离线缓存，网络恢复后自动同步

### 2.2 智能记忆管理模块

#### 用户故事 2.2.1：动态用户档案管理
**作为** 用户  
**我希望** 系统能够自动维护我的数字画像  
**以便** 系统能够更好地理解我的偏好和状态变化  

**验收标准：**
- 自动提取并更新用户偏好信息
- 处理偏好冲突（如"医生让我以后别喝咖啡了" → 系统主动将档案中的"爱好：咖啡"更新为"禁忌：咖啡"）
- 维护用户状态的历史版本
- 支持手动编辑和确认自动提取的信息
- 偏好更新的准确率 ≥ 85%
- 记忆冲突解决：检索发现旧记录时，Agentic Memory 主动执行数据库覆写操作，并将旧记录归档为历史

#### 用户故事 2.2.2：时间感知记录
**作为** 用户  
**我希望** 系统能够理解时间概念  
**以便** 能够回答"上周"、"昨天"等相对时间的问题  

**验收标准：**
- 每条记录自动打上精确时间戳
- 理解相对时间概念（昨天、上周、上个月等）
- 支持时间范围查询
- 能够处理时区变化
- 时间解析准确率 ≥ 95%

#### 用户故事 2.2.3：反馈纠错与自我修正
**作为** 用户  
**我希望** 能够对系统引用的错误/过时/不完整信息进行反馈与纠正  
**以便** 系统后续检索与回答能持续变得更准确  

**验收标准：**
- 用户可以对任意一条 evidence（尤其是 WeKnora chunk/knowledge 引用）提交反馈：incorrect/outdated/incomplete
- 支持填写可选的用户纠正文本（user_correction）
- 反馈必须被记录并可审计（包含时间、关联 evidence 标识；可选 session_id）
- 对被标记为 incorrect/outdated 的证据，后续检索必须降低其权重或排除
- 配置缺失或外部依赖不可用时，反馈接口必须返回结构化错误（code/message）

### 2.3 检索与交互模块

#### 用户故事 2.3.1：语义与逻辑问答
**作为** 用户  
**我希望** 能够用自然语言查询我的记忆  
**以便** 快速找到需要的信息  

**验收标准：**
- 支持基础事实查询（"我的护照号码是多少？"）
- 支持复杂逻辑查询（"上周二跟我开会的那个长发投资人，他当时推荐了什么书？"）
- 查询响应时间 < 1.5 秒
- 查询准确率 ≥ 90%
- 提供查询结果的证据链和来源
- 多路召回：查询工作记忆 + 查询状态库 + 图谱/向量检索

#### 用户故事 2.3.2：主动触发与提醒
**作为** 用户  
**我希望** 系统能够主动提醒我相关信息  
**以便** 在合适的时间和场景获得帮助  

**验收标准：**
- 基于时间的自动提醒（时间触发：基于日程提醒）
- 基于地理位置的情境提醒（情境触发：当用户到达超市，主动推送前天随口提过的购物清单）
- 支持提醒规则的自定义
- 提醒的相关性准确率 ≥ 80%
- 支持提醒的确认和延后

## 3. 功能需求

### 3.1 核心 API 接口

#### 3.1.1 数据录入接口
- `POST /ingest`：录入原始事件数据
  - 入参：source、source_message_id、occurred_at、content、tags（可选）、idempotency_key（可选）
  - 出参：event_id、queued_jobs
- `POST /chat`：对话式交互接口
  - 后端负责：写入 raw_events、自动召回 evidence（fast）、调用模型生成回复、返回 assistant_message + evidence[]
- `POST /upload`：文件上传接口

#### 3.1.2 查询检索接口
- `POST /query`：智能查询接口
  - 入参：query、top_k、time_range（可选）、mode（fast/deep）
  - 出参：answer_hint（可选）、evidence[]（含 evidence_id、type、text、occurred_at、source、confidence、refs）
- 【新增】`POST /query` 检索排序管线（统一抽象，agent-agnostic）：
  - 【新增】候选召回（可并行）：Semantic（pgvector/结构化事实）+ Episodic（WeKnora 混合检索/可选 GraphRAG）+（可选）Graph（Neo4j 扩展召回）
  - 【新增】融合（fusion）：dense 为主；lexical/BM25 命中提供奖励/保底（尤其是符号型查询：ID、token、配置项、环境变量等）
  - 【新增】可选 rerank（cross-encoder 或等价重排）：失败必须降级到 fusion 结果
  - 【新增】归一化与过滤：length normalization；hardMinScore（硬过滤无关结果）
  - 【新增】时间与生命周期重排：time-decay / recency boost（阶段 1）；后续可演进为 reinforcement/tier（见 3.2.4/5.6）
  - 【新增】噪声过滤与多样性：noise filter；MMR diversity（相似项延后而非删除）
- 【新增】`POST /query` 可用性与顺序约束：
  - 【新增】任何上游（WeKnora、rerank provider、图谱）不可用时，`/query` 必须仍能返回结果（至少走 Semantic/Working Memory 回退路径）
  - 【新增】`hardMinScore` 必须发生在 time-decay/lifecycle 之前，避免衰减项抬高低质结果
  - 【新增】必须支持“符号型查询保底”策略；对高置信 lexical 命中设置 preservation floor，避免被 rerank 轻易淘汰
  - 【新增】可解释性：evidence[] 必须携带关键评分信息（至少 final_score；推荐同时包含 dense_score/bm25_score/rerank_score）
- `GET /memories`：获取记忆列表（供 Sidebar 展示）
- `GET /conversations/{id}/messages`：获取对话历史（供 Chat 展示）

#### 3.1.3 管理接口
- `POST /forget`：记忆擦除接口
  - 入参：按 time_range / tags / event_ids
  - 出参：erase_job_id（可查询状态）
- `GET /forget/{erase_job_id}`：擦除作业状态查询接口
  - 返回擦除作业的状态（queued/running/succeeded/failed）与影响范围摘要（如被软删/硬删的事件数量）
- `GET /profile`：获取用户档案
- `PUT /profile`：更新用户档案
- `GET /health`：系统健康检查（检查 Postgres/Redis/Neo4j 连通性、队列积压）
- `POST /episodic/knowledge-bases`：创建 KnowledgeBase（WeKnora）
- `GET /episodic/knowledge-bases`：列出 KnowledgeBase（WeKnora）
- `POST /episodic/ingestions`：导入文档/URL/对话摘要到 WeKnora（异步作业）
  - 入参：kb_id、source_type(file|url|conversation_summary)、source_payload、tags（可选）、occurred_at（可选）
  - 出参：ingestion_job_id
- `GET /episodic/ingestions/{ingestion_job_id}`：导入作业状态查询（queued/running/succeeded/failed）
- `POST /feedback`：反馈纠错（支持关联 WeKnora chunk/knowledge 引用）

### 3.2 分层记忆架构

#### 3.2.1 工作记忆（Working Memory）
- Context Window + Prompt Caching (CAG)
- 存储最近 1-7 天的对话上下文，极速响应

#### 3.2.2 语义记忆（Semantic/Agentic Memory）
- Redis / PostgreSQL，基于 Mem0 架构
- 存储用户的核心事实、状态、偏好
- 例如：姓名=张三, 职业=程序员, 忌口=花生

#### 3.2.3 情景记忆（Episodic Memory）
- 以 **WeKnora** 作为 Episodic Memory 的“检索与理解层”（文档解析/分块/索引/混合检索/可选 GraphRAG 增强）
- SBO 保留编排层（Orchestration）：决定何时检索 WeKnora、何时写入 WeKnora、何时做对话摘要归档，以及权限/隔离/审计
- 适用内容：海量日志、历史文档、会议记录、对话摘要归档等

#### 3.2.4 Episodic 的读写策略（WeKnora 集成约束）
- **读路径（Deep Mode）**：SBO 并发检索 Semantic Memory + WeKnora（混合检索 + 可选 GraphRAG），返回 evidence（含可追溯来源元数据）
- **写路径（Episodic Ingestion）**：文档/URL/对话摘要作为 Knowledge 写入 WeKnora；SBO 记录导入作业状态（成功/失败/重试）
- **时间权重重排（Time-Decay Re-ranking）**：SBO 侧对 WeKnora 返回结果按时间衰减进行二次重排，提高“近期情景事实”优先级

- 【新增】Cross-Encoder 重排与降级策略（适用于 deep 或需要高质量答案的场景）：
  - 【新增】重排 provider 不得成为 `/query` 的强依赖；不得因重排超时导致整体超时
  - 【新增】重排必须有独立超时与并发控制
  - 【新增】重排失败时必须降级回 fusion 排序，并在响应或审计日志中记录降级原因（如 timeout/5xx）
  - 【新增】混合评分：rerank 分数不应完全覆盖原始相关性，推荐加权融合
  - 【新增】符号查询保护：对高 BM25/lexical 命中设置保底阈值，避免 cross-encoder 错杀

时间权重重排建议算法：
- 从 WeKnora 检索结果中获取每条 chunk 的 `occurred_at` 或 `created_at`
- 计算时间衰减权重：`time_weight = exp(-WEKNORA_TIME_DECAY_RATE * days_ago)`
- 最终分数：`final_score = semantic_score * WEKNORA_SEMANTIC_WEIGHT + time_weight * WEKNORA_TIME_WEIGHT`

### 3.3 异步巩固任务

#### 3.3.1 任务拆分（Redis Queue / RQ）
- `consolidate_event(event_id)`：抽取结构化信息（实体/关系/偏好变化/待办等），写入 extractions
- `upsert_profile(extraction_id)`：冲突解决 + 版本化（current + history）
- `embed_event(event_id)`：生成 embedding 写入 pgvector
- `upsert_graph(extraction_id)`：Neo4j MERGE 节点/关系（带 source_event_id 与时间戳）

#### 3.3.2 工作流程
1. **输入与快响应**：用户输入放入工作记忆，瞬间回复确认
2. **后台静默提取**：分类器判断 + 实体抽取 + GraphRAG 处理
3. **记忆冲突解决**：检索旧记录，执行覆写操作，归档历史

### 3.4 写入/读取数据流（权威工作流）

#### 3.4.1 写入（Capture -> Consolidation）
1. 用户通过 Web App 或 OpenClaw 任意渠道输入。
2. 前台必须快速确认（“记住了/收到”），不得被巩固流程阻塞。
3. 调用 `POST /ingest` 将事件写入 `raw_events`（事实源）。
4. 服务端将 `consolidate_event(event_id)` 入队（RQ/Redis），由 worker 异步处理。
5. worker 后台完成：抽取结构化信息、更新语义记忆（profile current + history）、生成 embedding、写入/更新 Neo4j 子图。

#### 3.4.2 读取（Question -> Retrieval -> Evidence）
1. 客户端或 OpenClaw 调用 `POST /query`。
2. 后端执行多路召回：工作记忆（近 1-7 天）+ 语义记忆（profile/facts）+ 向量检索 +（deep 模式下）图谱扩展。
3. `POST /query` 的返回必须包含 `evidence[]`（带时间戳/来源/置信度/引用），用于前端或上游模型生成最终答案并可展示证据。

### 3.5 embeddings 接入策略与失败策略

#### 3.5.1 接入边界
- embeddings 必须作为 SecondBrainOS Core 的内部能力，对调用方（Web App/
OpenClaw）透明。
- OpenClaw/前端不得直接持有 embeddings 的 API key。

#### 3.5.2 失败策略（必须）
- embedding 失败不得影响 `raw_events` 落库与其它抽取步骤的执行。
- 系统必须支持对历史事件批量重跑 embedding（从 `raw_events` 回放），并可重试且
可审计。

### 3.6 数据模型

#### 3.6.1 原始事件（Raw Events）
- event_id：事件唯一标识
- user_id：用户标识（可选；单机单用户形态不需要）
- source：来源渠道（telegram/webchat/whatsapp...）
- content：原始内容
- occurred_at：发生时间
- created_at：创建时间
- metadata：元数据
- 作为事实源 append-only（支持软删字段），其余派生表/索引可重建

#### 3.6.2 结构化记忆（Structured Memory）
- memory_id：记忆唯一标识
- type：记忆类型（preference/fact/event）
- content：记忆内容
- confidence：置信度
- source_events：来源事件列表
- created_at：创建时间
- updated_at：更新时间

#### 3.6.3 用户档案（User Profile）
- user_id：用户标识（可选；单机单用户形态不需要）
- preferences：偏好信息
- facts：事实信息
- constraints：约束条件
- version：版本号
- updated_at：更新时间

#### 3.6.4 前端状态模型
- **Memory**：id、content、type（preference | fact | event）、timestamp
- **Message**：id、role（user | assistant | system）、content、
timestamp、evidence[]（可选）
- **Evidence**：evidence_id、type（raw_event | profile_fact | 
graph_fact）、text、occurred_at、source、confidence、refs

- 【新增】Evidence（统一元数据中枢规范，作为跨存储后端的收敛点）：
  - 【新增】标识：evidence_id、type、refs
  - 【新增】隔离：user_id（单机单用户形态可默认常量）、project_id（如适用）、scope（见 5.2/6.1.1）
  - 【新增】时间：occurred_at（优先）、created_at（次之）
  - 【新增】质量：confidence、scores（推荐：dense/bm25/rerank/final）
  - 【新增】审计：request_id、retrieval_trace（可选）

## 4. 技术架构需求

### 4.1 技术栈选型

#### 4.1.1 后端技术栈
- **框架**：FastAPI + Redis Queue (RQ worker)
- **数据库**：PostgreSQL + pgvector（存储原始文本与系统元数据）
- **缓存**：Redis（缓存 + 队列）
- **记忆框架**：Mem0（专为 LLM 设计的自适应记忆层）
- **Episodic Memory 引擎**：WeKnora（通过 HTTP REST API 集成）
- **图谱增强（可选）**：WeKnora 启用 GraphRAG profile 时可使用其内置 Neo4j；SBO Core 不把 Neo4j 作为 MVP 硬依赖

#### 4.1.2 大模型驱动层
- **本地推理（llama.cpp）**：DeepSeek V3 / Llama-3（快速低成本，用于日常对话与路由）
- **外部 PROVIDER**：DeepSeek R1 / Claude 3.5 Sonnet / GPT-4o（复杂推理，用于记忆归档与复杂推理）
- **Embeddings**：硅基流动（SiliconFlow）API

#### 4.1.3 前端技术栈
- **框架**：Vite + React + TypeScript + Tailwind
- **复用策略**：从 zip/ 原型迁移 UI 组件（Chat.tsx、Sidebar.tsx、ErrorBoundary.tsx）
- **API Client**：统一处理 baseUrl、鉴权、错误、重试与超时

### 4.2 OpenClaw 集成（可选）

#### 4.2.1 架构边界
- **OpenClaw 负责**：多渠道接入、会话隔离与安全策略、Skills/Tools 编排、控制台与运维入口
- **SecondBrainOS Core 负责**：记忆写入与异步巩固、分层记忆存储、检索与证据组装、擦除权与审计

#### 4.2.2 集成原则
- OpenClaw 可频繁升级；SecondBrainOS Core 的 API 契约保持稳定
- 任何输入先落 raw（可回放）；profile/graph/vector 等均为派生物（可重建）
- SecondBrainOS 必须可独立使用，不依赖 OpenClaw

#### 4.2.3 鉴权边界（建议但需在实现中保持一致）
- OpenClaw -> SecondBrainOS：使用 `Authorization: Bearer <OPENCLAW_GATEWAY_TOKEN>` 进行机器到机器鉴权。
- SecondBrainOS 独立 Web App：建议使用独立的登录/会话体系，与 OpenClaw 的 Bearer token 分离。

## 5. 非功能性需求

### 5.1 性能需求
- **文本响应时间**：< 1.5 秒
- **记忆入库延迟**：< 10 秒（异步处理）
- **高频上下文缓存命中率**：≥ 80%（利用长上下文 CAG 技术）
- **系统可用性**：≥ 99.5%
- **并发用户支持**：≥ 1000 用户

### 5.2 安全与隐私需求
- **数据加密**：传输和存储均采用 AES-256 加密
- **租户隔离**：单机单用户形态不需要；如未来演进为多用户/多租户，则按用户 ID 进行数据库行级隔离，图数据库按用户建立 Sub-graph
- **访问控制**：单机单用户形态不需要 RBAC；如未来演进为多用户/多租户，则引入 RBAC
- **审计日志**：完整的操作审计日志
- **记忆擦除权**：用户可以说"忘掉昨天下午关于投资的所有对话"，系统必须具备软删除（Soft Delete）和硬删除的机制
- **混合部署模式**（可选）：提供"端云结合"方案，敏感对话和状态提取完全在用户本地完成

- 【新增】Scope/Namespace 隔离模型（单机单用户也需保留字段语义以便未来演进）：
  - 【新增】统一支持 scope 形态（内部可等价映射）：global、user:<user_id>、agent:<agent_id>、project:<project_id>、custom:<name>
  - 【新增】硬隔离：scope 过滤必须在检索/融合之前执行，禁止“先检索再过滤导致泄露”
  - 【新增】统一字段：所有 evidence（来自 Postgres/WeKnora/Neo4j）必须携带 user_id/project_id（按适用性）与 scope
  - 【新增】二次校验（多用户/多租户形态适用）：对外部系统返回结果（如 WeKnora）必须校验其携带的隔离标识与当前请求一致

- 【新增】Prompt 注入安全约束（统一适用）：
  - 【新增】任何 evidence 注入到大模型上下文时必须标记为 `[UNTRUSTED DATA]`（或等价语义），提示模型仅作参考而非指令
  - 【新增】默认注入数量必须有上限（top-N），并允许按阈值过滤；上限与阈值必须可配置

### 5.3 运维与数据韧性需求

#### 5.3.1 健康检查
- `GET /health` 必须检查 Postgres/Redis/Neo4j 连通性以及队列积压情况，并返回可用于告警的结构化结果。

#### 5.3.2 迁移与回滚
- Postgres schema 变更必须通过迁移工具管理（如 Alembic）。
- `raw_events` 作为事实源必须保持 append-only（可包含软删字段），其余派生表/索引/图谱必须可从事实源重建。

#### 5.3.3 备份策略
- 必须支持定期备份 Postgres（至少包含 `raw_events`、profile/事实与必要元数据）。
- Neo4j 允许选择“备份”或“可重建策略”，但必须明确并可执行验证。

### 5.4 可扩展性需求
- **水平扩展**：支持服务的水平扩展
- **存储扩展**：支持数据存储的弹性扩展
- **模块化设计**：核心功能模块化，便于独立升级
- **API 版本管理**：支持 API 版本向后兼容

### 5.5 可维护性需求
- **代码覆盖率**：≥ 80%
- **文档完整性**：API 文档、部署文档、用户文档齐全
- **监控告警**：完善的系统监控和告警机制
- **日志管理**：结构化日志，便于问题排查

### 5.6 自动召回护栏
- **阈值**：按 confidence 过滤低质量证据；默认只注入 top-N（如 3~8 条）
- **缓存**：同一会话/相近 query 在短窗口内复用召回结果，减少重复调用
- **失败降级**：SecondBrainOS 不可用时，OpenClaw 直接正常聊天（不影响 OpenClaw 原有能力）
- **分档策略**：mode=fast 用 pgvector + 时间优先规则；mode=deep 才做图谱扩展与更昂贵的推理

- 【新增】shouldSkipRetrieval（召回护栏）与噪声过滤：
  - 【新增】护栏判定必须先于 WeKnora 调用，以避免不必要的外部请求与延迟
  - 【新增】跳过 Deep Retrieval 的典型输入：问候语/寒暄/简单确认（“好”“OK”“收到”）、emoji 或短无信息输入、纯命令/斜杠指令（若系统已用 tool 直达处理）
  - 【新增】强制 Deep Retrieval 的典型输入：包含“记得/之前/上次/回顾/根据文档/查历史/会议纪要/制度/日志”等记忆或证据意图
  - 【新增】CJK 特性：中文短 query 常见，应采用独立的最短长度/阈值策略，避免误判为“无需检索”
  - 【新增】可配置：阈值、关键词列表、最短长度、跳过规则必须配置化，并在审计日志中记录生效配置版本

## 6. 约束条件

### 6.1 技术约束
- **后端框架**：必须使用 FastAPI 框架
- **数据库**：必须使用 PostgreSQL + pgvector
- **缓存**：必须使用 Redis
- **前端框架**：必须使用 React + TypeScript
- **Python 环境**：强制使用项目根目录的 .venv 虚拟环境
- **编码规范**：TypeScript Strict（禁止 any），前端使用 Zod 校验，后端使用 Pydantic

### 6.1.1 情景记忆（Episodic）集成约束
- **WeKnora 为权威 Episodic 检索与理解层**：SBO 不在 Core 内重复实现文档解析/分块/混合检索
- **Neo4j 可选**：仅当启用 WeKnora GraphRAG（或后续阶段的图谱增强）时需要；MVP 阶段不作为必需依赖
- **隔离与审计**：单机单用户形态不强制 `X-Request-ID`；如需要请求追踪可携带 `X-Request-ID`；如启用多租户/组织能力，必须保证 tenant/organization/KB 的硬隔离

- 【新增】检索与重排审计要求（外部依赖可观测性）：
  - 【新增】必须记录本次请求是否执行 rerank、使用的 provider/model/version、以及降级原因（如超时/5xx）
  - 【新增】当注入召回证据到 prompt 时，必须以“不可信数据”语义注入（见 5.2 Prompt 注入安全约束）

- 【新增】生命周期/衰减（分阶段落地约束）：
  - 【新增】阶段 1：仅 time-decay re-ranking（简单、可解释）
  - 【新增】阶段 2：引入 access_count/last_accessed_at（强化衰减）
  - 【新增】事实源优先：生命周期字段不得破坏 raw_events 的可回放与派生可重建原则
  - 【新增】写入点约束：访问计数/最后访问时间的更新必须通过明确写路径（例如 `/query` 返回后异步记录），不得在热路径造成显著延迟

### 6.2 业务约束
- **用户模式**：初期仅支持单用户模式
- **部署方式**：数据必须支持本地部署
- **离线支持**：必须支持离线模式的基本功能
- **数据使用**：用户数据不得用于模型训练

### 6.3 合规约束
- **数据保护**：遵循 GDPR 数据保护规定
- **网络安全**：遵循中国网络安全法
- **用户权利**：支持用户数据导出和删除权利

### 6.4 配置约束
- **配置外部化**：所有配置必须外部化，禁止硬编码
- **环境变量**：关键配置项必须通过环境变量管理
- **配置校验**：所有配置项必须定义 Zod schema 并在加载时校验

#### 6.4.1 大模型与 embeddings 关键环境变量（最低集）
- `LLM_LLAMA_BASE_URL`
- `LLM_LLAMA_API_KEY`
- `LLM_LLAMA_MODEL_ID`
- `PROVIDER_API_KEY`
- `PROVIDER_BASE_URL`
- `PROVIDER_MODEL_ID`
- `SILICONFLOW_API_KEY`
- `SILICONFLOW_BASE_URL`
- `SILICONFLOW_EMBEDDING_MODEL`

#### 6.4.2 WeKnora（Episodic Memory）关键环境变量（最低集）
- `WEKNORA_BASE_URL`（示例：`http://weknora:8080/api/v1`）
- `WEKNORA_API_KEY`
- `WEKNORA_REQUEST_TIMEOUT_MS`
- `WEKNORA_RETRIEVAL_TOP_K`
- `WEKNORA_RETRIEVAL_THRESHOLD`（可选：SBO 侧二次过滤阈值）
- `WEKNORA_TIME_DECAY_RATE`（默认建议 0.1）
- `WEKNORA_SEMANTIC_WEIGHT`（默认建议 0.7）
- `WEKNORA_TIME_WEIGHT`（默认建议 0.3）

#### 6.4.3 真实集成原则：WeKnora 外部依赖测试与失败策略
- WeKnora 属于外部依赖服务：任何涉及 Episodic（deep 检索、文档导入、对话归档、反馈纠错）的能力都必须以真实 WeKnora 实例进行端到端验证。
- 配置缺失（例如 `WEKNORA_BASE_URL`/`WEKNORA_API_KEY`）时：
  - 若测试覆盖的链路需要 WeKnora，则测试必须失败并给出清晰错误。
  - 若运行时请求显式选择 `mode=deep` 或调用 `/episodic/*`、`/feedback`，则 API 必须返回结构化错误（`code/message`）。
- WeKnora 不可用/超时/鉴权失败时：
  - `mode=deep` 查询必须有明确策略：要么失败并返回结构化错误，要么降级为 `mode=fast` 并在响应中明确标记降级与原因（实现必须选择其一并保持一致）。
  - `/episodic/*` 与 `/feedback` 不允许静默成功；必须可观测并可审计。

## 7. 演进路线图

### 7.1 第一阶段：MVP —— 打造"懂你的备忘录"（耗时约 4 周）
**目标**：实现基础输入、Agentic 状态记忆和对话

**功能范围**：
- 采用微信小程序或轻量 Web 端接入语音/文字
- 引入 Mem0 框架接管记忆逻辑
- 后端仅使用 PostgreSQL（文本 + JSONB 存状态 + pgvector 做简单相似度检索）

**WeKnora 依赖与开关策略**：
- MVP 阶段 WeKnora 不作为 `mode=fast` 主路径硬依赖。
- `mode=deep` 作为可选开关：
  - 开启时：并发检索 Semantic Memory + WeKnora，并执行时间权重重排。
  - 关闭或 WeKnora 不可用时：必须采用一致策略（失败或降级到 fast），并保证响应可观测（明确标记失败原因或降级原因）。
- Episodic 写路径（文档/URL/对话摘要导入 WeKnora）可作为可选能力先行落地；若启用，必须具备导入作业状态可观测（queued/running/succeeded/failed）。

**舍弃功能**：
- 暂不引入复杂的知识图谱（GraphRAG）
- 暂不支持图片识别输入
- 暂不支持主动触发功能

### 7.2 第二阶段：完整形态 —— 引入关系推理（耗时约 6-8 周）
**目标**：解决复杂事件关联记忆问题

**新增功能**：
- 引入 Neo4j 和 GraphRAG 流程，让系统能够理解"人-事-物"的多级关联
- 实现图片识别输入（Vision 大模型接入）
- 完善复杂逻辑查询能力

**WeKnora 依赖与开关策略**：
- 建议默认启用 `mode=deep`（当请求被路由为“需要外部证据”时），并纳入可用性与延迟监控。
- GraphRAG/图谱增强保持开关化：
  - 优先采用 WeKnora 的 GraphRAG profile（或等价能力）。
  - 若图谱依赖不可用：deep 仍可仅使用 WeKnora 混合检索 + 时间重排运行；不得影响 `mode=fast`。
- 对话归档摘要写入 WeKnora 建议在阶段 2 进入常态化，作为长周期可检索证据来源。

### 7.3 第三阶段：全知数字伴侣 —— 被动变主动（长期）
**目标**：系统具备时间感、生物钟和主动干预能力

**新增功能**：
- 开发后台常驻的定时触发 Agent（Cron Jobs）
- 结合用户设备的日历、GPS、健康数据（如 Apple HealthKit API），主动推送提醒和建议
- 完善情境感知和主动服务能力

**WeKnora 依赖与开关策略**：
- 主动服务的触发与推荐链路可复用 WeKnora 作为“情景证据”来源（历史对话摘要/运行日志/文档片段）。
- 对 WeKnora 的调用必须具备限流与熔断策略，并在触发链路中保证“可降级不打断”。
- 若 WeKnora 不可用：主动能力应降级为仅基于 Semantic/近期 Working Memory 的保守提醒，避免输出不可验证内容。

## 8. 验收标准

### 8.1 功能验收
- 所有用户故事的验收标准必须通过
- 核心 API 接口功能完整且稳定
- 端到端测试场景全部通过
- 真实集成测试（禁止使用 mock）
- WeKnora 作为外部依赖必须纳入端到端验证：连通性/鉴权、导入、检索、超时/不可用时的失败策略或降级行为必须可验证

### 8.2 性能验收
- 性能指标达到规定要求
- 负载测试通过预期并发量
- 压力测试系统表现稳定
- 缓存命中率达到预期

### 8.3 安全验收
- 安全扫描无高危漏洞
- 渗透测试通过
- 数据加密和隔离机制有效
- 用户数据擦除功能正常

### 8.4 可用性验收
- 用户界面友好易用
- 错误处理机制完善
- 帮助文档完整准确
- 多渠道输入体验一致

### 8.5 零遗留项验收
- 所有审查问题必须 100% 修复
- 文档完整性确认（API 文档/错误码/配置项）
- 所有测试覆盖确认（单元测试/冒烟测试）
- 配置缺失时测试必须失败并记录原因
