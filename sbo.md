
# AI 个性化记忆辅助系统 (Second Brain OS) 需求与架构文档

## 一、 产品概述
### 1.1 产品愿景
打造一个主动的、具备时间感知的“数字外脑”。它不仅能无摩擦地记录用户的碎片化信息，更能像人类大脑一样，自动将信息结构化、处理矛盾记忆（如用户偏好改变），并通过复杂逻辑推理回答跨越时间维度的提问。

### 1.2 核心痛点与解决方案
* **痛点 1：输入阻力大。**（解决：支持全局语音输入、截图与多渠道转发集成。）
* **痛点 2：传统搜索像“大海捞针”。**（解决：采用 GraphRAG 构建人物/事件关系图谱，支持逻辑推理问答。）
* **痛点 3：AI记不住“我是谁”且记忆矛盾。**（解决：采用 Agentic Memory 架构，AI 在后台主动更新、覆写、遗忘用户的状态配置。）

---

## 二、 核心功能需求 (Functional Requirements)

### 2.1 无摩擦录入模块 (Capture)
* **全局语音速记：** 唤醒后直接说话，系统自动转录并静默提取关键信息。
* **多模态解析：** 发送图片或屏幕截图，AI 自动提取画面中的待办、地点或人脉信息。
* **多端同步入口：** 支持微信/Telegram Bot转发、浏览器插件划线保存。

### 2.2 智能记忆管理模块 (Memory Management)
* **动态人物/偏好档案：** 系统自动维护用户的数字画像（如：喜好、健康状况、近期目标）。当用户输入“医生让我以后别喝咖啡了”，系统主动将档案中的“爱好：咖啡”更新为“禁忌：咖啡”。
* **时间感知记录：** 每条被记录的事件都会打上时间戳，理解“上周”、“昨天”的相对时间概念。

### 2.3 检索与交互模块 (Retrieval & Interaction)
* **语义与逻辑问答：** 
  * *基础问答：* “我护照号码是多少？”
  * *逻辑图谱问答：* “上周二跟我开会的那个长发投资人，他当时推荐了什么书？”
* **主动触发与提醒：**
  * *时间触发：* 基于日程提醒。
  * *情境触发：* （基于手机定位）当用户到达超市，主动推送前天随口提过的购物清单。

---

## 三、 系统架构设计 (System Architecture)

彻底抛弃老旧的单一向量数据库方案，采用**多重记忆分层架构（Multi-Tier Memory Architecture）**。

### 3.1 架构图解逻辑
```text
[用户端 / 前端 Client]  <--->[API 网关 / 路由接入层]
                                  |
               +------------------+------------------+
               |                  |                  |
    【大模型认知引擎层 (LLM Routing & Orchestration)】
       (快速回复模型)         (复杂推理模型)        (多模态模型)
               |                  |                  |
               +------------------+------------------+
                                  |
    【分层记忆系统层 (Hierarchical Memory System) - 核心】
       |
       ├── 1. 工作记忆 (Working Memory) -> Context Window + Prompt Caching (CAG)
       |      存储最近1-7天的对话上下文，极速响应。
       |
       ├── 2. 语义记忆 (Semantic/Agentic Memory) -> Redis / PostgreSQL
       |      基于 Letta/Mem0 架构。存储用户的核心事实、状态、偏好。
       |      (例如: 姓名=张三, 职业=程序员, 忌口=花生)
       |
       └── 3. 情景记忆 (Episodic Memory) -> GraphRAG (Neo4j) + Vector DB (Milvus)
              海量日志、历史文档、会议记录。以“知识图谱 + 向量”混合存储。
```

### 3.2 技术栈选型建议 (2026最新最佳实践)
* **大模型驱动层：**
  * *本地推理（llama.cpp）*：`LLM_LLAMA_BASE_URL`、`LLM_LLAMA_API_KEY`、`LLM_LLAMA_MODEL_ID` — 用于日常对话与路由（快速低成本）。
  * *外部 PROVIDER*：`PROVIDER_API_KEY`、`PROVIDER_BASE_URL`、`PROVIDER_MODEL_ID` — 用于记忆归档与复杂推理（如 NVIDIA API）。
  * *备选模型*：DeepSeek V3 / Llama-3（快速低成本）、DeepSeek R1 / Claude 3.5 Sonnet / GPT-4o（复杂推理）。
