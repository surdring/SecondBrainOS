# 验收日志：3.4.2 WeKnora Episodic 检索对接（Deep Mode）

- 日期：2026-03-21
- 任务：`.kiro/specs/second-brain-os/tasks.md` 中 **3.4.2 WeKnora Episodic 检索对接（Deep Mode）**

## 变更摘要

- WeKnora 客户端：`backend/sbo_core/weknora_client.py`
  - 支持 `/knowledge-search` 调用
  - 超时/不可用/鉴权失败的错误映射
  - 支持 `knowledge_base_id` 或 `knowledge_base_ids`
- Episodic recall 集成：`backend/sbo_core/retrieval_pipeline.py`
  - Deep 模式并发召回（Semantic + WeKnora）并进入统一管线
  - Time-Decay 二次重排：`final_score = weknora_score*semantic_weight + exp(-decay_rate*days_ago)*time_weight`
  - WeKnora 失败按策略 fail/degrade，并记录 `degraded_services`
- 冒烟测试：
  - `backend/scripts/weknora_knowledge_search_smoke_test.py`（验证 knowledge-search 端点）
  - `backend/scripts/deep_query_weknora_smoke_test.py`（验证 `/api/v1/query mode=deep` 端到端）

## 验证与测试

### 1) 单元测试（Unit Test）

- 命令：

```bash
.venv/bin/python -m pytest -q backend/tests
```

- 结果：通过（exit code 0）
- 覆盖要点：
  - WeKnora episodic recall 成功/鉴权失败降级等路径均有覆盖

### 2) 冒烟测试（Smoke Test，真实服务）

#### 2.1 WeKnora knowledge-search

- 命令：

```bash
.venv/bin/python backend/scripts/weknora_knowledge_search_smoke_test.py
```

- 结果：通过（exit code 0）

#### 2.2 Deep 查询端到端（含 WeKnora）

- 命令：

```bash
.venv/bin/python backend/scripts/deep_query_weknora_smoke_test.py
```

- 结果：通过（输出 `OK`，exit code 0）

## 证据与结论

- 结论：验收通过。
- 已将任务 **3.4.2** 在 `.kiro/specs/second-brain-os/tasks.md` 中标记为完成。

## 零遗留项声明（Zero Technical Debt Policy）

- 阻断性问题（Blocker）：无
- 严重问题（Critical）：无
- 一般问题（Major）：无
- 优化建议（Minor）：无

- 文档完整性确认：本任务不新增/更新对外契约文档；不触发“文档引用同步”要求。
- 回滚验证：不适用（本任务未新增迁移）。
