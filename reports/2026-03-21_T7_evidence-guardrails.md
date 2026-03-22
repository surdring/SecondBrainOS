# 验收日志：3.4.1 Evidence 证据模型与护栏实现

- **日期**：2026-03-21
- **任务**：3.4.1 Evidence 证据模型与护栏实现
- **范围**：`POST /api/v1/query` 查询链路的 `evidence[]` 输出护栏（阈值过滤、top-N 裁剪、短窗口缓存复用）

## 交付内容

### 1) evidence[] 字段契约对齐
- **字段集合**：`evidence_id/type/text/occurred_at/source/confidence/refs`
- **实现位置**：
  - `backend/sbo_core/retrieval_pipeline.py`：`RetrievalCandidate.to_evidence()` 统一生成 `Evidence`
  - `backend/sbo_core/models.py`：`Evidence` Pydantic 模型定义（额外包含 `scores/request_id/retrieval_trace`，不影响既有字段集合）

### 2) 护栏：阈值过滤 + top-N 裁剪
- **阈值过滤**：按 `confidence`（对应 pipeline 的 `final_score`）过滤低置信度证据
- **top-N 裁剪**：对最终 evidence 数量做上限裁剪
- **默认策略**：
  - `min_confidence = 0.3`
  - `max_items = 8`
- **实现位置**：`backend/sbo_core/query_service.py`：`_apply_evidence_guardrails()`

### 3) 护栏：短窗口缓存复用（同会话/相近 query）
- **Key**：`conversation_id + normalize(query)`
- **normalize(query)**：去首尾空白、lower、折叠空格
- **TTL**：10 秒
- **最大条目数**：128（超过后淘汰最旧条目）
- **实现位置**：`backend/sbo_core/query_service.py`：`_cache_get/_cache_set/_normalize_query` + `query()` 热路径命中短路

## 验证与测试

### 单元测试（已运行）
- **命令**：
  - `./.venv/bin/python -m pytest -q backend/tests/test_query.py`
- **覆盖点**：
  - **护栏过滤与裁剪**：低于阈值的 evidence 被过滤，且最终最多 8 条
  - **缓存复用**：同一 `conversation_id` 下，归一化后相同 query 的第二次调用不触发检索管线重复执行
- **结果**：PASS

### 冒烟测试（说明）
- 本任务为 **服务内存级护栏与缓存**，不依赖外部服务即可单元级验证；冒烟测试覆盖在 `POST /api/v1/query` 的整体链路（已在既有查询接口任务中验证）。

## 关键实现文件
- `backend/sbo_core/query_service.py`
- `backend/tests/test_query.py`

## 零遗留项声明（Zero Technical Debt Policy）
- **阻断性问题（Blocker）**：无
- **严重问题（Critical）**：无
- **一般问题（Major）**：无
- **优化建议（Minor）**：无
- **文档完整性确认**：本任务不新增对外 API 文档；契约以 `models.py` 为准
- **测试覆盖确认**：单元测试已运行并通过；与外部依赖无关