* **分层记忆框架：** 
  * *Agentic Memory：* **Mem0** (开源框架，专为 LLM 设计的自适应记忆层)。
  * *知识图谱：* **Graphiti** 或 LlamaIndex Property Graph。
* **数据库层：**
  * *图数据库：* **Neo4j** (构建实体联系)。
  * *向量数据库：* **Qdrant** 或 **Milvus**。
  * *关系型基础库：* **PostgreSQL + pgvector** (存储原始文本与系统元数据)。

### 3.3 分层记忆系统详细说明

#### 3.3.1 工作记忆 (Working Memory)

* **功能定义：** 存储最近 1-7 天的对话上下文，负责极速响应的"热路径"。
* **实现方式：** Context Window + Prompt Caching (CAG)。
* **性能目标：** 延迟 < 100ms，缓存命中率 > 80%。

#### 3.3.2 语义记忆 (Semantic/Agentic Memory)

* **功能定义：** 存储用户的核心事实、状态、偏好（如姓名、职业、禁忌）。
* **实现方式：** 基于 Mem0 框架，使用 Redis / PostgreSQL + JSONB 存储结构化事实。
* **核心能力：** 冲突解决、版本化、覆写/撤销/审计。

#### 3.3.3 情景记忆 (Episodic Memory) - 接入层

* **功能定义：** 负责处理非结构化文档、海量历史记录的索引与检索。
* **实现细节：** 本系统目前采用 **WeKnora** 作为情景记忆的底层引擎，提供文档解析、分块、向量化、混合检索（BM25 + Dense + GraphRAG）等能力。
* **集成规约：** 详细的 API 映射、写入逻辑、检索策略、配置项与安全隔离策略请参见独立文档：**[INTEGRATION_WEKNORA_EpisodicMemory.md](./INTEGRATION_WEKNORA_EpisodicMemory.md)**。

---

## 四、 核心工作流设计 (Core Workflows)

这是整个系统“好不好用”的关键，记忆的写入不能阻塞用户的实时对话。

### 4.1 写入/更新流 (异步记忆巩固 Async Memory Consolidation)
1. **输入与快响应：** 用户输入：“我刚才把备用钥匙放在玄关左边第二个抽屉了”。系统将其放入**工作记忆**，并瞬间回复：“好的，记住了”。（延迟 < 1秒）
2. **后台静默提取 (Worker Node)：**
   * *分类器：* 判断这句话是“新事件”、“偏好更新”还是“无用闲聊”。
   * *实体抽取 (GraphRAG)：* 提取节点：`[备用钥匙]`，关系：`[存放于]`，地点：`[玄关左二抽屉]`，时间：`[2026-03-16 14:41]`。
3. **记忆冲突解决：** 系统检索发现上个月记录了“备用钥匙在书房”。Agentic Memory 主动执行数据库覆写（Update）操作，并将旧记录归档为历史。

### 4.2 读取/检索流 (增强上下文检索)
1. **用户提问：** “我备用钥匙在哪？”
2. **多路召回 (Multi-Agent Retrieval)：**
   * *查询工作记忆：* 最近几天提过吗？
   * *查询状态库 (Agentic)：* 这是用户的核心属性吗？
   * *图谱/向量检索 (GraphRAG)：* 遍历实体图谱，寻找“备用钥匙”相关的最新时间戳节点。
3. **Prompt 组装与缓存：** 将召回的记忆片段与 System Prompt 组装。利用 **Prompt Caching**（提示词缓存）技术降低成本，一次性喂给大模型生成最终答案。

---

## 五、 非功能性需求 (Non-Functional Requirements)

### 5.1 数据隐私与安全 (Data Privacy) - 极度重要
* **租户隔离 (Multi-tenancy)：** 严格的按用户 ID 进行数据库行级权限隔离，图数据库必须建立按用户的 Sub-graph。
* **混合部署模式 (可选)：** 提供“端云结合”方案。敏感对话和状态提取完全在用户本地（基于本地运行的 7B/8B 小模型）完成，云端大模型只负责脱敏后的复杂推理。
* **记忆擦除权：** 用户可以说“忘掉昨天下午关于投资的所有对话”，系统必须具备软删除（Soft Delete）和硬删除的机制。

