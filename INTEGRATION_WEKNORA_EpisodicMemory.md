# SecondBrainOS × WeKnora 分层记忆集成方案（Episodic Memory）

## 1. 目标与范围

### 1.1 目标

- 明确 WeKnora 与 SecondBrainOS（SBO）在**分层记忆架构**中的职责边界。
- 让 WeKnora 承担 **Episodic Memory 的“检索与理解层”**：文档解析、分块、索引、混合检索、GraphRAG 增强。
- 让 SBO 保留：
  - **Working Memory**：上下文构建、缓存、路由（热路径、低延迟）。
  - **Semantic/Agentic Memory**：结构化事实/偏好表（真值层、可演化）。
  - **Orchestration**：何时查询 WeKnora、何时写入 WeKnora、何时归档/摘要、如何做权限/隔离/审计。

### 1.2 非目标（不做什么）

- 不把 WeKnora 作为 Working Memory 的缓存层（不负责 prompt caching / CAG / 近期会话热路径）。
- 不把 WeKnora 作为 Semantic Memory 的真值存储（结构化事实以 SBO 的数据库为准）。
- 本方案不强制规定具体 LLM Provider；只规定对接接口与策略。

---

## 2. 总体架构与责任边界

### 2.1 组件职责

#### 2.1.1 WeKnora（Episodic Memory 检索与理解层）

- **文档解析与理解**：PDF/Word/图片 OCR/Caption 等解析为结构化内容。
- **分块与索引**：chunk 管理、向量化、关键词索引。
- **检索**：BM25 + Dense Retrieve + GraphRAG（可选）等混合策略。
- **知识组织**：知识库（FAQ/文档）、标签、组织/共享（如启用）。
- **对外能力**：
  - REST API（`/api/v1`）：SBO 通过 HTTP Client 直接调用。
  - 可选：WeKnora 自带 chat/agent 能力（SBO 可选择“直接用”或“只用检索结果自己生成”）。

#### 2.1.2 SBO Working Memory（热路径）

- 会话上下文拼装（窗口管理、裁剪、引用注入）。
- 近期对话缓存/临时态（Redis 等）。
- Prompt 模板与路由（快模型/慢模型/多模态）。

#### 2.1.3 SBO Semantic/Agentic Memory（真值层）

- 结构化用户事实、偏好、状态、长期目标与约束。
- 事实写入与更新策略（冲突合并、覆盖、撤销、审计）。
- 对外提供稳定的 schema（SBO 自己定义，避免漂移）。

#### 2.1.4 SBO Orchestration（编排层）

- 决策：
  - 哪些请求需要查 WeKnora（Episodic）
  - 哪些信息需要写入 Semantic（结构化）
  - 哪些内容适合写入 WeKnora（文档化/事件化归档）
  - 何时触发“摘要归档”（把多轮对话/事件压缩后入库）
- 权限与隔离：单机单用户形态不需要；如未来演进为多用户/多租户，再引入多租户、组织共享边界与知识库级访问控制。
- 可观测性：请求追踪（Request-ID）、检索命中、生成质量指标。

---

## 3. 核心数据对象与映射

> 这里不强制 WeKnora 内部表结构，仅规定 SBO 与 WeKnora 的“对接语义”。

单机单用户形态说明：
- `user_id` 在隔离意义上可以视为常量（可由后端默认补齐），主要用于审计、回放与未来演进一致性。
- `agent_id` 表示入口/执行体（例如不同渠道 bot、不同自动化 agent），语义上不等同于 `user_id`。

### 3.1 SBO 内部对象（建议）

- `ConversationSession`：会话元数据、参与者、上下文策略。
- `SemanticFact`：结构化事实（key/value/类型/来源/置信度/版本）。
- `EpisodicArtifact`：情景记忆载体（文档、会议纪要、日志切片、事件摘要等）。
- `EpisodicIngestionJob`：导入任务（状态、失败原因、重试策略）。

### 3.2 WeKnora 对接对象

