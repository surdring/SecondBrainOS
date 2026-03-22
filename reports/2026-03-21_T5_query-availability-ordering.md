# 查询可用性与顺序约束实现验收日志

## 任务信息
- **任务编号**: 3.4.4
- **任务名称**: 查询可用性与顺序约束实现
- **完成时间**: 2026-03-21
- **优先级**: P1

## 需求对齐（设计文档）
- **任何上游不可用时的降级**：rerank 失败必须降级到 fusion 结果（不影响整体返回）。
- **过滤顺序约束**：`hardMinScore` 必须发生在 time-decay/lifecycle 之前。
- **符号型查询保底**：对高置信 lexical 命中设置 preservation floor。
- **可解释性**：`evidence[].scores` 至少携带 `final_score`，并保留关键中间分数。

## 实现内容

### ✅ 1) 符号型查询保底（preservation floor）
- 在检索管线内新增符号型 query 判定 `_is_symbolic_query()`。
- 对符号型 query 且 `bm25_score` 高于阈值的候选：
  - 在 fusion 阶段应用 `preservation_floor`
  - 在 rerank 阶段再次应用，避免被重排拉低后淘汰

### ✅ 2) 顺序约束（hardMinScore before time-decay）
- 管线顺序保持为：
  - `fusion -> rerank -> normalization_and_filter(hardMinScore) -> time_lifecycle_rerank`
- 通过测试覆盖确保该顺序下的 `final_score` 可稳定落盘。

### ✅ 3) evidence 可解释性（评分字段）
- 在输出 evidence 前，写入：
  - `scores.final_score`
- 并保留/补齐：
  - `dense_score` / `lexical_score`（与 `semantic_score`/`bm25_score` 对齐）
  - `fusion_score`
  - `rerank_score`（若执行）
  - `preservation_floor_*`（若触发）

## 代码变更

### 📁 修改文件
- `backend/sbo_core/retrieval_pipeline.py`
  - 增加 `_is_symbolic_query()`
  - 增加 `preservation_floor` 相关参数与逻辑
  - 输出 evidence 前写入 `scores.final_score`

### 📁 测试变更
- `backend/tests/test_retrieval_pipeline.py`
  - 新增符号型查询 preservation floor 测试
  - 新增 `final_score` 写入断言
  - 适配 `_fusion/_optional_rerank` 新签名

### 📦 依赖落盘
- `backend/pyproject.toml`
  - dev 依赖新增 `pytest-asyncio`（保证异步测试可复现）

## 自动化验证

### ✅ 编译检查
```bash
.venv/bin/python -m compileall backend/sbo_core
```
结论：通过。

### ✅ 单元测试（覆盖关键约束）
```bash
.venv/bin/python -m pytest -q backend/tests/test_retrieval_pipeline.py backend/tests/test_query.py
```
结论：通过。

## 零遗留项声明
- 本任务范围内**无未处理的阻断/严重/一般问题**。
- 本任务实现**不保留 TODO** 类遗留项。
- 测试与编译均已实际运行并通过。

---

**验收结论**：✅ 3.4.4 完成，满足设计约束并通过自动化验证。
