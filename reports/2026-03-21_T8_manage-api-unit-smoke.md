# 验收日志：3.7 管理接口单元测试

- 日期：2026-03-21
- 任务：`.kiro/specs/second-brain-os/tasks.md` 中 **3.7 管理接口单元测试**
- 范围：管理接口 `/forget`、`/profile`、`/health`

## 变更摘要

- 新增单元测试：`backend/tests/test_manage.py`
- 修复迁移测试在仓库根目录执行时的 Alembic 路径解析问题：`backend/tests/test_db_migrations_and_constraints.py`
- 新增管理接口冒烟测试脚本：`backend/scripts/manage_api_smoke_test.py`
  - 支持在未显式设置环境变量时从 `backend/.env` 自动加载 `DATABASE_URL`/`POSTGRES_DSN`

## 验证与测试

### 1) 单元测试（Unit Test）

- 命令：

```bash
.venv/bin/python -m pytest -q backend/tests
```

- 结果：通过（exit code 0）
- 覆盖要点：
  - `GET /api/v1/health` 返回 `status=ok`
  - `GET /api/v1/profile` 与 `PUT /api/v1/profile` 正常往返更新
  - `POST /api/v1/forget` 创建擦除作业 + `GET /api/v1/forget/{id}` 状态查询
  - `GET /api/v1/forget/{id}` not found 返回 404 + `code=erase_job_not_found`

### 2) 冒烟测试（Smoke Test，真实服务）

- 前置条件：
  - `backend/.env` 已配置真实 `DATABASE_URL`（或通过环境变量显式设置 `POSTGRES_DSN`/`DATABASE_URL`）
  - Postgres 可连通

- 命令：

```bash
.venv/bin/python backend/scripts/manage_api_smoke_test.py
```

- 结果：通过（输出 `OK`，exit code 0）
- 覆盖链路：
  - 初始化真实数据库连接
  - 调用健康检查、档案读写、擦除作业创建与状态读取

## 证据与结论

- 结论：验收通过。
- 已将任务 **3.7** 在 `.kiro/specs/second-brain-os/tasks.md` 中标记为完成。

## 零遗留项声明（Zero Technical Debt Policy）

- 阻断性问题（Blocker）：无
- 严重问题（Critical）：无
- 一般问题（Major）：无
- 优化建议（Minor）：无

- 文档完整性确认：本任务不新增/更新对外契约文档；不触发“文档引用同步”要求。
- 回滚验证：不适用（本任务未新增迁移；但迁移相关测试已在单元测试集中通过）。