### 5.2 性能指标 (Performance)
* 文本响应时间：< 1.5 秒。
* 记忆入库延迟：异步处理，后台入库不超过 10 秒。
* 高频上下文缓存命中率：期望达到 80% 以上（利用长上下文 CAG 技术）。

---

## 六、 演进路线图 (MVP 落地计划)

为了避免项目过于庞大烂尾，建议分三个阶段开发：

### 第一阶段：MVP —— 打造“懂你的备忘录” (耗时约 4 周)
* **目标：** 实现基础输入、Agentic 状态记忆和对话。
* **舍弃：** 暂不引入复杂的知识图谱 (GraphRAG)。
* **做法：** 
  * 采用微信小程序或轻量 Web 端接入语音/文字。
  * 引入 **Mem0** 框架接管记忆逻辑。
  * 后端仅使用 PostgreSQL (文本 + JSONB 存状态 + pgvector 做简单相似度检索)。

### 第二阶段：完整形态 —— 引入关系推理 (耗时约 6-8 周)
* **目标：** 解决复杂事件关联记忆问题。
* **增加功能：** 引入 **Neo4j 和 GraphRAG** 流程，让系统能够理解“人-事-物”的多级关联。实现图片识别输入（Vision大模型接入）。

### 第三阶段：全知数字伴侣 —— 被动变主动 (长期)
* **目标：** 系统具备时间感、生物钟和主动干预能力。
* **增加功能：** 开发后台常驻的定时触发 Agent (Cron Jobs)。结合用户设备的日历、GPS、健康数据（如 Apple HealthKit API），主动推送提醒和建议。

---

## 七、 OpenClaw 集成与维护方案 (入口/控制平面)

本章节将 OpenClaw 作为“多渠道入口 + 会话/工具控制平面”，SecondBrainOS 作为“记忆与推理后端（FastAPI + Redis Queue + Postgres(pgvector) + Neo4j）”，给出可维护的工程化集成方案。

### 7.1 架构边界与职责划分

**OpenClaw 负责：**
* **多渠道接入：** Telegram/WhatsApp/WebChat 等，统一入口与消息路由。
* **会话隔离与安全策略：** pairing/allowlist、群聊 requireMention、可选 sandbox。
* **Skills/Tools 编排：** 将命令或对话触发转换为对外部系统的工具调用。
* **控制台与运维入口：** Control UI、日志、doctor、配置热更新等。

**SecondBrainOS Core 负责：**
* **记忆写入与异步巩固：** 原始事件落库、后台抽取/冲突解决/归档。
* **分层记忆存储：**
  * 状态/事实：Postgres（JSONB + pgvector）
  * 情景/关系：Neo4j（以 user_id 形成 Sub-graph）
  * 向量检索：直接 pgvector（事件/片段 embedding）
* **检索与证据组装：** 多路召回（状态 + 事件 + 图谱），输出 evidence 列表供模型生成答案。
* **擦除权与审计：** 软删/硬删、删除作业与回执、可回放。

**核心原则：**
* OpenClaw 可频繁升级；SecondBrainOS Core 的 API 契约保持稳定。
* 任何输入先落 raw（可回放）；profile/graph/vector 等均为派生物（可重建）。

### 7.2 数据流（写入/读取）

**写入（Capture -> Consolidation）：**
1. 用户通过 OpenClaw 任意渠道输入。
2. OpenClaw 前台快速确认（“记住了/收到”），不阻塞。
3. OpenClaw skill 调用 SecondBrainOS：`POST /ingest`。
4. SecondBrainOS 将事件写入 `raw_events`，并将 `consolidate_event(event_id)` 入队（Redis Queue）。
5. Worker 后台完成：抽取结构化信息、更新状态记忆、生成 embedding、写入 Neo4j 图谱。

**读取（Question -> Retrieval -> Answer）：**
1. 用户提问。
2. OpenClaw skill 调用 SecondBrainOS：`POST /query`。
3. SecondBrainOS 进行多路召回并返回 evidence 列表（可包含时间戳/来源/引用）。
4. OpenClaw 将 evidence 注入上下文，由大模型生成最终回复（可要求引用证据）。

