# SecondBrainOS 实施任务列表

## 概述

基于 SecondBrainOS 需求文档和设计文档，本任务列表将系统实施分解为可执行的开发任务。采用分层记忆架构和异步巩固机制，实现无摩擦信息录入、智能记忆管理和时间感知推理。

## 全局约束与完成定义（所有任务通用）

### A. 权威约束（必须遵循）

- `raw_events` 为唯一事实源：append-only（允许软删字段）；其余派生表/索引/图谱必须可从 `raw_events` 回放重建。
- 所有对外输入输出必须契约化校验：后端 Pydantic 作为单一事实源；前端 Zod 作为单一事实源。
- 错误消息（message）必须使用英文；对外错误必须结构化（至少包含 `code`、`message`）。
- 请求追踪：本项目为非 SaaS/单机形态时不需要 `X-Request-ID`/`request_id`；如实现请求追踪则应保持端到端一致与可观测。
- embeddings/LLM 密钥仅允许在 Core/worker 持有，前端/OpenClaw 不得直接持有。
- 测试必须使用真实服务（Postgres/Redis/外部 embeddings/LLM；可选 Neo4j/GraphRAG 仅在启用 deep/图谱增强时）；配置缺失必须导致测试失败，不得跳过。
- Episodic Memory 通过 WeKnora 集成：SBO 不在 Core 内重复实现文档解析/分块/混合检索；Deep 检索通过 WeKnora 完成并返回可追溯 evidence。
- `mode=fast` 不得依赖 WeKnora；`mode=deep` 必须固定为"失败返回结构化错误"或"降级为 fast 并显式标记降级原因"二选一，并将字段结构契约化。
- `/episodic/*`（KB 管理、导入、状态查询）与 `/feedback`：不允许静默成功；失败必须返回结构化错误并落审计日志。
- 租户隔离：本项目为非 SaaS/单机单用户形态时不需要。
- 检索排序管线约束：必须实现候选召回、融合、可选 rerank、归一化过滤、时间重排、噪声过滤的完整管线。
- 可用性约束：任何上游不可用时必须降级回 Semantic/Working Memory；hardMinScore 必须在 time-decay 之前执行。
- 召回护栏约束：mustSkipRetrieval 判定必须先于 WeKnora 调用；支持 CJK 特性和可配置规则。
- Evidence 统一元数据约束：所有 evidence 必须携带标识、隔离、时间、质量、审计字段。
- Scope/Namespace 隔离约束：scope 过滤必须在检索/融合之前执行；支持 global/user/agent/project/custom 形态。
- Prompt 注入安全约束：evidence 注入时必须标记为 [UNTRUSTED DATA]；必须有数量上限和阈值控制。
- Cross-Encoder 重排约束：必须有独立超时控制；失败必须降级到 fusion；不得完全覆盖原始相关性。
- 生命周期/衰减约束：阶段 1 仅 time-decay；访问计数更新必须异步；不得破坏 raw_events 可回放原则。

### B. 每个任务的完成定义（DoD）

- 具备清晰的产出物（代码/迁移/脚本/文档/接口）。
- 同时具备并通过：
  - 单元测试（覆盖正常路径 + 关键边界 + 至少一个错误路径）。
  - 冒烟测试（端到端关键链路，连接真实服务，至少覆盖成功路径；适用时覆盖失败路径）。
- 相关配置项已外部化并可校验（环境变量缺失 -> 明确报错）。

### C. 阶段划分与里程碑（建议按开关演进）

- 阶段 1（MVP，4 周）：以 `POST /ingest` + 异步巩固 + `POST /query mode=fast` 为主路径；不强依赖 GraphRAG deep 推理/多模态/主动提醒。
- 阶段 2（关系推理，6-8 周）：引入 Neo4j 图谱扩展，落地 `mode=deep`；多模态（OCR/Vision）纳入巩固。
- 阶段 3（主动服务，长期）：定时/情境触发 agent，外部信号源（日历/GPS/健康数据）接入。

### D. 任务优先级标注（用于项目管理）

- `[P0]`：关键路径阻断项；不完成会阻塞后续大多数任务或无法形成端到端闭环。
- `[P1]`：重要项；对核心能力或质量有显著影响，但不一定阻塞最小闭环。
- `[P2]`：增强项；可延后，不影响核心链路先跑通。

## 任务列表

### 1. 环境搭建和基础设施

