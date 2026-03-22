# 2026-03-22 T1 访问计数/最后访问时间（evidence_access_stats）代码审查报告

## 审查范围

- `backend/sbo_core/query_service.py`：`/query` 后异步触发访问统计写入
- `backend/sbo_core/services.py`：`EvidenceAccessService.record_access()` 写路径
- `backend/sbo_core/database.py`：`EvidenceAccessStats` ORM 模型
- `backend/alembic/versions/0003_add_evidence_access_stats_table.py`：迁移脚本
- `backend/tests/test_query.py`：异步写入触发的单元测试
- `backend/scripts/evidence_access_stats_smoke_test.py`：真实 Postgres 冒烟脚本

## 结论

- **总体结论**：通过（可合入）。
- **风险等级**：低。

## 审查维度与发现

### 1) 正确性（Correctness）

- **发现**
  - `EvidenceAccessService.record_access()` 对 `user_id + evidence_id` 执行“插入或自增更新”，符合访问计数语义。
  - `QueryService.query()` 使用 `asyncio.create_task()` 异步触发写入，满足“不阻塞热路径”。

- **结果**
  - 通过。

### 2) 可靠性与降级策略（Reliability/Degradation）

- **发现**
  - 写入异常会捕获并记录日志，返回 `0`，不会中断主请求。
  - 单元测试覆盖了异步触发行为，且避免 DB 未初始化导致的测试脆弱性。

- **结果**
  - 通过。

### 3) 数据一致性与可回放原则（Replayability）

- **发现**
  - 访问统计未写入 `raw_events`，而是落在独立表 `evidence_access_stats`，符合“事实源 append-only，可派生重建”的设计约束。

- **结果**
  - 通过。

### 4) 性能与资源使用（Performance）

- **发现**
  - 当前 `record_access()` 逐条 evidence 做一次 ORM 查询 + 更新，`top_k` 较大时会有额外 DB 往返。
  - 由于其异步执行且不阻塞主响应，功能层面满足要求；但仍建议后续可优化为批量 UPSERT（非本任务强制）。

- **结果**
  - 通过（无阻断问题）。

### 5) 安全性（Security）

- **发现**
  - 写入路径只依赖 `user_id` 与 `evidence_id`，无直接拼接用户输入到 SQL（服务侧使用 ORM；冒烟脚本使用固定 schema 名称与参数化写入）。

- **结果**
  - 通过。

### 6) 可测试性（Testability）

- **发现**
  - 单元测试验证“异步任务被创建且最终执行”。
  - 冒烟脚本在真实 Postgres + 临时 schema 下验证迁移与写入行为，满足真实集成原则。

- **结果**
  - 通过。

## 问题清单与处理结果（必须 0 遗留）

- 🔴 Blocker：无
- 🟠 Critical：无
- 🟡 Major：无
- 🟢 Minor：无
