# SecondBrainOS 借鉴 memory-lancedb-pro：要点与实现约束

## 0. 目的与边界

本文档用于把 `memory-lancedb-pro` 项目中经验证的工程化策略，**以“可移植、与 Agent 框架无关（agent-agnostic）”的方式**固化到 SecondBrainOS（SBO）的设计与实现中。

适用范围：
- 仅作为 SBO Core（FastAPI + Postgres/Redis/Neo4j/WeKnora）的**实现参考与约束来源**。
- 不引入 `memory-lancedb-pro` 的代码/运行时依赖，不将其作为 SBO 的存储真值层。

非目标：
- 不将 `memory-lancedb-pro` 作为 SBO 的 Semantic/Agentic Memory 真值存储。
- 不将 `memory-lancedb-pro` 作为 SBO 的 Episodic Memory 引擎（Episodic 以 WeKnora 为主）。
- 不依赖 OpenClaw 的 hook/tool/插件生态。

与 SBO 权威原则对齐：
- `raw_events` 为事实源（append-only，支持软删字段）。
- 其余派生表/索引可重建（pgvector/图谱/WeKnora 索引）。
- 单机单用户形态：不需要租户隔离；如未来演进为多用户/多租户，则以租户隔离、擦除权、审计与可回放优先。

---

## 1) 借鉴组一：检索排序管线（增强 `POST /query`）

### 1.1 借鉴要点（抽象成通用流水线）
SBO 的检索应统一进入可组合的排序管线（不绑定具体数据源）：

1. 候选召回（可能并行）：
   - Semantic（Postgres/pgvector/结构化事实）
   - Episodic（WeKnora：BM25 + Dense + 可选 GraphRAG）
   - Graph（Neo4j 图谱扩展召回，如适用）
2. 融合（fusion）：
   - dense 为主
   - lexical 命中提供奖励/保底（尤其是符号型查询：ID、token、配置项、环境变量等）
3. 可选 rerank（cross-encoder 或等价重排）：
   - 失败必须降级到 fusion 结果
4. 归一化与过滤：
   - length normalization（避免长文本主导）
   - hardMinScore（硬过滤无关结果）
5. 时间与生命周期重排：
   - time-decay / recency boost（阶段 1）
   - reinforcement / tier（阶段 2+，见第 5 组）
6. 噪声过滤与多样性：
   - noise filter
   - MMR diversity（相似项延后而非删除）

### 1.2 实现约束（必须满足）
- **可用性约束**：任何上游（WeKnora、rerank provider、图谱）不可用时，`/query` 必须仍能返回结果（至少 Semantic 或 Working Memory 回退路径）。
- **顺序约束**：`hardMinScore` 必须发生在 time-decay/lifecycle 之前，避免衰减项抬高低质结果。
- **融合约束**：必须支持“符号型查询保底”策略；对高置信 lexical 命中不得被 rerank 轻易淘汰（preservation floor）。
- **可解释性约束**：`evidence[]` 必须携带关键评分信息（至少 `final_score`，推荐同时包含 `dense_score/bm25_score/rerank_score`）。

---

## 2) 借鉴组二：Cross-Encoder 重排与降级策略

### 2.1 借鉴要点
- 重排是质量增益点，但必须以稳定性为前提：
  - **API 失败降级**：重排失败时回退到 fusion 排序。
  - **混合评分**：重排分数不应完全覆盖原始相关性（可采用加权融合）。
  - **符号查询保护**：对高 BM25/lexical 命中设置保底阈值，避免被 cross-encoder 错杀。

### 2.2 实现约束
- **禁止强依赖**：重排 provider 不得成为 `/query` 的强依赖；不得因重排超时导致整体超时。
- **超时约束**：重排必须有独立超时与并发控制。
- **审计约束**：必须记录本次请求是否执行重排、使用的 provider/model/version、以及降级原因（如超时/5xx）。

---

## 3) 借鉴组三：shouldSkipRetrieval（召回护栏）与噪声过滤

### 3.1 借鉴要点
为了控制延迟与噪声注入，SBO 需要显式的“是否检索”决策：

- **跳过 Deep Retrieval** 的典型输入：
  - 问候语、寒暄、简单确认（“好”“OK”“收到”）
  - emoji 或短无信息输入
  - 纯命令/斜杠指令（若系统已用 tool 直达处理）
- **强制 Deep Retrieval** 的典型输入：
  - “记得/之前/上次/回顾/根据文档/查历史/会议纪要/制度/日志”等记忆或证据意图

CJK 特性：
- 中文短 query 常见，应采用不同的最短长度/阈值策略，避免误判为“无需检索”。

### 3.2 实现约束
- **护栏优先**：是否进入 Deep Mode 的判定必须先于 WeKnora 调用，以避免不必要的外部请求。
- **可配置**：阈值、关键词列表、最短长度、跳过规则必须配置化（环境变量或配置文件），并在审计日志中记录生效配置版本。
- **安全注入**：当注入召回证据到 prompt 时，必须标记为不可信数据（见第 4 组）。