- [x] [P0] 1.1 项目结构初始化
  - 创建 `backend/`、`web/`、`docs/`、`reports/` 目录结构
  - 设置 Python 虚拟环境 `.venv`
  - 配置 `.gitignore` 和基础项目文件
  - _需求: 6.1, 6.4_

- [x] [P1] 1.1.1 文档变更同步检查（Spec Sync）
  - 对齐权威文档对 Episodic Memory 的最新约束（WeKnora 作为检索与理解层；Neo4j/GraphRAG 为可选增强）
  - 核对任务清单中与 WeKnora/Episodic 相关的依赖、配置与验收项是否已同步更新
  - 基础自动化校验：确认 `.venv` 存在，且 `.venv/bin/python -m compileall backend` 通过

- [x] [P0] 1.2 后端基础环境配置
  - 初始化 FastAPI 项目结构
  - 配置 Pydantic 模型和依赖管理
  - 设置 Redis Queue (RQ) 工作环境
  - 创建 `.env.example` 配置模板
  - 补充并校验 WeKnora 配置（`WEKNORA_BASE_URL`/`WEKNORA_API_KEY`/超时/检索参数/时间衰减参数等），缺失配置必须明确报错
  - _需求: 4.1.1, 6.4.1, 6.4.2_

- [x] [P1] 1.3 单元测试环境搭建
  - 配置 pytest 测试框架
  - 设置测试数据库和 Redis 实例
  - 创建测试配置和 fixtures

- [x] [P0] 1.4 数据库环境搭建
  - 配置 PostgreSQL + pgvector 扩展
  - 配置 Redis 缓存和队列
  - 验证所有数据库连接
  - _需求: 4.1.1, 5.2_

- [x] [P1] 1.5 集成测试环境验证
  - 验证 Postgres + pgvector 连通性
  - 验证 Redis 缓存和队列功能

- [x] [P0] 1.5.1 WeKnora 连通性与鉴权验证
  - 验证 WeKnora REST API 连通性（Base URL + API Key）
  - （可选）若实现请求追踪：验证请求可携带 `X-Request-ID`
  - _需求: 3.2.4, 6.4.2_

- [x] [P1] 1.5.2 WeKnora KnowledgeBase 管理最小闭环验证
  - 验证 KnowledgeBase 的创建/列出/选择（以 WeKnora API 为准）
  - 验证按 KnowledgeBase/Tag 的隔离与范围控制（如启用）
  - _依赖: 1.5.1_

- [x] [P2] 1.6 本地开发与验证命令基线
  - 约定并固化基础验证命令（后端/前端）
  - 后端最低校验：`python -m compileall backend`
  - 后端单元测试：`pytest -q`
  - 后端冒烟测试：提供 `backend/scripts/*_smoke_test.py`（连接真实 Postgres/Redis 与外部 embeddings/LLM；可选验证 deep/图谱增强依赖）
  - 前端构建：`npm run build`（在 `web/` 目录）
  - _需求: 8.1, 5.6, 6.1_

### 2. 数据库设计和迁移

- [x] [P0] 2.1 PostgreSQL 数据模型设计
  - 设计 `raw_events` 表（事实源）
  - 设计 `extractions` 表（结构化提取）
  - 设计 `user_profiles` 表（当前态 + 历史版本）
  - 设计 `embeddings` 表（pgvector 索引）
  - _需求: 3.6.1, 3.6.2, 3.6.3_

- [x] [P0] 2.2 数据库迁移脚本
  - 使用 Alembic 创建迁移管理
  - 实现 upgrade/downgrade 脚本
  - 添加必要的索引和约束
  - _需求: 5.3.2_

- [x] [P1] 2.2.1 迁移可回滚性验证（强制）
  - 验证 `upgrade -> downgrade -> upgrade` 循环成功
  - 将验证步骤纳入冒烟测试脚本或 CI 任务
  - _需求: 5.3.2_

- [x] [P2] 2.3 数据模型单元测试
  - 测试 Pydantic 模型验证
  - 测试数据库约束和索引
  - 测试迁移脚本的可回滚性

- [x] [P1] 2.4 Neo4j 图谱模型设计
  - 设计节点类型（Person、Event、Location、Thing）
  - 设计关系类型（参与、发生于、关联、认识）
  - 实现按 user_id 的子图隔离
  - _需求: 3.2.3, 5.2_

- [ ] [P2] 2.4.1 阶段性开关：Neo4j/GraphRAG 可选增强（非 MVP 硬依赖）
  - 将 Neo4j 相关能力纳入 `mode=deep` 的可用性探测与降级策略
  - 确保 `mode=fast` 在仅 Postgres/Redis 可用时仍可工作
  - _需求: 5.6_