- `KnowledgeBase`：知识库（文档型/FAQ 型），可视为 Episodic 的“命名空间”。
- `Knowledge`：知识条目（文件、URL、在线录入等）。
- `Chunk`：分块内容，承载检索最小单元。
- `Tag`：标签，建议用于“业务域/项目/时间范围/密级/来源系统”。
- （可选）`Organization/Tenant`：单机单用户形态不需要；如未来演进为多用户/多租户，用于多租户/共享（以 WeKnora API 为准）。

### 3.3 映射建议

- 单机单用户形态：可不启用 WeKnora 多租户能力；默认使用单一空间/知识库命名空间。
- 如未来演进为多用户/多租户：每个 SBO 租户/用户空间 -> WeKnora 一个 `Tenant/Organization`（若你启用 WeKnora 多租户能力）。
- 每个 SBO 业务域（如“项目A”“法律库”“运行日志”）-> WeKnora 一个 `KnowledgeBase`。
- SBO 的 `EpisodicArtifact` -> WeKnora `Knowledge`（文档/URL/FAQ 条目）。

---

## 4. 关键链路与数据流

### 4.1 读路径（问答/总结）

#### 4.1.1 普通问答（推荐默认策略）

1. SBO 接收用户请求。
2. Working Memory 构建当前上下文（最近对话 + 必要的 Semantic Facts）。
3. Orchestration 判定是否需要 Episodic 检索：
   - 触发条件例：问题包含“根据文档/历史/会议纪要/制度/日志”等意图；或模型路由判断为“需要外部证据”。
4. 调用 WeKnora **检索接口**获取候选 chunk/文档片段（混合检索 + 可选 GraphRAG）。
5. SBO 将检索片段（附带来源元数据）注入 prompt。
6. SBO 选择模型（快/慢/多模态）生成答案。
7. 输出：答案 + 引用（若你需要可追溯证据链）。

#### 4.1.2 检索模式分级（性能优化）

为避免每次对话都调用 WeKnora 增加延迟（500ms-1s），建议引入两种检索模式：

- **Fast Mode（仅语义）**：
  - 仅查询 SBO 内部的 Semantic Memory（基于 Mem0 或 Postgres）
  - 适用：身份类问题（"我叫什么？"）、偏好查询、日常寒暄
  - 延迟目标：<100ms

- **Deep Mode（语义 + Episodic）**：
  - 并发查询 Semantic Memory 和 WeKnora
  - 适用："去年那个项目是怎么回事？"、"根据文档..."、"回顾会议..."
  - 延迟目标：<1.5s

触发策略：
- Orchestration 根据意图识别自动选择模式
- 用户可显式指定（例如："深度检索：XXX"）

#### 4.1.3 时间权重排序（Time-Decay Re-ranking）

WeKnora 的默认向量检索仅考虑语义相关性，不考虑时间距离。建议在 SBO 侧增加重排：

- **实现**：
  1. 从 WeKnora 获取 chunk 时，同时获取 `occurred_at` 或 `created_at` 时间戳
  2. 根据时间衰减函数计算权重：`time_weight = exp(-decay_rate * days_ago)`
  3. 最终分数 = `semantic_score * semantic_weight + time_weight * time_weight_factor`

- **配置建议**：
  - `WEKNORA_TIME_DECAY_RATE`：衰减速率（默认 0.1，即 10 天后权重降至 37%）
  - `WEKNORA_SEMANTIC_WEIGHT`：语义分数权重（默认 0.7）
  - `WEKNORA_TIME_WEIGHT`：时间权重（默认 0.3）

- **理由**：情景记忆中，"近期的事实"通常比"远期的事实"更有参考价值。

#### 4.1.4 Agent 模式（可选）

- SBO 的 Agent（ReAct）可通过 REST API 将 WeKnora 当作工具：
  - 工具1：知识库检索（调用 knowledge-search API）
  - 工具2：文档片段展开（调用 chunk API）
  - 工具3：网络搜索（若 WeKnora 启用 web-search）