### 7.3 SecondBrainOS Core：最小 API 契约（建议）

**鉴权：**
* 复用 OpenClaw Gateway 的 Bearer token 作为统一入口鉴权（单用户场景）。
* OpenClaw skill 调用 SecondBrainOS 时附带：`Authorization: Bearer <OPENCLAW_GATEWAY_TOKEN>`。
* SecondBrainOS 验证该 token 后放行（可加入简单的 token rotation）。

**`POST /ingest`**（写入原始事件 + 入队）
* 入参建议：
  * `source`：telegram/webchat/whatsapp...
  * `source_message_id`：上游消息 ID（用于幂等）
  * `occurred_at`：事件时间
  * `content`：纯文本（语音/图片先转写/OCR 后写入）
  * `tags`：可选
  * `idempotency_key`：可选（推荐）
* 出参建议：`event_id`、`queued_jobs`。

**`POST /query`**（召回 + 证据）
* 入参建议：
  * `query`、`top_k`、`time_range`（可选）、`mode`（fast/deep）
* 出参建议：
  * `answer_hint`（可选）
  * `evidence[]`：
    * `evidence_id`
    * `type`：raw_event/profile_fact/graph_fact
    * `text`
    * `occurred_at`
    * `source`
    * `confidence`
    * `refs`：event_id / graph node id

**`POST /forget`**（擦除权：异步）
* 入参建议：按 `time_range` / `tags` / `event_ids`。
* 出参建议：`erase_job_id`（可查询状态）。

**`GET /health`**（健康检查）
* 检查 Postgres/Redis/Neo4j 连通性、队列积压。

### 7.4 异步巩固（Redis Queue / RQ）任务拆分

建议拆分为可重试、可单独重跑的 Job（避免一个大任务导致难以修复）：
* `consolidate_event(event_id)`：抽取结构化信息（实体/关系/偏好变化/待办等），写入 `extractions`。
* `upsert_profile(extraction_id)`：冲突解决 + 版本化（current + history）。
* `embed_event(event_id)`：生成 embedding 写入 pgvector。
* `upsert_graph(extraction_id)`：Neo4j MERGE 节点/关系（带 `source_event_id` 与时间戳）。

### 7.5 embeddings：硅基流动（SiliconFlow）API 接入策略

* 将 embeddings 作为 SecondBrainOS Core 的内部能力，避免 OpenClaw 侧耦合。
* 配置建议（示例字段名）：
  * `SILICONFLOW_API_KEY`
  * `SILICONFLOW_BASE_URL`（如供应商提供自定义网关/域名）
  * `SILICONFLOW_EMBEDDING_MODEL`
* 失败策略：
  * embedding 失败不影响 raw_events 落库与其它抽取步骤。
  * 允许对历史事件批量重跑 embedding（从 raw_events 回放）。

### 7.6 OpenClaw Skills：接入方式（建议）

目标是把 SecondBrainOS 能力封装为少量、稳定的命令入口：
* `/remember <text>` -> 调用 `POST /ingest`
* `/recall <question>` -> 调用 `POST /query` 并展示 evidence
* `/forget <selector>` -> 调用 `POST /forget`
* `/sb-status`（可选）-> 调用 `GET /health`

安全与可维护建议：
* 使用 OpenClaw skill 的 `command-dispatch: tool` 让命令直接派发到工具调用，避免模型“自由发挥”。
* OpenClaw 配置保持默认 DM pairing + allowFrom（单用户场景只 allow 自己）。
* SecondBrainOS 服务地址与 token 均走环境变量或 secretref，避免写入 skill 文本。

### 7.7 运维与升级策略（单用户但可长期演进）

**升级：**
* OpenClaw 使用 stable channel，升级后运行 `openclaw doctor`。
* SecondBrainOS Core 通过 API 契约保持稳定，内部可独立迭代。

**迁移与回滚：**
* Postgres 使用迁移工具（如 Alembic）。
* `raw_events` 作为事实源 append-only（支持软删字段），其余派生表/索引可重建。
* Neo4j 图谱可从 raw_events + extractions 重建（将图谱视为派生物）。

