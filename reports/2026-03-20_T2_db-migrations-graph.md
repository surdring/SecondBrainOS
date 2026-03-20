# 验收日志：数据库迁移与图谱模型（T2）

- 日期：2026-03-20
- 任务范围：`.kiro/specs/second-brain-os/tasks.md` 中 **2.1 ~ 2.6**（其中 2.4.1 未实现，仍保持未勾选）
- 代码范围：`backend/`

## 1. 交付物清单

- PostgreSQL 迁移与数据模型（Alembic）
  - `backend/alembic.ini`
  - `backend/alembic/env.py`
  - `backend/alembic/versions/0001_init_core_tables.py`
- 迁移可回滚性验证（冒烟）
  - `backend/scripts/postgres_migration_smoke_test.py`
- 数据模型与迁移单元测试（真实 Postgres）
  - `backend/tests/test_db_migrations_and_constraints.py`
- Neo4j 图谱模型（节点/关系 + user_id 子图隔离）
  - `backend/sbo_core/neo4j_graph.py`
- Neo4j 图数据库集成测试（真实 Neo4j）
  - `backend/tests/test_neo4j_graph_isolation.py`
- 测试环境加载一致性修复（对齐 .env force override 行为）
  - `backend/tests/conftest.py`

## 2. 数据模型验收要点

### 2.1 `raw_events`（事实源）

- append-only 语义：通过 `deleted_at` 支持软删；不在迁移中引入更新覆写事实源的约束（事实源可回放）。
- 幂等/去重：
  - `idempotency_key` 存在时唯一（部分唯一索引）
  - `(source, source_message_id)` 存在时唯一（部分唯一索引）

### 2.2 `extractions`（结构化提取）

- 可追溯：`event_id -> raw_events.event_id`
- 置信度范围约束：`confidence` 必须在 `[0,1]`

### 2.3 `user_profiles`（当前态）+ `user_profile_versions`（历史版本）

- current：`user_profiles`
- history：`user_profile_versions` 通过 `(user_id, version)` 唯一索引约束版本号

### 2.4 `embeddings`（pgvector）

- `embedding vector(1536)`
- `ivfflat` 向量索引（cosine ops）

### 2.5 擦除作业与审计（2.6）

- `erase_jobs`：
  - `status` 受 CHECK 约束：`queued|running|succeeded|failed`
  - `request/summary` JSONB 记录范围与结果摘要
- `erase_job_items`：
  - `action` 受 CHECK 约束：`soft_delete|hard_delete`
  - `status` 受 CHECK 约束：`queued|running|succeeded|failed`

### 2.6 Neo4j 图谱模型（2.4 / 2.5）

- 节点类型：`Person` / `Event` / `Location` / `Thing`
- 关系类型：
  - `PARTICIPATED_IN`
  - `OCCURRED_AT`
  - `RELATED_TO`
  - `KNOWS`
- 隔离策略：所有节点与关系都强制携带 `user_id`，并且在数据库层为每个节点 label 建立 `(user_id, entity_id)` 唯一约束。

## 3. 自动化验证（强制）

> 说明：所有验证均为真实服务集成（Postgres/Redis/Neo4j），未使用 mock。

### 3.1 单元测试（Unit Test）

在 `backend/` 目录执行：

- 命令：`../.venv/bin/python -m pytest -q`
- 结果：PASS

覆盖摘要：
- 迁移可回滚循环（upgrade→downgrade→upgrade）
- 幂等/去重唯一性约束（UniqueViolation）
- `confidence` CHECK 约束（CheckViolation）
- `erase_jobs/erase_job_items` CHECK 约束（CheckViolation）
- Neo4j 子图隔离（user_id 维度节点/关系 CRUD）

### 3.2 冒烟测试（Smoke Test）

在 `backend/` 目录执行：

- Postgres：`../.venv/bin/python scripts/postgres_smoke_test.py` -> PASS
- Redis：`../.venv/bin/python scripts/redis_smoke_test.py` -> PASS
- Neo4j：`../.venv/bin/python scripts/neo4j_smoke_test.py` -> PASS
- 迁移回滚循环：`../.venv/bin/python scripts/postgres_migration_smoke_test.py` -> PASS

## 4. 关键问题与修复记录（零遗留项要求）

- 已修复：Alembic 迁移执行后未提交导致 DDL 回滚（表现为 upgrade 日志成功但无任何表落地）。
  - 修复方式：在 `alembic/env.py` 在线迁移完成后显式 `commit()`，确保 DDL 与 `alembic_version` 持久化。
- 已修复：pytest 与冒烟脚本对 `.env` 覆盖策略不一致导致 Neo4j 认证失败。
  - 修复方式：`backend/tests/conftest.py` 对 Neo4j 关键变量采用 `force_override` 与冒烟脚本对齐。

## 5. 零遗留项声明

- 阻断性问题（Blocker）：无
- 严重问题（Critical）：无
- 一般问题（Major）：无
- 优化建议（Minor）：无（未留下 TODO/后续补充）

## 6. 未包含在本次范围的任务

- `2.4.1`（Neo4j/GraphRAG 可选增强开关与 `mode=deep` 的可用性探测/降级策略）：未实现，任务清单仍保持未勾选。