- 实现：SBO 在 Agent 工具层封装 WeKnora REST API 调用。
- 适用：需要多次迭代、跨知识库、跨工具推理的任务（如“做一份全面报告”）。

### 4.2 写路径（Episodic Ingestion）

#### 4.2.1 文档/URL 导入

1. SBO 产生 `EpisodicArtifact`（文件、URL、外部系统导出的内容）。
2. SBO 调用 WeKnora 知识导入 API：
   - 创建/选择 KnowledgeBase
   - 上传文件或提交 URL
   - 绑定标签（项目、来源、密级、时间戳、作者等）
3. WeKnora 解析（docreader）-> 分块 -> 向量化 -> 索引。
4. SBO 轮询/订阅导入任务状态（按 WeKnora 能力选择）。
5. SBO 记录 `EpisodicIngestionJob`：
   - 成功：写入 WeKnora knowledgeId、chunk 统计、可检索时间。
   - 失败：记录错误码/错误信息/重试次数。

#### 4.2.2 对话归档（摘要入库）

> 目标：将大量对话压缩成可检索的“事件摘要”，进入 Episodic。

- 触发条件建议：
  - 会话结束（显式结束或长时间无交互）
  - 达到阈值（消息数、token 数、时间跨度）
  - 发生关键事件（决策、结论、TODO 归零后的最终方案、事故复盘等）

- 归档策略建议：
  1. SBO 先把本会话抽取为结构：背景/问题/关键事实/结论/决策/证据/后续动作（若你允许出现动作项）。
  2. 将摘要作为“文档”写入 WeKnora（一个 knowledge 条目），并打上标签：
     - `type:conversation_summary`
     - `session_id:<id>`
     - `date:YYYY-MM-DD`
     - `project:<name>`
  3. 原始对话仍由 SBO 自己保存（Working/Episodic 的事实源策略由你决定）。

### 4.3 Semantic 写入（与 WeKnora 解耦）

- SBO 在生成答案/对话时，可以同时抽取“可持久化事实”写入 Semantic Memory。
- 原则：
  - **结构化事实写入 SBO**。
  - **非结构化证据写入 WeKnora**。

### 4.4 反馈纠错机制（Feedback Loop）

记忆系统必须具备**自我修正**能力，否则错误的信息会不断被重复检索。

#### 4.4.1 反馈接口设计

- **接口**：`POST /api/v1/feedback`
- **请求体**：
  ```json
  {
    "chunk_id": "string",
    "knowledge_id": "string",
    "feedback_type": "incorrect|outdated|incomplete",
    "user_correction": "string (可选)",
    "session_id": "string"
  }
  ```

#### 4.4.2 反馈处理策略

- **标记过时**：
  - 将该 chunk 标记为 `deprecated: true`
  - 后续检索时降低其权重或完全排除

- **用户纠正**：
  - 记录用户提供的正确信息
  - 可选：触发重新抽取/更新流程

- **审计追踪**：
  - 记录反馈时间、用户、会话上下文
  - 用于后续分析和改进

#### 4.4.3 实现建议

- SBO 侧维护 `FeedbackRecord` 表，记录所有反馈
- 定期同步到 WeKnora（若 WeKnora 支持反馈 API）
- 或在 SBO 侧检索时过滤已标记的 chunk

---

## 5. Orchestration 决策规则（建议默认）

### 5.1 什么时候查 WeKnora（Episodic Retrieval）

- **用户意图命中**：
  - 明确要求引用资料："根据XXX文档" "按制度" "回顾会议" "查历史记录"。
- **不确定性高**：
  - 模型路由判定“需要外部证据/需要检索”。
- **长尾知识**：
  - 非通用常识且与组织内部资料相关。
- **合规/审计类**：
  - 必须提供出处/证据链。

### 5.2 什么时候写入 WeKnora（Episodic Ingestion）

- 新文档产生：PRD/设计/合同/运行手册/复盘报告。
- 外部信息采集：网页剪藏、邮件摘要、工单闭环总结。
- 对话归档摘要：重要会议讨论、关键决策。

### 5.3 什么时候写入 Semantic（结构化事实）