- [x] [P1] 2.5 图数据库集成测试
  - 测试节点和关系的 CRUD 操作
  - 测试 user_id 隔离机制
  - 测试图谱查询性能

- [x] [P2] 2.6 擦除作业与审计数据模型
  - 为 `POST /forget` / `GET /forget/{erase_job_id}` 设计持久化表（例如 erase_jobs、erase_job_items）
  - 记录作业状态流转（queued/running/succeeded/failed）、影响范围摘要与错误信息
  - _需求: 3.1.3, 5.2_

### 3. 核心 API 开发

- [x] [P0] 3.1 FastAPI 应用框架
  - 创建 FastAPI 应用实例
  - 配置 CORS 和中间件
  - 实现统一错误处理
  - 添加请求日志和监控
  - （可选）请求追踪：如实现 `X-Request-ID` 透传/生成，应保证端到端一致与可观测
  - _需求: 3.1_

- [x] [P1] 3.1.1 结构化错误码与响应契约
  - 定义全局错误码枚举与错误响应模型（`code/message`）
  - 为每个端点明确可能错误码（参数校验/鉴权失败/上游不可用/超时/依赖不可用）
  - _需求: 5.5, 6.4_

- [x] [P1] 3.1.2 外部依赖失败/降级策略契约化（统一门禁）
  - 固化 `mode=deep` 对 WeKnora 不可用/超时/鉴权失败时的策略（二选一：失败/降级）并形成响应字段契约
  - `mode=fast` 明确禁止调用 WeKnora（实现与测试双门禁）
  - _依赖: 3.1.1_

- [x] [P0] 3.2 数据录入接口实现
  - 实现 `POST /ingest` 接口基础框架
  - 实现 `POST /chat` 接口基础框架
  - 实现 `POST /upload` 接口基础框架
  - 添加幂等性支持
  - _需求: 3.1.1, 2.1.1, 2.1.2_

- [x] [P1] 3.2.1 数据录入接口业务逻辑实现
  - 实现数据录入的完整业务流程
  - 实现文件上传的处理逻辑
  - 实现对话交互的处理逻辑
  - _依赖: 3.2_

- [x] [P1] 3.2.2 写入"快确认"与异步入队的硬性门禁
  - 明确 `POST /ingest` 与 `POST /chat` 必须先落 `raw_events` 再入队、再返回
  - 证明不会被抽取/embedding/图谱写入阻塞（与性能指标对齐）
  - _需求: 3.4.1, 5.1_

- [x] [P2] 3.3 数据录入接口单元测试
  - 测试输入验证和错误处理
  - 测试幂等性机制
  - 测试异步任务入队

- [x] [P0] 3.4 查询检索接口实现
  - 实现 `POST /query` 接口
  - 实现多路召回机制（fast/deep 模式）
  - 实现 `GET /memories` 接口
  - 实现 `GET /conversations/{id}/messages` 接口
  - _需求: 3.1.2, 2.3.1_

- [x] [P1] 3.4.3 检索排序管线实现（统一抽象，agent-agnostic）
  - 实现候选召回（可并行）：Semantic + Episodic + （可选）Graph
  - 实现融合（fusion）：dense 为主，lexical/BM25 保底
  - 实现可选 rerank（cross-encoder）：失败必须降级到 fusion 结果
  - 实现归一化与过滤：length normalization + hardMinScore
  - 实现时间与生命周期重排：time-decay / recency boost
  - 实现噪声过滤与多样性：noise filter + MMR diversity
  - _需求: 3.1.2, 设计文档检索排序管线_

- [x] [P1] 3.4.4 查询可用性与顺序约束实现
  - 实现任何上游不可用时的降级策略（至少走 Semantic/Working Memory 回退路径）
  - 确保 hardMinScore 发生在 time-decay/lifecycle 之前
  - 实现符号型查询保底策略（对高置信 lexical 命中设置 preservation floor）
  - 确保 evidence[] 携带关键评分信息（final_score；推荐 dense/bm25/rerank_score）
  - _需求: 3.1.2, 设计文档可用性约束_

