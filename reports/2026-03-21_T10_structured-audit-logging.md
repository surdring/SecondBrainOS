# 验收日志：3.6.2 结构化审计日志（范围对齐设计约束）

- 日期：2026-03-21
- 任务：`.kiro/specs/second-brain-os/tasks.md` 中 **3.6.2 结构化审计日志（范围对齐设计约束）**
- 范围：管理接口（/forget、/profile）与 WeKnora Episodic recall 的结构化审计日志

## 变更摘要

- 新增结构化审计日志工具：`backend/sbo_core/audit.py`
  - `audit_log(event, outcome, request_id, details)` 统一输出结构化字段
- 管理接口补齐审计日志：`backend/sbo_core/routes/manage.py`
  - `/forget` 创建与状态查询：success/fail/error
  - `/profile` 读取与更新：success/fail/error
- WeKnora recall 补齐审计日志：`backend/sbo_core/retrieval_pipeline.py`
  - `weknora.recall`：success/fail/degrade
- 修复 sqlite 内存库单测稳定性：`backend/sbo_core/database.py`
  - `sqlite:///:memory:` 使用 `StaticPool`，确保建表连接与后续 session 连接一致
- 修复单测重复初始化真实数据库的问题：`backend/sbo_core/app.py`
  - 若已 `init_database()`，则不再用 settings 覆盖初始化

## 验证与测试

### 1) 单元测试（Unit Test）

- 命令：

```bash
.venv/bin/python -m pytest -q backend/tests
```

- 结果：通过（exit code 0）
- 覆盖要点：
  - 新增 `backend/tests/test_audit_logging.py`
    - 验证 `POST /api/v1/forget` 会输出 `audit_event=forget.create`、`audit_outcome=success` 且包含 `erase_job_id`
    - 验证 WeKnora episodic recall 成功会输出 `audit_event=weknora.recall`、`audit_outcome=success` 且 `candidates_out=1`

### 2) 冒烟测试（Smoke Test，真实服务）

- 前置条件：
  - `backend/.env` 配置真实 `DATABASE_URL`（或环境变量 `POSTGRES_DSN`/`DATABASE_URL`）
  - Postgres 可连通

- 命令：

```bash
.venv/bin/python backend/scripts/manage_api_smoke_test.py
```

- 结果：通过（输出 `OK`，exit code 0）

## 证据与结论

- 结论：验收通过。
- 已将任务 **3.6.2** 在 `.kiro/specs/second-brain-os/tasks.md` 中标记为完成。

## 零遗留项声明（Zero Technical Debt Policy）

- 阻断性问题（Blocker）：无
- 严重问题（Critical）：无
- 一般问题（Major）：无
- 优化建议（Minor）：无

- 文档完整性确认：本任务不新增/更新对外契约文档；不触发“文档引用同步”要求。
- 回滚验证：不适用（本任务未新增迁移）。