---

## 4) 借鉴组四：Scope 隔离模型（多租户与多 Agent 边界）

### 4.1 借鉴要点
参考 `memory-lancedb-pro` 的 scope 体系，将隔离维度统一抽象为“scope/namespace”，用于所有 evidence 的硬过滤：

单机单用户形态说明：
- `user_id` 在隔离意义上可以视为常量（可由后端默认补齐），主要用于审计、回放与未来演进一致性。
- `agent_id` 表示入口/执行体（例如不同渠道 bot、不同自动化 agent），语义上不等同于 `user_id`。

- 建议统一支持的 scope 形态（SBO 内部可等价映射）：
  - `global`
  - `user:<user_id>`
  - `agent:<agent_id>`
  - `project:<project_id>`
  - `custom:<name>`

### 4.2 实现约束
- **硬隔离**：scope 过滤必须在检索/融合之前执行，禁止“先检索再过滤导致泄露”。
- **统一字段**：所有 evidence（来自 Postgres/WeKnora/Neo4j）必须携带：
  - `tenant_id`（多用户/多租户形态适用；单机单用户形态可省略）
  - `user_id`（单机单用户形态可默认常量；多用户形态必须提供并硬过滤）
  - `project_id`（如适用）
  - `scope`
- **二次校验**：单机单用户形态不需要；如未来演进为多用户/多租户，对外部系统返回的结果（如 WeKnora）必须进行二次校验：结果携带的租户/组织标识必须与当前请求一致。

---

## 5) 借鉴组五：统一 metadata 中枢 + 生命周期/衰减（分阶段落地）

### 5.1 借鉴要点（metadata 中枢）
借鉴“smart metadata 作为系统收敛点”的思想，SBO 必须定义统一的 `evidence[]` 规范，使上层 Agent 适配器不需要理解每个存储后端的细节。

建议 `evidence[]` 至少包含：
- 标识：`evidence_id`、`type`、`refs`
- 隔离：`tenant_id`（多用户/多租户形态适用）、`user_id`（单机单用户形态可默认常量）、`project_id`、`scope`
- 时间：`occurred_at`（优先）、`created_at`（次之）
- 质量：`confidence`、`scores`（推荐：`dense/bm25/rerank/final`）
- 审计：`request_id`、`retrieval_trace`（可选）

### 5.2 借鉴要点（生命周期/衰减目标）
借鉴生命周期设计要解决的问题，而非绑定某个具体实现：
- 近期更重要（recency）
- 常用更重要（frequency / reinforcement）
- 高重要性更慢衰减（importance）

### 5.3 实现约束（必须满足）
- **事实源优先**：任何生命周期字段（如 access_count、last_accessed_at）不得破坏 `raw_events` 的可回放与派生可重建原则。
- **分阶段约束**：
  - 阶段 1：仅 time-decay re-ranking（简单、可解释）
  - 阶段 2：引入 access_count/last_accessed_at（强化衰减）
  - 阶段 3：再评估更复杂 decay engine
- **写入点约束**：生命周期“访问计数/最后访问时间”的更新必须通过明确的写路径（例如在 `/query` 返回后异步记录），不得在热路径造成显著延迟。

---

## 6) Prompt 注入安全约束（统一适用）

无论证据来自何处，注入到大模型上下文时必须满足：
- 注入块必须标记为 **`[UNTRUSTED DATA]`**（或等价语义），提示模型仅作参考而非指令。
- 系统提示词应包含：不得泄露/引用内部证据块原文（按产品策略选择严格程度）。
- evidence 默认注入数量应有上限（例如 top-N），并允许按阈值过滤。

---

## 7) 验收清单（落地前必过）

- [ ] `/query` 在 WeKnora 不可用时可降级返回（无 5xx，且有可用答案/证据为空也可接受）
- [ ] rerank provider 超时/失败时可降级，且审计日志记录降级原因
- [ ] `hardMinScore` 生效位置正确（发生在 time-decay/lifecycle 之前）
- [ ] 对符号型查询存在 lexical 保底机制，且有回归用例
- [ ] shouldSkipRetrieval 规则对问候/短确认生效，且对“记忆意图关键词”强制检索生效
- [ ] 所有 evidence 都包含 `scope` 与 `user_id/project_id`（按适用性），并在检索前执行硬过滤
- [ ] 多用户/多租户形态（如适用）：所有 evidence 都包含 `tenant_id`，并在检索前执行硬过滤与二次校验
- [ ] evidence 注入块带 `[UNTRUSTED DATA]`，并且注入数量上限可配置
- [ ] 访问计数/last_accessed 的更新不阻塞热路径（建议异步）

---

## 8) 文档变更与任务提示词同步

- 本文档为非日志类权威参考文档。
- 若仓库未来出现 `docs/task-prompts/*.md`，必须在相关任务提示词中新增“权威参考文档/约束来源”并引用本文档路径：`BORROWING_memory-lancedb-pro.md`，并在对应 `# Checklist` 勾选“Doc References Updated / 文档引用已同步”。