- [x] [P1] 3.4.5 shouldSkipRetrieval 召回护栏实现
  - 实现护栏判定逻辑（先于 WeKnora 调用）
  - 配置跳过 Deep Retrieval 的典型输入（问候语/寒暄/简单确认/emoji/命令）
  - 配置强制 Deep Retrieval 的典型输入（记得/之前/上次/回顾/根据文档/查历史等）
  - 实现 CJK 特性（中文短 query 独立策略）
  - 实现可配置规则（阈值、关键词列表、最短长度）
  - _需求: 5.6, 设计文档召回护栏_

- [x] [P0] 3.4.2 WeKnora Episodic 检索对接（Deep Mode）
  - 实现 WeKnora HTTP client（超时/重试/错误映射）
  - 实现按 KnowledgeBase/Tag 的范围检索策略（项目/密级/时间）
  - Deep 模式必须并发检索 Semantic Memory + WeKnora，并统一输出 evidence
  - 实现 Time-Decay Re-ranking（二次重排：`final_score = semantic_score * semantic_weight + exp(-decay_rate * days_ago) * time_weight`）
  - 对 WeKnora 失败执行统一策略（失败或降级），并确保可观测（响应字段 + 结构化日志）
  - _需求: 3.2.4, 6.4.2_

- [x] [P1] 3.4.1 Evidence 证据模型与护栏实现
  - 明确定义 `evidence[]` 字段：`evidence_id/type/text/occurred_at/source/confidence/refs`
  - 实现阈值过滤（按 `confidence`）与 top-N 裁剪（建议 3~8）
  - 实现短窗口缓存复用（同会话/相近 query）
  - _需求: 5.6, 3.4.2_

- [x] [P2] 3.5 查询检索接口单元测试
  - 测试查询参数验证
  - 测试证据召回和排序
  - 测试时间范围过滤

- [x] [P1] 3.6 管理接口实现
  - 实现 `POST /forget` 接口
  - 实现 `GET /forget/{erase_job_id}` 接口
  - 实现 `GET /profile` 和 `PUT /profile` 接口
  - 实现 `GET /health` 接口
  - _需求: 3.1.3, 2.2.1, 5.1_

- [x] [P1] 3.6.2 结构化审计日志（范围对齐设计约束）
  - `POST /forget` 与擦除作业执行：记录影响范围摘要
  - `PUT /profile`：记录变更摘要与触发来源
  - `POST /feedback`：记录 evidence 标识、反馈类型与可选 session_id（若有）
  - 对外部依赖（WeKnora/embeddings/LLM provider）调用结果：成功/失败/降级
  - 检索与重排审计：记录 rerank 执行状态、provider/model/version、降级原因
  - Prompt 注入安全审计：记录不可信数据标记和注入数量
  - _依赖: 3.1, 3.1.1_

- [x] [P1] 3.6.3 Episodic 管理接口（WeKnora 透传/编排）
  - 实现 `POST /episodic/knowledge-bases` / `GET /episodic/knowledge-bases`
  - 实现 `POST /episodic/ingestions` / `GET /episodic/ingestions/{ingestion_job_id}`（异步导入 + 状态可观测）
  - 失败不得静默成功；必须返回结构化错误并落审计日志
  - _依赖: 1.5.1, 3.1.1_

- [x] [P1] 3.6.4 反馈纠错接口实现
  - 实现 `POST /feedback` 接口（支持关联 WeKnora chunk/knowledge 引用）
  - 支持反馈类型：incorrect/outdated/incomplete
  - 支持可选用户纠正文本（user_correction）
  - 记录审计字段（时间、evidence 标识、session_id、来源）
  - 实现影响策略（对 incorrect/outdated 证据降权或过滤）
  - 外部依赖失败时返回结构化错误（不得静默成功）
  - _需求: 2.2.3, 设计文档反馈纠错_

- [x] [P2] 3.6.1 /health 指标化输出与告警友好结构
  - 返回 Postgres/Redis/Neo4j 连通性
  - 返回队列积压（长度/延迟）等可用于告警的指标级信息
  - _需求: 5.3.1_

- [x] [P2] 3.7 管理接口单元测试
  - 测试记忆擦除功能
  - 测试用户档案管理
  - 测试健康检查机制

### 4. 异步任务处理

- [ ] [P1] 4.1 Redis Queue 工作框架
  - 配置 RQ worker 和队列管理
  - 实现任务失败重试机制
  - 添加任务监控和日志
  - _需求: 3.3.1_

