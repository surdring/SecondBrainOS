# 2026-03-22 T1 访问计数/最后访问时间（evidence_access_stats）验收日志

## 目标

为 `POST /query` 增加证据访问统计的异步写入能力：

- 将 evidence 的 `access_count` 与 `last_accessed_at` 写入独立表 `evidence_access_stats`
- 写入在 `/query` 主响应返回后异步执行，不阻塞热路径
- 写入失败不影响主响应（降级为不记录统计）

## 变更摘要

- **数据模型**：新增表 `evidence_access_stats`（`user_id + evidence_id` 唯一）用于存储 `access_count`、`last_accessed_at`
- **写路径**：新增 `EvidenceAccessService.record_access()`，对每个 evidence 执行插入或自增更新
- **异步更新**：`QueryService.query()` 在构建完响应后，通过 `asyncio.create_task()` 异步触发 `record_access()`
- **测试**：新增/更新单元测试覆盖“异步触发且不阻塞响应”的行为
- **冒烟**：新增真实 Postgres 冒烟脚本验证迁移 + 写入自增逻辑

## 验证（自动化）

### 1) 语法/可编译性检查（compileall）

- **命令**

```bash
.venv/bin/python -m compileall backend
```

- **结果**

通过（exit code 0）。

### 2) 单元测试（Unit Test）

- **命令**（在 `backend/` 目录执行）

```bash
../.venv/bin/python -m pytest -q
```

- **覆盖要点**

- **异步写入触发**：`QueryService.query()` 会调用 `asyncio.create_task()`，并传入 `evidence_access_service.record_access()` 对应协程
- **不阻塞主响应**：主响应正常返回，异步任务在事件循环切换后执行

- **结果**

通过（全量测试 `100%` 通过）。

### 3) 数据库迁移回滚验证（upgrade -> downgrade -> upgrade）

- **命令**

```bash
.venv/bin/python -m pytest -q backend/tests/test_db_migrations_and_constraints.py::test_migrations_upgrade_downgrade_upgrade
```

- **结果**

通过。

### 4) 冒烟测试（Smoke Test，真实 Postgres）

#### 4.1 Postgres 基础可用性

- **命令**

```bash
.venv/bin/python backend/scripts/postgres_smoke_test.py
```

- **结果**

通过。

#### 4.2 evidence_access_stats 写入/自增/更新时间验证（临时 schema + 迁移到 head）

- **命令**

```bash
.venv/bin/python backend/scripts/evidence_access_stats_smoke_test.py
```

- **覆盖要点**

- 在临时 schema 中执行 `alembic upgrade head`
- 插入一条 `evidence_access_stats` 记录并将 `access_count` 更新为 `2`
- 更新 `last_accessed_at` 并断言为预期时间戳
- 测试结束后 drop 临时 schema

- **结果**

通过。

## 结论

- **功能**：`/query` 已支持在返回后异步更新证据访问统计（`access_count`/`last_accessed_at`）
- **一致性与可回放**：访问统计与事实源 `raw_events` 解耦，不破坏可回放原则
- **可靠性**：写入失败不影响主链路，单元测试与真实 Postgres 冒烟测试均已验证

## 零遗留项声明（Zero Technical Debt Policy）

- **阻断/严重/一般问题**：本任务范围内均已修复并完成验证
- **文档完整性**：本任务未新增/更新需求/设计类权威文档（仅新增验收日志与审查报告），无契约漂移风险
- **测试覆盖确认**：
  - 单元测试：已运行并通过
  - 冒烟测试（真实 Postgres）：已运行并通过
  - 迁移可回滚性验证：已运行并通过