**备份：**
* 定期备份 Postgres（raw_events + profile + 元数据）。
* Neo4j 可选备份；若成本较高，可仅保留重建策略与重建脚本。


## 八、 SecondBrainOS 独立应用形态（可选集成 OpenClaw）

本章节明确 SecondBrainOS 作为一个独立应用（自带前后端，可脱离 OpenClaw 单独使用）的产品形态，并给出“默认自动召回（选项2）”的稳定实现策略，以及与 OpenClaw 的松耦合集成方式。

### 8.1 独立应用总体架构

SecondBrainOS 以“独立应用 + 可选适配器”的方式建设：

* **SecondBrainOS App（独立可用）：**
  * 前端：Capture（快速记录）、Timeline（事件流）、Profile（偏好/禁忌/事实）、Query（问答与 evidence 展示）、Erase（擦除权）。
  * 后端：FastAPI 提供统一 API（供 Web 前端/未来移动端/外部适配器调用）。
  * 异步：Redis Queue（RQ Worker）完成抽取、冲突解决、embedding、图谱 upsert。
  * 存储：Postgres + pgvector（事实/索引）与 Neo4j（关系图谱）。

* **OpenClaw Adapter（可选）：**
  * 作为额外入口，将 OpenClaw 的渠道消息转为对 SecondBrainOS API 的调用。
  * SecondBrainOS 仍是事实源；OpenClaw 仅负责渠道接入、会话与工具编排。

### 8.2 “默认自动召回（选项2）”实现策略

目标是在不降低对话体验的前提下，让系统“像真的记得住你”。推荐采用“SecondBrainOS 负责召回证据，OpenClaw/前端负责生成回复”的模式。

**自动召回流程（OpenClaw 场景）：**
1. 用户发来任意消息。
2. OpenClaw 在生成回复前，先调用 SecondBrainOS：`POST /query`（建议 `mode=fast`，`top_k` 较小）。
3. SecondBrainOS 返回 `evidence[]`（带时间戳/来源/置信度/引用）。
4. OpenClaw 将 evidence 注入上下文，由大模型生成最终回复（可要求引用证据）。

**自动召回流程（SecondBrainOS 独立 Web App 场景）：**
1. 用户在 Query 页面提问。
2. 后端执行 `POST /query` 的检索编排并返回 evidence。
3. 前端展示 evidence，并展示最终答案或答案草案。

### 8.3 自动召回的护栏（性能/噪音/失败降级）

为避免“每次都召回导致延迟变大或注入噪音”，建议固化以下护栏：

* **阈值：** 按 `confidence` 过滤低质量证据；默认只注入 top-N（如 3~8 条）。
* **缓存：** 同一会话/相近 query 在短窗口内复用召回结果，减少重复调用。
* **失败降级：** SecondBrainOS 不可用时，OpenClaw 直接正常聊天（不影响 OpenClaw 原有能力）。
* **分档策略：** `mode=fast` 用 pgvector + 时间优先规则；`mode=deep` 才做图谱扩展与更昂贵的推理。
* **可选意图判定：** 仅当检测到“需要记忆”的问题时才触发召回（后续优化项）。

### 8.4 与 OpenClaw 的松耦合集成方式

SecondBrainOS 独立应用与 OpenClaw 的关系是“可选增强”，而非强依赖：

* **SecondBrainOS 可独立使用：** 不启动 OpenClaw 也可通过 Web App 完成 capture、检索与管理。
* **OpenClaw 可独立运行：** 即便 SecondBrainOS 暂时不可用，OpenClaw 仍能接收消息并正常对话。
* **统一 API：** Web App 与 OpenClaw Adapter 都通过同一套 SecondBrainOS API 访问记忆能力。

**鉴权建议（单用户）：**
* OpenClaw -> SecondBrainOS 的调用继续复用 OpenClaw Gateway Bearer token。
* SecondBrainOS Web App 建议使用独立的登录/会话（与机器到机器 token 分离），避免未来扩展时混用。

### 8.5 推荐落地路线图（先独立，再集成）

* **阶段 1：独立 App MVP（先可用）**
  * Web App：可记录、可检索、可展示 evidence。
  * API：`/ingest`、`/query`、`/forget`、`/health`。
  * Worker：embedding + 基础抽取（可先弱化图谱）。