- [ ] [P1] 4.1.2 Cross-Encoder 重排任务实现
  - 实现 rerank 任务（独立超时与并发控制）
  - 确保重排失败时降级回 fusion 排序
  - 记录降级原因（timeout/5xx）到审计日志
  - 实现混合评分（rerank 分数加权融合，不完全覆盖原始相关性）
  - 实现符号查询保护（对高 BM25/lexical 命中设置保底阈值）
  - _需求: 设计文档 Cross-Encoder 重排策略_

- [x] [P1] 4.1.3 生命周期/衰减任务实现
  - 阶段 1：实现 time-decay re-ranking（简单、可解释）
  - 实现访问计数/最后访问时间的异步更新（避免热路径延迟）
  - 确保生命周期字段不破坏 raw_events 可回放原则
  - 为阶段 2（access_count/last_accessed_at 强化衰减）预留接口
  - _需求: 设计文档生命周期/衰减约束_

- [ ] [P1] 4.1.1 对话归档（摘要）写入 WeKnora（异步）
  - 定义归档触发条件（会话结束/阈值/关键事件等）
  - 生成结构化摘要（背景/问题/关键事实/结论/决策/证据）并作为 Knowledge 写入 WeKnora
  - 记录导入作业状态（成功/失败/重试）并可观测
  - _依赖: 4.1, 5.4.2_

- [ ] [P2] 4.2 事件巩固任务实现
  - 实现 `consolidate_event(event_id)` 任务
  - 实现结构化信息抽取
  - 实现实体和关系识别
  - _需求: 3.3.1, 3.4.1_

- [ ] [P2] 4.3 事件巩固任务单元测试
  - 测试信息抽取准确性
  - 测试任务失败处理
  - 测试重试机制

- [ ] [P1] 4.4 用户档案更新任务
  - 实现 `upsert_profile(extraction_id)` 任务
  - 实现记忆冲突检测和解决
  - 实现档案版本化管理
  - _需求: 2.2.1, 3.4.1_

- [ ] [P2] 4.5 档案更新任务单元测试
  - 测试冲突检测逻辑
  - 测试版本化机制
  - 测试历史记录归档

- [ ] [P1] 4.6 向量嵌入任务实现
  - 实现 `embed_event(event_id)` 任务
  - 集成 SiliconFlow embeddings API
  - 实现失败不阻塞策略
  - 支持批量重跑机制
  - _需求: 3.5, 4.1.2_

- [ ] [P2] 4.6.1 embeddings 回放重建与审计
  - 提供从 `raw_events` 批量回放重跑 embeddings 的作业入口与脚本
  - 记录每次回放的范围、结果与失败原因，确保可审计
  - _需求: 3.5.2_

- [ ] [P2] 4.7 向量嵌入任务单元测试
  - 测试 embeddings API 集成
  - 测试失败处理机制
  - 测试批量重跑功能

- [ ] [P1] 4.8 图谱更新任务实现
  - 实现 `upsert_graph(extraction_id)` 任务
  - 实现 Neo4j 节点和关系 MERGE
  - 添加 source_event_id 和时间戳
  - _需求: 3.3.1_

- [ ] [P2] 4.9 图谱更新任务单元测试
  - 测试图谱节点创建和更新
  - 测试关系建立和维护
  - 测试数据溯源机制

### 5. 分层记忆架构实现

- [ ] [P1] 5.1 工作记忆实现
  - 实现 Context Window 管理
  - 实现 Prompt Caching (CAG)
  - 优化近期对话上下文存储
  - _需求: 3.2.1_

- [ ] [P2] 5.2 语义记忆实现
  - 集成 Mem0 框架
  - 实现用户事实和偏好存储
  - 实现约束条件管理
  - _需求: 3.2.2_

- [ ] [P2] 5.3 语义记忆单元测试
  - 测试 Mem0 集成
  - 测试事实和偏好管理
  - 测试约束条件验证

- [ ] [P1] 5.4 情景记忆实现
  - 对接 WeKnora：KnowledgeBase 管理、知识导入、混合检索（BM25 + Dense）
  - Deep 模式下并发检索 Semantic Memory + WeKnora，并统一输出 evidence
  - _需求: 3.2.3, 3.2.4_

- [ ] [P2] 5.4.3 反馈纠错闭环（Episodic 证据自我修正）
  - 提供 `POST /feedback`（或等价能力）记录用户对证据的 incorrect/outdated/incomplete 反馈
  - 检索侧对已标记证据进行降权或过滤（行为必须一致且可测）
  - `incorrect/outdated` 必须确定性地“降低权重或排除”二选一，并证明不会在证据链中高频重复出现
  - _依赖: 3.4.2, 3.4.1_

