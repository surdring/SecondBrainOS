# 验收日志：T1 后端虚拟环境与冒烟测试

- 日期：2026-03-20
- 范围：后端 `.venv` 安装（含 dev 依赖）、单元测试、静态检查（compileall）、冒烟测试（Postgres/Redis/Neo4j/WeKnora/SiliconFlow embeddings/LLM provider）

## 变更摘要

- 修正文档 `AGENTS.md`：明确 `.venv` 位于仓库根目录，`backend/` 下需使用 `../.venv/bin/python`。
- 安装后端依赖（含 dev）：用于补齐 `pytest/httpx` 等测试依赖。
- 添加开发工具配置（问题清单第 12 条）：
  - 新增 `.editorconfig` 统一换行/缩进/去尾随空格等基础编辑器行为。
  - 新增 `.pre-commit-config.yaml` 并以 **离线可用** 的 `repo: local` 形式落地基础钩子与 `ruff` 检查（避免环境无法访问 GitHub 时无法初始化 hooks）。
  - `backend[dev]` 增补 `pre-commit` 与 `ruff`，保证在 `.venv` 中可复现运行。
- 修复冒烟脚本 `.env` 读取覆盖策略，避免旧环境变量或重复键导致读取到空值/旧值：
  - `backend/scripts/neo4j_smoke_test.py`
  - `backend/scripts/siliconflow_embeddings_smoke_test.py`
  - `backend/scripts/provider_llm_smoke_test.py`
- `provider_llm_smoke_test.py`：在 `PROVIDER_*` 未配置时回退到 `LLM_LLAMA_*`，匹配当前 `backend/.env` 的实际配置方式。

## 自动化验证

### 1) 依赖安装（真实环境）

- 命令（仓库根目录）：
  - `.venv/bin/pip install -e "backend[dev]"`
- 结果：PASS（exit code 0）
- 关键点：`httpx` 已安装，用于 `fastapi.testclient`。

### 2) 静态检查（compileall）

- 命令（仓库根目录）：
  - `.venv/bin/python -m compileall backend`
- 结果：PASS（exit code 0）

### 3) 单元测试（Unit Test）

- 命令（在 `backend/` 目录）：
  - `../.venv/bin/python -m pytest -q`
- 结果：PASS（13 passed）

### 4) 冒烟测试（Smoke Test，真实服务/外部 API）

- Postgres：
  - `../.venv/bin/python scripts/postgres_smoke_test.py`
  - 结果：PASS
- Redis（含 RQ enqueue）：
  - `../.venv/bin/python scripts/redis_smoke_test.py`
  - 结果：PASS
- WeKnora：
  - `../.venv/bin/python scripts/weknora_smoke_test.py`
  - 结果：PASS
- Neo4j：
  - `../.venv/bin/python scripts/neo4j_smoke_test.py`
  - 结果：PASS
- SiliconFlow embeddings（外部请求）：
  - `../.venv/bin/python scripts/siliconflow_embeddings_smoke_test.py`
  - 结果：PASS
- LLM provider（外部/本地 OpenAI-compatible 请求）：
  - `../.venv/bin/python scripts/provider_llm_smoke_test.py`
  - 结果：PASS

### 5) 开发工具配置校验（pre-commit）

- 命令（仓库根目录）：
  - `.venv/bin/pre-commit run --all-files`
- 结果：PASS

## 关键链路覆盖说明

- **成功路径**：
  - Postgres 连接与基础能力验证
  - Redis 连接、RQ 入队验证
  - Neo4j 连接与基础查询验证
  - WeKnora 连通性/鉴权验证
  - embeddings 请求（SiliconFlow）
  - chat completion 请求（OpenAI-compatible provider / LLM_LLAMA 回退路径）

## 安全与配置完整性检查

- `.gitignore` 已恢复对 `.env`/`.env.local`/`.env.*.local` 的忽略规则，避免误提交密钥。
- `zip/.gitignore` 已恢复对 `.env*` 的忽略规则（保留 `!.env.example`）。
- `backend/.env.example` 未包含真实密钥（`SILICONFLOW_API_KEY` 为空）。

## 零遗留项声明（Zero Technical Debt Policy）

- **阻断/严重/一般问题**：无遗留，均已修复或验证通过。
- **文档完整性**：本次涉及的环境与验证命令说明已在 `AGENTS.md` 中更新。
- **测试覆盖**：
  - 单元测试：已运行并通过。
  - 冒烟测试：已运行并通过（包含真实服务与外部 API）。
- **未完成项**：无。