* **阶段 2：接入 OpenClaw（获得多渠道入口 + 自动召回）**
  * OpenClaw skills/adapter 将每次对话前自动调用 `/query`。
  * 落地阈值/缓存/失败降级，保证体验。

* **阶段 3：GraphRAG + 主动触发（完整形态）**
  * Neo4j 深度检索与图谱推理。
  * 主动提醒与情境触发（可由 SecondBrainOS 自己的调度器实现，也可复用 OpenClaw cron/nodes）。


## 九、 独立前端复用与迁移方案（基于 zip 原型）

本章节评估现有前端原型（`zip/`）对 SecondBrainOS 独立应用的可复用性，并给出“从原型到正式独立应用”的前端落地方案。核心目标是复用已验证的 UI/交互，替换 Firebase 与前端直连大模型等不适合生产的部分。

### 9.1 原型可复用部分（建议直接迁移）

`zip/` 原型已具备“Sidebar + Chat”的 MVP 交互形态，以下模块可原样迁移到独立前端工程：

* **UI 组件：**
  * `zip/src/components/Chat.tsx`：消息展示、输入与 loading、Markdown 渲染。
  * `zip/src/components/Sidebar.tsx`：记忆卡片侧栏展示。
  * `zip/src/components/ErrorBoundary.tsx`：错误边界与故障自恢复。

* **页面骨架：**
  * `zip/src/App.tsx` 的布局结构（Sidebar + Chat）可复用，但其数据读取与写入逻辑需要改为调用 SecondBrainOS Core API。

### 9.2 必须替换部分（从原型走向独立应用）

* **Firebase Auth / Firestore：**
  * 原型通过 Firebase Auth 登录、通过 Firestore 实时订阅 `memories/messages`。
  * 正式方案中应迁移为 SecondBrainOS Core（FastAPI + Postgres）提供的数据接口；实时能力可先用轮询，后期再上 SSE/WebSocket。

* **前端直连大模型（Gemini）：**
  * 原型在浏览器中直接初始化模型 SDK 并调用 `generateContent`，存在 key 暴露与难以审计的问题。
  * 正式方案中，模型调用、抽取、embedding、图谱写入全部迁移到后端与 worker；前端只调用后端 API。

* **记忆抽取在浏览器执行：**
  * 原型中 `extractMemories()` 输出 add/update/delete 并直接写 Firestore。
  * 正式方案中，该能力应改为后端异步巩固（RQ worker）执行：可重试、可回放、可审计。

### 9.3 推荐前端技术栈（面向复用与迭代）

为最大化复用现有 React + Tailwind 风格的 UI，推荐继续使用：

* **Vite + React + TypeScript + Tailwind**

其优势是迁移成本低、开发反馈快；如果后期需要服务端渲染或更复杂的路由/权限体系，再评估 Next.js。

### 9.4 前端状态模型（建议）

为了支持“默认自动召回（选项2）”与可解释证据展示，建议在前端类型上引入 evidence：

* **Memory**
  * `id`
  * `content`
  * `type`: `preference | fact | event`
  * `timestamp`

* **Message**
  * `id`
  * `role`: `user | assistant | system`
  * `content`
  * `timestamp`
  * `evidence?`: `Evidence[]`（可选，用于展示引用证据）

* **Evidence**
  * `evidence_id`
  * `type`: `raw_event | profile_fact | graph_fact`
  * `text`
  * `occurred_at`
  * `source`
  * `confidence`
  * `refs`（event_id / graph node id 等）

### 9.5 API Client 设计（前端只做 API 调用）

建议新增独立的 API client 层（例如 `src/services/api.ts`），统一处理：baseUrl、鉴权、错误、重试与超时。

前端应仅调用 SecondBrainOS Core，避免把业务逻辑散落在组件中：

* `GET /memories`：拉取已巩固的记忆（供 Sidebar 展示）。
* `GET /conversations/{id}/messages`：拉取消息列表（供 Chat 展示）。
* `POST /chat`（或 `POST /conversations/{id}/messages`）：发送用户消息并获得 assistant 回复。
  * 后端负责：写入 raw_events、自动召回 evidence（fast）、调用模型生成回复、返回 `assistant_message` + `evidence[]`。