- 用户稳定偏好/约束：长期有效且需要精确更新。
- 用户身份信息、权限、常用项目。
- 可用于路由与个性化的稳定状态。

---

## 6. API 对接约定（基于 WeKnora 文档）

### 6.1 基础约定

- Base URL：`/api/v1`
- 认证：HTTP Header
  - `X-API-Key: <api_key>`
  - 建议：`X-Request-ID: <uuid>` 用于全链路追踪
- 错误格式（WeKnora 文档定义）：

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Error message",
    "details": "..."
  }
}
```

### 6.2 接口文档入口

- WeKnora API 文档总览：`docs/api/README.md`
- 关键分类（按 WeKnora 文档）：
  - 知识库：`knowledge-base.md`
  - 知识导入/管理：`knowledge.md`
  - 分块：`chunk.md`
  - 搜索：`knowledge-search.md`
  - 聊天：`chat.md`
  - Agent：`agent.md`
  - 组织/共享：`organization.md`

> SBO 对接时建议优先落地：知识库管理 + 知识导入 + 搜索/检索。

---

## 7. 配置与部署建议

### 7.1 WeKnora 部署模式建议

- 生产环境：建议私有网络部署，避免公网暴露（WeKnora README 安全声明）。
- 按需启用组件（docker compose profile）：
  - `neo4j`：需要 GraphRAG 再开
  - `minio`：需要图片/多模态文件存储再开
  - `jaeger`：需要 tracing 再开

### 7.2 SBO 侧建议新增配置（示例命名）

- `WEKNORA_BASE_URL`：例如 `http://weknora:8080/api/v1`
- `WEKNORA_API_KEY`
- `WEKNORA_REQUEST_TIMEOUT_MS`
- `WEKNORA_DEFAULT_KB_ID`（可选：默认知识库）
- `WEKNORA_RETRIEVAL_TOP_K`
- `WEKNORA_RETRIEVAL_THRESHOLD`（如果你在 SBO 侧做二次过滤）
- `WEKNORA_TENANT_MODE`（single/tenant/org，单机单用户形态建议使用 single；多用户/多租户时按你的隔离方案启用）

---

## 8. 安全、隔离与审计

### 8.1 隔离边界

- 单机单用户形态：不需要租户隔离；可直接以 KnowledgeBase + Tag 作为命名空间与范围控制。
- 如未来演进为多用户/多租户：以“租户/组织 -> KnowledgeBase -> Tag”三层组合实现：
  - 租户级隔离：不同租户不共享 KnowledgeBase
  - 组织内共享：组织成员共享指定 KnowledgeBase
  - 细粒度范围：用 Tag 控制检索范围（项目/密级/时间等）

### 8.2 审计与可追溯

- 每次检索：记录
  - `request_id`
  - 查询文本（必要时脱敏）
  - 命中的 knowledge/chunk 元数据
  - 生成答案所引用的来源
- 建议：SBO 输出时带“引用来源”（可选）

---

## 9. 最小可行实现（MVP）与里程碑

### 9.1 MVP（建议 2 周内可落地）

- 能力：
  - 创建/管理 KnowledgeBase
  - 上传文档（至少 PDF/TXT/MD）并可检索
  - SBO 在回答前调用 WeKnora 检索，将结果注入 prompt
- 验收：
  - 给定一份文档，SBO 能回答 5 个需要引用文档细节的问题
  - 每个回答至少包含 1 条可追溯引用（chunk 或文档片段）

### 9.2 Milestone 2（增强检索质量）

- 启用混合检索（BM25 + Dense）与阈值策略
- 引入标签范围检索（项目/时间）

### 9.3 Milestone 3（GraphRAG/图谱增强，可选）

- 启用 `neo4j` profile
- 将结构化关系（实体/章节/引用）用于检索增强

### 9.4 Milestone 4（对话归档摘要）

- 会话结束自动生成摘要文档并写入 WeKnora
- 支持按 `session_id` 检索历史摘要

---

## 10. 运行手册（建议）

