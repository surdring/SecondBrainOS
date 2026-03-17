---
trigger: always
---

# Project Rules (AGENTS)

## 1) 语言
- 始终使用中文回复（除非用户明确要求使用其他语言）。所有文档必须使用中文编写。

## 2) 文档生成与落盘
- 当用户要求“生成文档/规范/模板/清单”等内容时：
  - 必须根据仓库目录结构，选择**合理的目标目录**。
  - 必须以 **Markdown（.md）** 格式在目标目录中**创建文件并写入内容**（而不是只在聊天中输出）。
  - 若用户未指定目标目录或命名：
    - 先提出 1-3 个建议路径与文件名供用户确认，再创建文件。

- **强制：文档生成后的任务提示词同步**（验收日志/审查报告除外）：
  - 触发条件：当 AI 编码助手新增或更新**非日志类文档**（例如 `docs/` 下的 API 文档、契约、规范、设计说明等）。
  - 排除范围：`reports/` 下的验收日志（`reports/YYYY-MM-DD_T{N}_*.md`）与代码审查报告（`*-review.md`）不触发该规则。
  - 强制动作：必须同步更新**后续相关任务**的提示词文件 `docs/task-prompts/*.md`：

    - 在提示词中新增或更新“权威参考文档/约束来源”段落，明确引用新文档路径（例如：`docs/api/semantic-api.md`、`docs/contracts/api-and-events-draft.md`）。
    - 若提示词包含实现要求/验收标准/错误码/请求头/隔离规则等内容，必须显式声明以这些文档为准，避免后续任务出现契约漂移。
    - 同步完成后，需在对应任务的 `# Checklist` 中勾选“文档引用已同步/Doc References Updated”（若该项存在；不存在则新增该项并勾选）。