- [ ] [P2] 5.4.1 阶段性开关：MVP 不强依赖 deep 图谱
  - 在配置层提供 `mode=deep` 可用性开关与依赖探测（Neo4j 不可用时明确降级）
  - 保证 `mode=fast` 在仅 Postgres/Redis 可用时仍可工作
  - _需求: 5.6_

- [ ] [P1] 5.4.2 Episodic 写路径：文档/URL/对话摘要导入 WeKnora
  - 创建/选择 KnowledgeBase
  - 上传文件或提交 URL，并绑定 Tag（项目/来源/密级/时间戳）
  - 记录导入作业状态（成功/失败/重试）并可观测
  - _需求: 3.2.4_

- [ ] [P2] 5.5 情景记忆集成测试
  - 测试 WeKnora 文档导入（文件/URL/对话摘要）与作业状态可观测
  - 测试 WeKnora 混合检索（BM25 + Dense）在 Deep 模式下可用，并返回可追溯引用
  - 测试 Time-Decay Re-ranking（近期内容优先）
  - （可选）启用 WeKnora GraphRAG profile 后的增强检索效果与性能

### 6. 多模态输入处理

- [ ] [P2] 6.1 语音输入处理
  - 实现语音转录功能
  - 集成语音识别 API
  - 实现噪音环境优化
  - _需求: 2.1.1_

- [ ] [P2] 6.2 图片输入处理
  - 实现 OCR 文字提取
  - 实现图片信息抽取
  - 支持多种图片格式
  - _需求: 2.1.2_

- [ ] [P2] 6.3 多模态输入单元测试
  - 测试语音转录准确性
  - 测试 OCR 识别准确性
  - 测试图片信息抽取

- [ ] [P2] 6.4 多模态能力分阶段落地
  - MVP 阶段明确：`POST /upload` 可先实现文件落库 + 异步 OCR/抽取入队（不阻塞快确认）
  - 阶段 2 再补齐 Vision/OCR 质量指标与结构化抽取覆盖
  - _需求: 7.1, 7.2_

### 7. 前端开发

- [ ] [P2] 7.1 前端项目初始化
  - 创建 Vite + React + TypeScript 项目
  - 配置 Tailwind CSS
  - 从 zip/ 原型迁移 UI 组件
  - _需求: 4.1.3_

- [ ] [P2] 7.2 核心组件开发
  - 迁移和优化 Chat.tsx 组件
  - 迁移和优化 Sidebar.tsx 组件
  - 迁移和优化 ErrorBoundary.tsx 组件
  - _需求: 4.1.3_

- [ ] [P2] 7.3 前端组件单元测试
  - 测试 Chat 组件交互
  - 测试 Sidebar 组件功能
  - 测试错误边界处理

- [ ] [P2] 7.4 API 客户端实现
  - 实现统一 API 客户端
  - 配置鉴权和错误处理
  - 实现重试和超时机制
  - _需求: 4.1.3_
- [ ] [P2] 7.5 前端状态管理实现
  - 实现 Memory、Message、Evidence 状态模型
  - 配置 Zod 数据验证
  - 实现状态持久化
  - _需求: 3.6.4_

- [ ] [P2] 5.5.1 Evidence 统一元数据模型实现
  - 实现标识字段：evidence_id、type、refs
  - 实现隔离字段：user_id、project_id、scope（global/user/agent/project/custom）
  - 实现时间字段：occurred_at（优先）、created_at（次之）
  - 实现质量字段：confidence、scores（dense/bm25/rerank/final）
  - 实现审计字段：request_id、retrieval_trace（可选）
  - _需求: 3.6.4, 设计文档 Evidence 统一元数据规范_

- [ ] [P2] 5.5.2 Scope/Namespace 隔离实现
  - 实现统一 scope 形态（global、user:<user_id>、agent:<agent_id>、project:<project_id>、custom:<name>）
  - 实现硬隔离（scope 过滤在检索/融合之前执行）
  - 确保所有 evidence 携带 user_id/project_id 与 scope
  - 实现二次校验（多用户/多租户形态的外部系统结果校验）
  - _需求: 5.2, 设计文档 Scope/Namespace 隔离模型_

- [ ] [P2] 5.5.3 Prompt 注入安全实现
  - 实现不可信数据标记（[UNTRUSTED DATA]）
  - 实现注入数量控制（top-N 上限与阈值过滤）
  - 实现可配置的注入规则
  - _需求: 5.2, 设计文档 Prompt 注入安全约束_