* `POST /ingest`：纯记录入口（不需要模型回复时使用）。
* `POST /forget`：擦除权。
* `GET /health`：健康检查与调试。

鉴权建议（单用户）：
* Web 前端使用 SecondBrainOS 自己的登录/会话。
* OpenClaw -> SecondBrainOS 复用 OpenClaw Bearer token（见第七章）。

### 9.6 证据（Evidence）展示 UI（建议）

为保持对话简洁，同时提供可解释性，建议采用“默认折叠”的证据展示：

* assistant 消息下方显示“引用证据（N）”按钮/折叠面板。
* 展开后按 `type` 分组展示：profile_fact（偏好/事实）、raw_event（事件片段）、graph_fact（关系推理）。
* 每条证据展示：摘要 + 时间戳 + 来源（source）+ 置信度（可选）。
* 若后端提供 `refs`，可进一步支持跳转到 Timeline 或详情页（后续能力）。

### 9.7 从原型到正式前端的分阶段迁移计划

* **阶段 A：UI 迁移与数据 mock（先跑起来）**
  * 新建独立前端工程目录。
  * 迁移 `Chat/Sidebar/ErrorBoundary` 组件与样式。
  * 用 mock 数据驱动页面，验证 UI 结构与交互。

* **阶段 B：接入 SecondBrainOS Core API（替换 Firebase）**
  * 新增 `services/api.ts`。
  * `App` 从 Firestore 订阅改为 API 拉取（可先轮询）。
  * 发送消息改为调用 `/chat`，由后端返回回复与 evidence。

* **阶段 C：补齐管理能力（Timeline/Profile/Erase）**
  * Timeline：展示 raw_events（便于审计与回放）。
  * Profile：展示 current facts + history（可选）。
  * Erase：擦除权管理与回执。


这份《AI 个性化记忆辅助系统 (Second Brain OS) 需求与架构文档》是一份**极其专业、架构清晰且具有高度落地可行性**的设计方案。

文档不仅准确抓住了当前 AI 应用的痛点（记忆遗忘、记忆冲突、输入摩擦），而且在架构设计上完全对齐了目前业界最前沿的 Agentic Memory（如 MemGPT/Letta）和 GraphRAG 理念。特别值得称赞的是**“异步记忆巩固”**和**“分阶段 MVP 演进”**的设计，这极大地降低了工程烂尾的风险。

以下是文档中各项需求的详细可行性评估，以及潜在的工程风险和优化建议：

---

### 一、 高度可行的亮点（设计得非常棒的地方）

1. **分层记忆架构 (Multi-Tier Memory)**
   * **可行性：极高。** 完全抛弃“将所有对话塞进向量库”的老路，采用工作记忆（Context Window）、状态记忆（KV/Profile）和情景记忆（Vector+Graph）分层，这是目前解决 AI 记忆混乱的唯一正解。
2. **异步巩固工作流 (Async Memory Consolidation)**
   * **可行性：极高且必要。** 让前台瞬间响应“记住了”，后台利用 Redis Queue + Worker 节点去做耗时的实体抽取、向量化和图谱重构。这保证了用户体验的丝滑，也是实现 `< 1.5 秒` 响应时间的刚性前提。
3. **分阶段演进路线图 (MVP 策略)**
   * **可行性：极高。** 也是本方案最清醒的地方。Phase 1 暂缓引入极其复杂的 GraphRAG (Neo4j)，仅用 `Postgres + JSONB + pgvector + Mem0` 打底，这让 4 周内跑通 MVP 成为完全可能。
4. **与 OpenClaw 解耦的 API 设计**
   * **可行性：极高。** 将前端/多渠道网关与后端的“记忆引擎”彻底解耦，定义了极简的 API 契约（`/ingest`, `/query`, `/forget`）。这意味着系统既可以作为独立 App 存在，也可以接入 Telegram/微信。

---

### 二、 潜在的工程风险与挑战（需要注意的坑）

尽管整体可行，但在实际开发中，以下几个需求会面临较大的技术挑战：