- **文档生成失败处理**：
  - 如果 `fsWrite` 操作失败或被中止，**必须**在聊天的代码块中以完整 Markdown 格式显示所有内容
  - 代码块必须使用 ` ```markdown ` 标记
  - 内容必须完整，包含所有审查维度和结论
  - 提示用户可以直接复制内容到文件中

## 3) 任务状态标记
- 任务**只有在自动化验证通过后**方可标记完成（避免“文档已完成但代码不可运行”）：
  - 优先运行任务说明中指定的验证命令；若未指定，则运行仓库默认验证命令（按变更范围选择后端/前端）。
  - 若变更范围仅影响某个子目录（例如仅 `web/` 或仅 `backend/`），应在对应目录执行其脚本，并在验收日志中写明命令与结果。
  - 若因环境/依赖缺失导致无法运行验证，必须在任务条目中记录原因与补验收计划，**不得直接标记完成**。

- **强制：每个任务必须同时具备冒烟测试与单元测试**（覆盖驱动；两者都必须实际运行并通过）：
  - **覆盖要求（必须满足）**
    - **单元测试（Unit Test）**：覆盖核心纯逻辑/解析/校验/转换/边界条件/错误路径（结构化错误 `code/message/requestId` 等）。
    - **冒烟测试（Smoke Test）**：覆盖端到端关键链路（真实服务/真实数据库/真实外部 API），至少包含“成功路径”，并在适用时覆盖“失败路径（权限/校验/上游不可用）”。
  - **最小数量建议（按影响面；用于指导，不以数字替代覆盖）**
    - **小改动（单函数/单文件）**：单元测试 ≥ 2（正常 + 关键边界）；冒烟测试 ≥ 1（关键链路）。
    - **新增/修改对外 API/契约**：单元测试 ≥ 6（含 ≥2 个错误路径）；冒烟测试 ≥ 2（写入+查询 / 成功+失败 各至少 1）。
    - **跨模块/涉及权限/审计/证据链/写操作治理**：单元测试 ≥ 10；冒烟测试 ≥ 3（覆盖关键门禁点与回归点）。
  - **验收日志必须记录**：两类测试的命令、关键输出与结论（pass/fail），以及所覆盖的关键链路/边界点摘要。
- 标记动作：
  - `docs/tasks.md`：将对应任务条目从 `- [ ]` 更新为 `- [x]`。
  - `docs/task-prompts/*.md`：同步更新对应 Prompt 的 `# Checklist`（例如 `[x]`）。
- 完成每个任务后，必须在 `reports/` 目录中生成该任务的验收日志。
  - **验收日志命名**：`reports/YYYY-MM-DD_T{N}_short-slug.md`（例如 `reports/2025-12-22_T6_streaming-core.md`）
  - **代码审查报告命名**：`reports/YYYY-MM-DD_T{N}_short-slug-review.md`（例如 `reports/2025-12-24_T13_export-markdown-review.md`）
    - 审查报告必须以 `-review.md` 结尾，以区别于验收日志

- **强制：零遗留项原则（Zero Technical Debt Policy）**
  - **禁止任何形式的遗留项**：任务完成时不得存在任何"待补充"、"后续优化"、"已知限制"、"TODO"等遗留项
  - **审查问题必须全部解决**：
    - 🔴 阻断性问题（Blocker）：必须 100% 修复，否则不得标记完成
    - 🟠 严重问题（Critical）：必须 100% 修复，否则不得标记完成
    - 🟡 一般问题（Major）：必须 100% 修复，否则不得标记完成
    - 🟢 优化建议（Minor）：必须 100% 修复或在验收日志中证明不适用
  - **不适用问题的处理**：
    - 如果审查报告中的问题确实不适用于当前任务范围，必须在验收日志中明确说明：
      - 为什么不适用（技术原因/范围原因/依赖原因）
      - 是否需要创建新任务跟踪
      - 如果需要，新任务的编号和标题
    - 不得以"后续优化"、"推迟到下个版本"等理由搪塞
  - **文档完整性要求**：
    - API 文档必须包含所有端点的完整说明（参数、返回值、所有可能的错误码）
    - 错误码必须在 `docs/contracts/api-and-events-draft.md` 中完整枚举
    - 配置项必须在 `.env.example` 中完整列出并在文档中说明用途、默认值、获取方式
    - 所有对外契约必须有对应的 schema 定义（前端 Zod / 后端 Pydantic）
  - **迁移可回滚性验证**（如适用）：
    - 如果任务涉及数据库 schema 变更，必须验证 `upgrade -> downgrade -> upgrade` 循环成功
    - 验收日志必须记录回滚验证的命令和结果
    - 如使用 Alembic，必须确保 `downgrade` 脚本与 `upgrade` 脚本配套完整
  - **性能基准验证**（如适用）：
    - 如果任务涉及性能敏感操作（如批量写入、复杂查询），必须提供性能基准数据
    - 验收日志必须记录关键操作的响应时间（P50/P95/P99）
    - 如果性能不达标，必须优化到满足要求或调整需求
  - **验收日志强制要求**：
    - 必须包含"零遗留项声明"章节，明确列出：
      - 所有审查问题的处理结果（已修复/不适用+原因）
      - 所有文档的完整性确认（API文档/错误码/配置项）
      - 所有测试的覆盖确认（单元测试/冒烟测试/回滚测试）
    - 如果存在任何未解决项，必须阻止任务标记完成


## 4) SecondBrainOS 工程约定（约定）

1. **文档权威来源**
   - 需求与架构（权威）：`sbo.md`（SecondBrainOS 需求与架构文档）
   - 需求（PRD）：`docs/requirements.md`
   - 任务（Implementation Plan）：`docs/tasks.md`
   - 设计：`docs/design.md`
   - API 契约：`docs/contracts/api-and-events-draft.md`

2. **Python 虚拟环境（强制）**
   - **强制使用项目根目录的 `.venv`** 作为 Python 虚拟环境；禁止直接使用系统 Python 或用户全局 site-packages。
   - 开发者本地创建（示例）：`python -m venv .venv`
   - 激活方式（示例）：
     - Linux/macOS：`source .venv/bin/activate`
   - **命令规范（强制）**：
     - 运行 Python/pytest/脚本时必须确保解析到 `.venv` 中的解释器与依赖（例如 `which python` 指向 `.venv/bin/python`）。
     - 安装依赖时必须使用 `.venv` 中的 `pip`（例如 `python -m pip ...` 且 `python` 来自 `.venv`）。
   - **验证命令执行要求（强制）**：当你在 IDE/终端执行 `pytest`、`python -m compileall`、`backend/scripts/*.py` 等验证命令时，必须在 `.venv` 已激活或明确使用 `.venv/bin/python` 的前提下执行，以保证结果可复现。

3. **工程结构（建议对齐仓库规范）**
   - 本仓库工程结构（以 SecondBrainOS 为准）：
     - `zip/`：前端原型（参考实现，不作为正式发布入口）
     - `backend/`：SecondBrainOS Core（FastAPI 后端 + RQ worker；Postgres(pgvector) + Neo4j + Redis）
     - `web/`：SecondBrainOS 独立应用前端（Vite + React + TypeScript + Tailwind；从 `zip/` 迁移复用 UI）
     - `docs/`：文档体系（PRD/设计/任务拆解/契约/验收）
     - `reports/`：验收日志与审查报告
     - `sbo.md`：SecondBrainOS 需求与架构权威文档
   - 约定：
     - `zip/` 仅作为原型参考；实现应落在 `backend/` 与 `web/`。
     - OpenClaw 为可选集成入口，不作为 SecondBrainOS Core 的运行时依赖。
     - `raw_events` 作为事实源 append-only（支持软删字段），其余派生表/索引可重建。
     - Neo4j 图谱可从 raw_events + extractions 重建（将图谱视为派生物）。

4. **默认验证命令（若任务未单独指定）**
   - 后端（`backend/`，Python/FastAPI + RQ）：
     - 优先运行任务内指定命令。
     - 若任务未指定：
       - **最低限度校验**：`python -m compileall backend`
       - **单元测试**：`pytest -q`（以 `backend/` 实际测试目录为准）
       - **冒烟测试**：必须覆盖真实链路（Postgres + Redis + Neo4j + 外部 embeddings/LLM API），由 `backend/scripts/*_smoke_test.py` 或等价脚本承载。
   - 前端（`web/`，Vite/React/TS）：
     - 优先运行任务内指定命令；否则运行 `npm run build`（在 `web/` 目录）。
   - 原型前端（`zip/`）：
     - 仅用于 UI 参考；如需验证，运行 `npm run build`（在 `zip/` 目录）。
   - 若对应目录未提供可运行脚本或依赖缺失，必须在验收日志中明确说明原因与补验收计划，**不得**直接标记完成。

5. **全局编码规范（强制）**
   - TypeScript Strict（**禁止 `any`**）
   - 契约与校验（单一事实源）：
     - 前端/TypeScript：对外输入输出使用 **Zod** 校验并从 schema 推导类型
     - 后端/Python：对外输入输出使用 **Pydantic** 模型作为单一事实源
   - 错误消息（message）必须用 **英文**（便于日志搜索）；注释可中文
   - API 使用 **REST**；如采用流式输出，优先使用 **Server-Sent Events (SSE)**，并确保事件/分片协议可契约化校验

6. **自动化验收原则（强制）**
   - 每个任务的 Verification 优先写成**可自动化断言**（单元/集成/契约测试），避免仅“手工目测”。
   - 契约相关（REST/SSE/Events/Streaming/Citation/Error）以本仓库 `docs/` 下的权威设计文档为准，并使用 schema 做断言（前端 Zod / 后端 Pydantic）。

7. **真实集成原则（强制）**
   - **所有代码必须使用真实服务进行集成和测试**
   - **所有测试必须针对真实服务运行**（如 RAGFlow、数据库、外部 API）
   - **禁止使用 mock**：不得使用 mock 对象、mock 服务、stub 等模拟真实服务的方式进行测试
   - **单元测试例外**：仅在单元测试中，为了隔离被测试单元，可以通过依赖注入传入测试专用的实现（如 fake fetch），但必须模拟真实行为和错误场景
   - 测试环境通过环境变量配置真实服务地址
   - **严格的失败策略**：当真实服务不可用或缺少配置时，测试必须失败并记录原因
     - **禁止 skip 策略**：不得使用 `test.skip()`、`describe.skip()`、条件跳过等任何形式的测试跳过
     - **配置缺失 => 测试失败**：按照本仓库 `docs/` 规范，缺少必需配置时测试必须抛出清晰错误并失败
     - **服务不可用 => 测试失败**：真实服务连接失败时测试必须失败，不得绕过或降级
     - **环境问题必须解决**：测试失败时必须修复环境配置或服务可用性，而非跳过测试
   - 集成测试必须验证完整的端到端流程

 8. **配置化开发原则（强制）**
   - **所有配置必须外部化**：URL、端口、超时时间、重试次数、API 密钥等配置项必须通过环境变量或配置文件管理
   - **禁止硬编码配置值**：代码中不得出现硬编码的 URL（如 `http://localhost:9999`）、端口号、超时时间、魔法数字等配置值
   - **使用统一的配置加载机制**：所有模块必须通过统一的配置加载函数（如 `loadRagflowConfig()`）获取配置，确保配置来源一致
   - **配置必须有 Zod 校验**：所有配置项必须定义 Zod schema 并在加载时校验，确保类型安全和完整性
   - **本地开发 `.env.local`（强制）**：
     - 配置读取优先级必须为：**进程环境变量** > **仓库根目录 `.env.local`**。
     - 运行时不得通过交互式提问来获取关键配置；关键配置缺失必须直接失败，并给出清晰的英文错误消息（例如缺少 `GANGQING_DATABASE_URL`）。
     - `.env.local` 仅用于本地开发与测试，不得提交到仓库；`.env.example` 必须完整列举所有必需与可选配置项。
   - **配置缺失时的处理**：
     - 开发/测试阶段：当检测到配置文件（`.env.local`）缺少必需的配置项时，AI 必须主动询问用户并协助补充配置
     - 运行时：关键配置缺失时必须抛出清晰的英文错误消息，说明缺失的配置项名称和获取方式
     - 可选配置可以有合理的默认值，但必须在文档中明确说明
   - **测试中的配置**：
     - 单元测试可以使用测试专用的配置对象（通过参数传入），但不得硬编码配置值
     - 集成测试必须从环境变量加载真实配置，配置缺失时测试失败
     - 测试辅助函数（如 fake fetch）可以接受配置参数，但调用方必须从配置系统获取值
   - **配置文档化**：所有配置项必须在 `.env.example` 中列出，并在 README 或相关文档中说明用途、默认值和获取方式

## 5) SecondBrainOS 项目专属约定（强制）

1. **核心技术栈（权威）**
   - **SecondBrainOS Core**：FastAPI + Redis Queue（RQ worker）
   - **存储层**：
     - Postgres（含 pgvector）：存储原始文本、系统元数据、状态/事实（JSONB + pgvector）
     - Neo4j：构建实体联系图谱（以 user_id 形成 Sub-graph）
     - Redis：缓存 + 队列
   - **大模型驱动层**：
     - 日常对话与路由：DeepSeek V3 / Llama-3（快速低成本）
     - 记忆归档与复杂推理：DeepSeek R1 / Claude 3.5 Sonnet / GPT-4o
   - **分层记忆框架**：
     - Agentic Memory：Mem0（专为 LLM 设计的自适应记忆层）
     - 知识图谱：Graphiti 或 LlamaIndex Property Graph
   - **embeddings**：硅基流动（SiliconFlow）API
   - **OpenClaw**：可选集成入口（多渠道/会话/工具编排），SecondBrainOS 必须可独立运行

2. **分层记忆架构（强制）**
   - **工作记忆（Working Memory）**：Context Window + Prompt Caching (CAG)，存储最近 1-7 天的对话上下文，极速响应
   - **语义记忆（Semantic/Agentic Memory）**：Redis / PostgreSQL，基于 Mem0 架构，存储用户的核心事实、状态、偏好
   - **情景记忆（Episodic Memory）**：GraphRAG (Neo4j) + Vector DB (pgvector)，海量日志、历史文档、会议记录，以"知识图谱 + 向量"混合存储

3. **OpenClaw 集成边界（强制）**
   - 禁止将核心记忆逻辑（抽取/冲突解决/回放/擦除权/图谱写入）放入 OpenClaw 内部实现。
   - OpenClaw 仅通过 skills/tools 调用 SecondBrainOS Core 的 HTTP API。
   - OpenClaw 不可用时，SecondBrainOS 仍需可独立使用（Web App + API）。
   - SecondBrainOS 不可用时，OpenClaw 仍应保持其原有能力可用（但 SecondBrainOS 相关功能会失败）。

4. **API 契约（最小 API 契约）**
   - **`POST /ingest`**：写入原始事件 + 入队
     - 入参：`source`、`source_message_id`、`occurred_at`、`content`、`tags`（可选）、`idempotency_key`（可选）
     - 出参：`event_id`、`queued_jobs`
   - **`POST /query`**：召回 + 证据
     - 入参：`query`、`top_k`、`time_range`（可选）、`mode`（fast/deep）
     - 出参：`answer_hint`（可选）、`evidence[]`（含 `evidence_id`、`type`、`text`、`occurred_at`、`source`、`confidence`、`refs`）
   - **`POST /forget`**：擦除权（异步）
     - 入参：按 `time_range` / `tags` / `event_ids`
     - 出参：`erase_job_id`（可查询状态）
   - **`GET /health`**：健康检查（检查 Postgres/Redis/Neo4j 连通性、队列积压）
   - **前端专用 API**：
     - `GET /memories`：拉取已巩固的记忆（供 Sidebar 展示）
     - `GET /conversations/{id}/messages`：拉取消息列表
     - `POST /chat`：发送用户消息并获得 assistant 回复 + `evidence[]`

5. **异步巩固任务拆分（Redis Queue / RQ）**
   - `consolidate_event(event_id)`：抽取结构化信息（实体/关系/偏好变化/待办等），写入 `extractions`
   - `upsert_profile(extraction_id)`：冲突解决 + 版本化（current + history）
   - `embed_event(event_id)`：生成 embedding 写入 pgvector
   - `upsert_graph(extraction_id)`：Neo4j MERGE 节点/关系（带 `source_event_id` 与时间戳）

6. **前端技术栈与状态模型**
   - **技术栈**：Vite + React + TypeScript + Tailwind
   - **状态模型**：
     - **Memory**：`id`、`content`、`type`（preference | fact | event）、`timestamp`
     - **Message**：`id`、`role`（user | assistant | system）、`content`、`timestamp`、`evidence?`（Evidence[]）
     - **Evidence**：`evidence_id`、`type`（raw_event | profile_fact | graph_fact）、`text`、`occurred_at`、`source`、`confidence`、`refs`
   - **API Client**：前端只调用 SecondBrainOS Core API，避免把业务逻辑散落在组件中
   - **证据展示 UI**：默认折叠，展开后按 `type` 分组展示（profile_fact、raw_event、graph_fact）

7. **自动召回护栏**
   - **阈值**：按 `confidence` 过滤低质量证据；默认只注入 top-N（如 3~8 条）
   - **缓存**：同一会话/相近 query 在短窗口内复用召回结果
   - **失败降级**：SecondBrainOS 不可用时，OpenClaw 直接正常聊天
   - **分档策略**：`mode=fast` 用 pgvector + 时间优先规则；`mode=deep` 才做图谱扩展与更昂贵的推理

8. **性能指标（强制）**
   - 文本响应时间：< 1.5 秒
   - 记忆入库延迟：异步处理，后台入库不超过 10 秒
   - 高频上下文缓存命中率：期望达到 80% 以上（利用长上下文 CAG 技术）

9. **鉴权与 Token（单用户场景）**
   - OpenClaw -> SecondBrainOS：允许复用 `OPENCLAW_GATEWAY_TOKEN` 作为 Bearer token（`Authorization: Bearer ...`）
   - Web 前端 -> SecondBrainOS：建议使用独立的登录/会话机制，与 OpenClaw token 分离

10. **关键配置项（必须外部化并在 `.env.example` 完整列出）**
    - Postgres：`DATABASE_URL`
    - Redis：`REDIS_URL`
    - Neo4j：`NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`
    - SiliconFlow：`SILICONFLOW_API_KEY`、`SILICONFLOW_BASE_URL`（如适用）、`SILICONFLOW_EMBEDDING_MODEL`
    - OpenClaw（可选）：`OPENCLAW_GATEWAY_TOKEN`
    - **LLM（本地 llama.cpp）**：`LLM_LLAMA_BASE_URL`、`LLM_LLAMA_API_KEY`、`LLM_LLAMA_MODEL_ID`
    - **LLM（外部 PROVIDER）**：`PROVIDER_API_KEY`、`PROVIDER_BASE_URL`、`PROVIDER_MODEL_ID`

11. **演进路线图（分阶段落地）**
    - **第一阶段：MVP（约 4 周）**：基础输入、Agentic 状态记忆和对话；暂不引入 GraphRAG；后端仅使用 PostgreSQL（文本 + JSONB + pgvector）
    - **第二阶段：完整形态（约 6-8 周）**：引入 Neo4j 和 GraphRAG 流程，解决复杂事件关联记忆；实现图片识别输入
    - **第三阶段：全知数字伴侣（长期）**：后台常驻定时触发 Agent；结合日历、GPS、健康数据主动推送提醒和建议