- [ ] [P2] 7.5.1 前端契约与错误处理一致性
  - 以 Zod 定义所有 API 响应/错误响应 schema，并从 schema 推导类型
  - 统一展示 evidence（时间/来源/置信度/引用跳转）
  - _需求: 3.6.4, 5.5_
  
- [ ] [P2] 7.6 前端集成测试
  - 测试 API 客户端集成
  - 测试状态管理功能
  - 测试用户交互流程

### 8. 大模型集成

- [ ] [P2] 8.1 本地模型集成
  - 集成 DeepSeek V3/Llama-3 本地推理
  - 配置 llama.cpp 环境
  - 实现模型路由逻辑
  - _需求: 4.1.2_

- [ ] [P2] 8.2 外部模型集成
  - 集成 DeepSeek R1/Claude 3.5 Sonnet
  - 实现复杂推理调用
  - 配置 API 密钥管理
  - _需求: 4.1.2_

- [ ] [P2] 8.3 模型集成单元测试
  - 测试本地模型调用
  - 测试外部模型集成
  - 测试模型路由逻辑

### 9. 时间感知和主动服务

- [ ] [P2] 9.1 时间感知查询实现
  - 实现相对时间解析
  - 实现时间范围查询
  - 优化时间戳处理
  - _需求: 2.2.2, 2.3.1_

- [ ] [P2] 9.1.1 时区与相对时间一致性测试
  - 覆盖“昨天/上周/上个月”等相对时间在不同时区下的解析与过滤
  - _需求: 2.2.2_

- [ ] [P2] 9.2 主动提醒机制
  - 实现基于时间的提醒
  - 实现基于情境的提醒
  - 配置提醒规则管理
  - _需求: 2.3.2_

- [ ] [P2] 9.3 时间感知功能单元测试
  - 测试时间解析准确性
  - 测试提醒触发机制
  - 测试规则配置功能

### 10. 安全和权限管理

- [ ] [P2] 10.1 鉴权机制实现
  - 实现 Bearer Token 鉴权
  - 配置 OpenClaw 集成鉴权
  - 实现会话管理
  - _需求: 5.2_

- [ ] [P2] 10.2 租户隔离实现
  - 单机单用户形态不需要（可移除或不实现）

- [ ] [P2] 10.3 安全机制单元测试
  - 测试鉴权机制
  - 测试数据隔离
  - 测试权限控制

- [ ] [P2] 10.4 审计日志与关键操作留痕
  - 对 ingest/query/forget/profile 更新等关键操作记录结构化审计日志
  - 审计日志需包含影响范围摘要
  - _需求: 5.2_

### 11. 性能优化和缓存

- [ ] [P2] 11.1 缓存机制实现
  - 实现查询结果缓存
  - 实现会话上下文缓存
  - 优化缓存命中率
  - _需求: 5.1_

- [ ] [P2] 11.2 性能监控实现
  - 实现响应时间监控
  - 实现队列积压监控
  - 配置性能告警
  - _需求: 5.1, 5.3.1_

- [ ] [P2] 11.3 性能优化单元测试
  - 测试缓存机制效果
  - 测试性能监控准确性
  - 测试告警触发机制

### 12. 集成测试和端到端测试

- [ ] [P0] 12.1 API 集成测试
  - 测试完整的数据录入流程
  - 测试查询检索端到端流程
  - 测试记忆擦除功能
  - _需求: 8.1_

- [ ] [P0] 12.1.1 端到端冒烟测试脚本（真实服务，强制）
  - 覆盖链路：`POST /ingest` -> RQ 入队 -> worker 巩固 -> `POST /query` 返回 evidence
  - 覆盖链路：`POST /forget` -> `GET /forget/{erase_job_id}` -> 影响范围可观测
  - 覆盖失败路径：依赖不可用（例如 Neo4j/embeddings）时的降级/不阻塞策略
  - 覆盖 WeKnora：连通性/鉴权校验、导入（文件/URL/对话摘要至少一种）、导入状态可观测、Deep 检索返回可追溯 evidence
  - 覆盖 WeKnora 失败路径：WeKnora 超时/不可用/鉴权失败时的失败或降级策略（必须与实现选择一致）
  - _需求: 8.1, 3.5.2, 5.6_

- [ ] [P2] 12.2 异步任务集成测试
  - 测试事件巩固完整流程
  - 测试记忆冲突解决
  - 测试图谱构建过程
  - _需求: 8.1_