#### 1. 记忆更新与冲突解决（Agentic Memory 的难点）
* **挑战：** 当用户说“我以后不喝咖啡了”，大模型需要精准识别出这是对旧记忆“爱好：咖啡”的覆写，而不是新增一条记忆。
* **可行性评估：** 中等偏上。Mem0 等框架原生支持这种逻辑，但大模型在后台做 `Update/Delete` 决策时，偶尔会发生幻觉（比如误删了其他信息）。
* **建议：** 必须保留 `raw_events`（原始事件流）作为事实基准（Append-only）。当状态记忆发生错乱时，系统可以通过重新回放 `raw_events` 来重建 Profile。

#### 2. 时间间隙导致的“赛跑条件 (Race Condition)”
* **挑战：** 用户刚输入：“我的护照在抽屉里”，2 秒后立马问：“我护照在哪？” 此时后台的 Redis Worker 可能还没完成抽取和入库（文档中写了后台入库不超过 10 秒）。
* **可行性评估：** 这是异步架构的通病。
* **建议：** 在 `POST /query` 的召回策略中，**必须将最近 10-15 分钟的对话记录（Working Memory）直接作为最高优先级的上下文喂给大模型**，以填补异步入库的时间差。

#### 3. GraphRAG (Neo4j) 的维护成本（Phase 2）
* **挑战：** 知识图谱的建立容易，但更新极难。当事件发生变化时，如何在图谱中找到旧节点、更新关系边，并与向量数据库（pgvector）保持同步？
* **可行性评估：** 落地成本极高。
* **建议：** 建议在 Phase 2 引入图谱时，先做**只读型/追加型图谱**。对于冲突的实体状态，优先依赖 Phase 1 中的 Postgres Profile 库来解决，不要把业务逻辑强绑定在 GraphRAG 的更新上。

#### 4. “记忆擦除权”的级联删除问题
* **挑战：** 用户要求“忘掉昨天下午的投资对话”。系统不仅要软删 `raw_events`，还要从 Postgres 状态库、pgvector 向量库、Neo4j 图谱中把衍生出来的节点和向量全部找出来删掉。
* **可行性评估：** 极其复杂。
* **建议：** 在 `extractions`（抽取表）和图谱节点中，**必须严格绑定 `source_event_id`**。擦除时，先软删 `raw_events`，然后通过外键或 ID 级联软删所有派生数据。

#### 5. 性能指标（< 1.5秒响应）
* **挑战：** 多路召回（Multi-Agent Retrieval）如果涉及向大模型发起多次请求来判断意图，时间很容易超过 3-5 秒。
* **可行性评估：** < 1.5 秒极其严苛。
* **建议：** 
  * 采用模型分级：意图识别和快速检索使用超快的小模型（如本地部署的 Qwen2.5-7B-Instruct 或云端的 DeepSeek-V3）。
  * 并发召回：对状态库、向量库的检索必须并发执行（`asyncio.gather`）。

---

### 三、 架构层面的微调建议

为了让系统更加健壮，我建议在您的架构上做一点微调：

1. **统一向量与关系存储：** 
   既然您使用了 `Postgres + pgvector`，建议在前期**不要引入独立的向量数据库（如 Milvus/Qdrant）**。Postgres + pgvector 完全能撑起百万级别的向量检索，减少一个组件，运维复杂度降低 50%。
2. **Embedding 策略：** 
   引入 SiliconFlow (硅基流动) 作为 Embedding API 是个好主意。推荐使用 `BAAI/bge-m3` 或 `bge-large-zh-v1.5`，它们对中文语义和长文本支持极好。
3. **前端证据展示（Evidence UI）：** 
   在第 9.6 节中提出的“引用证据（N）”设计非常关键。AI 伴侣系统最怕的就是“黑盒”。通过让用户看到系统是基于哪条过去的记录得出的结论，即使 AI 回答有些偏差，用户也会觉得系统是“可控的、透明的”。

### 总结

这份架构文档是一份**教科书级别的 AI 原生应用设计稿**。您没有盲目堆砌大模型能力，而是深刻理解了“记忆体系本质上是一个复杂的数据工程”。

**结论：完全可行，可以直接进入开发阶段。** 强烈建议严格按照您设定的“Phase 1 (MVP) -> Phase 2 -> Phase 3”来执行，先用 Postgres + Mem0 打通闭环，再图谋 GraphRAG，必将事半功倍。