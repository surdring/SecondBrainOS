# 验收日志：3.4.2-smoke WeKnora knowledge-search 冒烟测试

- 日期：2026-03-21
- 任务：TODO 列表中的 **3.4.2-smoke WeKnora knowledge-search 冒烟测试**
- 目标：验证 WeKnora `/knowledge-search` 在真实服务上可调用，并满足“必须提供 knowledge_base_id(s)”的约束

## 变更摘要

- 更新 `backend/.env`
  - 增加 `WEKNORA_KNOWLEDGE_BASE_ID=kb-00000001`，确保 knowledge-search 请求满足 WeKnora API 必填约束

## 验证与测试

### 冒烟测试（Smoke Test，真实 WeKnora）

- 命令：

```bash
.venv/bin/python backend/scripts/weknora_knowledge_search_smoke_test.py
```

- 环境：
  - `backend/.env` 中 `WEKNORA_BASE_URL`、`WEKNORA_API_KEY`、`WEKNORA_REQUEST_TIMEOUT_MS` 已配置
  - `WEKNORA_KNOWLEDGE_BASE_ID=kb-00000001`

- 结果：通过（exit code 0）

## 证据与结论

- 结论：验收通过。
- 关键点：WeKnora 在未提供 `knowledge_base_id(s)` 时会返回 HTTP 400（"At least one knowledge_base_id, knowledge_base_ids or knowledge_ids must be provided"），本次通过环境变量补齐后请求成功。

## 零遗留项声明（Zero Technical Debt Policy）

- 阻断性问题（Blocker）：无
- 严重问题（Critical）：无
- 一般问题（Major）：无
- 优化建议（Minor）：无

- 文档完整性确认：本任务不新增/更新对外契约文档；不触发“文档引用同步”要求。
- 回滚验证：不适用（本任务仅为冒烟测试与环境变量补齐）。