- [ ] 12.3 前后端集成测试
  - 测试前端与 API 的完整交互
  - 测试实时更新和状态同步
  - 测试错误处理和恢复
  - _需求: 8.1_

- [ ] 12.4 性能压力测试
  - 测试并发用户支持
  - 测试大数据量处理
  - 测试系统稳定性

### 13. 部署和运维

- [ ] 13.1 容器化部署
  - 创建 Docker 配置文件
  - 配置 docker-compose 编排
  - 实现环境变量管理
  - _需求: 5.3_

- [ ] 13.2 数据备份和恢复
  - 实现 PostgreSQL 备份策略
  - 实现 Neo4j 备份或重建策略
  - 配置定期备份任务
  - _需求: 5.3.3_

- [ ] 13.3 部署验证测试
  - 测试容器化部署
  - 测试备份恢复功能
  - 测试环境配置

- [ ] 13.4 监控和日志
  - 配置系统监控
  - 实现结构化日志
  - 配置告警机制
  - _需求: 5.5_

### 14. 文档和用户指南

- [ ] 14.1 API 文档编写
  - 编写完整的 API 文档
  - 包含所有端点和错误码
  - 提供使用示例
  - _需求: 5.5_

- [ ] [P2] 14.1.1 环境变量与配置校验文档
  - 列出最低环境变量集（LLM/Provider/Embeddings/DB/Redis/Neo4j）与用途
  - 必须包含 WeKnora 环境变量最低集与用途（`WEKNORA_BASE_URL`/`WEKNORA_API_KEY`/`WEKNORA_REQUEST_TIMEOUT_MS`/`WEKNORA_RETRIEVAL_TOP_K`/`WEKNORA_TIME_DECAY_RATE`/`WEKNORA_SEMANTIC_WEIGHT`/`WEKNORA_TIME_WEIGHT` 等）
  - 明确"缺少配置 -> 测试失败"的策略
  - 检索排序管线配置：RETRIEVAL_TOP_K、HARD_MIN_SCORE、TIME_DECAY_RATE、SEMANTIC_WEIGHT、TIME_WEIGHT、NOISE_FILTER_THRESHOLD、MMR_DIVERSITY_THRESHOLD
  - 召回护栏配置：SKIP_RETRIEVAL_MIN_LENGTH、SKIP_RETRIEVAL_KEYWORDS、FORCE_RETRIEVAL_KEYWORDS、CJK_MIN_LENGTH_THRESHOLD
  - Cross-Encoder 配置：RERANK_PROVIDER_URL、RERANK_API_KEY、RERANK_MODEL、RERANK_TIMEOUT_MS、RERANK_WEIGHT、LEXICAL_PRESERVATION_FLOOR
  - Prompt 注入安全配置：EVIDENCE_INJECTION上限、EVIDENCE_CONFIDENCE_THRESHOLD、UNTRUSTED_DATA_MARKER
  - Scope/Namespace 配置：DEFAULT_SCOPE、ENABLE_MULTI_TENANT、SCOPE_ISOLATION_STRICT_MODE
  - _需求: 6.4.1_

- [ ] 14.2 部署文档编写
  - 编写部署指南
  - 包含环境配置说明
  - 提供故障排除指南
  - _需求: 5.5_

- [ ] 14.3 用户使用文档
  - 编写用户操作指南
  - 包含功能使用说明
  - 提供最佳实践建议
  - _需求: 5.5_

### 15. 最终验收和优化

- [ ] 15.1 系统整体验收
  - 验证所有功能需求
  - 验证性能指标达标
  - 验证安全要求满足
  - _需求: 8.1, 8.2, 8.3_

- [ ] 15.2 用户体验优化
  - 优化界面交互体验
  - 优化响应速度
  - 完善错误提示
  - _需求: 8.4_

- [ ] 15.3 最终回归测试
  - 执行完整回归测试套件
  - 验证所有功能正常
  - 确认性能指标达标

- [ ] 15.4 生产环境准备
  - 配置生产环境
  - 执行生产部署
  - 验证生产环境功能
  - _需求: 8.1_

## 注意事项

- 标记 `*` 的任务为可选测试任务，可根据项目进度调整
- 每个任务都包含明确的验收标准和需求引用
- 任务间存在依赖关系，需按顺序执行
- 所有配置必须外部化，禁止硬编码
- 必须使用真实服务进行集成测试，禁止使用 mock
- 遵循零遗留项原则，所有问题必须在任务完成前解决