### 10.1 WeKnora 访问

- Web UI：`http://localhost`
- API：`http://localhost:8080`

> 实际以你的部署为准。


## 11. 技术坑位预警

### 11.1 多租户隔离的复杂性

**风险**：单机单用户形态不适用；如 SBO 未来演进为多用户/多租户，务必确保在调用 WeKnora 检索时，`tenant_id` 是硬隔离的。

**建议**：
- 在 WeKnora 中为每个租户创建独立的 `Organization` 或 `KnowledgeBase`
- SBO 调用检索 API 时，必须携带 `tenant_id` 或 `organization_id` 作为过滤条件
- 在 SBO 侧增加二次校验：检索结果中的 `tenant_id` 必须与当前用户匹配
- 定期审计：检查是否有跨租户数据泄露

**配置建议**：
- `WEKNORA_TENANT_MODE=tenant`（启用租户隔离模式）
- `WEKNORA_TENANT_STRICT=true`（严格模式，检索结果必须匹配租户）

### 11.2 异步队列的积压

**风险**：4.2.2 节的"对话归档"需要消耗大量 Token。如果用户连续高强度对话，大量的摘要任务可能会导致 Redis 队列积压。

**建议**：
- **调度策略**：
  - 优先级分级：实时导入（高优先级）vs 对话归档（低优先级）
  - 时间窗口：将对话归档任务放在深夜或系统空闲时执行
  - 批量合并：多个会话合并为一次归档任务

- **监控与熔断**：
  - 监控队列长度，超过阈值时暂停接收新归档任务
  - 监控 Token 消耗速率，避免超出预算
  - 设置单日归档任务上限

- **降级策略**：
  - 队列积压严重时，可跳过部分非关键会话
  - 或改为"仅归档关键决策类会话"

**配置建议**：
- `WEKNORA_ARCHIVE_PRIORITY=low`
- `WEKNORA_ARCHIVE_TIME_WINDOW=22:00-06:00`（归档时间窗口）
- `WEKNORA_ARCHIVE_QUEUE_MAX=100`（队列最大长度）
- `WEKNORA_ARCHIVE_DAILY_LIMIT=50`（单日归档上限）

### 11.3 Embedding 模型的一致性

**风险**：SBO 的 Semantic Memory 如果也用向量（pgvector），请务必保证与 WeKnora 使用**完全相同**的 Embedding 模型。否则，跨库的向量无法在同一逻辑维度下进行相似度比较。

**建议**：
- **统一模型配置**：
  - SBO 和 WeKnora 使用同一个 Embedding 服务（例如硅基流动的 `bge-m3`）
  - 或在配置中明确指定模型名称和版本

- **模型变更流程**：
  - 更换 Embedding 模型时，必须同时更新 SBO 和 WeKnora
  - 已有数据需要重新向量化（全量重建索引）

- **校验机制**：
  - 定期检查两边的模型配置是否一致
  - 在检索时记录使用的模型版本，便于问题排查

**配置建议**：
- `EMBEDDING_MODEL_PROVIDER=siliconflow`
- `EMBEDDING_MODEL_NAME=bge-m3`
- `EMBEDDING_MODEL_VERSION=v1.0`
- 两边共用同一组配置（从环境变量读取）

---

## 12. Checklist（落地前必过）

- [ ] 单机单用户形态：已明确 WeKnora 的命名空间策略（KnowledgeBase/Tag）
- [ ] 多用户/多租户形态（如适用）：已明确 SBO 的租户/组织模型如何映射到 WeKnora（Tenant/Organization/KB）
- [ ] 已定义知识库命名规范与标签规范（项目/密级/来源/时间）
- [ ] 已定义“何时检索、何时写入、何时归档摘要”的规则
- [ ] 已定义引用输出格式（是否对用户展示 chunk/文档来源）
- [ ] 已配置 `X-Request-ID` 全链路追踪并落库/落日志
- [ ] 已做安全策略：内网部署/防火墙/密钥管理（API Key）
- [ ] 已准备端到端验收用的真实文档集与问题集
