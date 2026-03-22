# SecondBrainOS 设计文档更新总结

## 已完成的【修改】内容补充

根据 `requirements.md` 中的【新增】内容，已对 `design.md` 进行以下完善和补充：

### 1. 检索排序管线（统一抽象，agent-agnostic）
**位置**: `design.md` 第429-460行
**内容**:
- 候选召回（可并行）：Semantic + Episodic + （可选）Graph
- 融合（fusion）：dense 为主，lexical/BM25 保底
- 可选 rerank（cross-encoder）：失败必须降级到 fusion 结果
- 归一化与过滤：length normalization + hardMinScore
- 时间与生命周期重排：time-decay / recency boost
- 噪声过滤与多样性：noise filter + MMR diversity

### 2. 可用性与顺序约束
**位置**: `design.md` 第455-460行
**内容**:
- 任何上游不可用时的降级策略
- 过滤顺序约束（hardMinScore 必须在 time-decay 之前）
- 符号型查询保底策略
- 可解释性要求（evidence[] 必须携带关键评分信息）

### 3. Cross-Encoder 重排与降级策略
**位置**: `design.md` 第78-91行
**内容**:
- 独立性要求（不得成为强依赖，独立超时控制）
- 失败降级（必须降级回 fusion 并记录原因）
- 混合评分（rerank 分数不应完全覆盖原始相关性）
- 符号查询保护（对高 BM25/lexical 命中设置保底阈值）

### 4. shouldSkipRetrieval（召回护栏）与噪声过滤
**位置**: `design.md` 第131-134行
**内容**:
- 护栏判定必须先于 WeKnora 调用
- 跳过/强制 Deep Retrieval 的典型输入
- CJK 特性（中文短 query 策略）
- 可配置要求（阈值、关键词列表等）

### 5. Evidence 统一元数据中枢规范
**位置**: `design.md` 第627-650行
**内容**:
- 标识字段：evidence_id、type、refs
- 隔离字段：user_id、project_id、scope
- 时间字段：occurred_at（优先）、created_at（次之）
- 质量字段：confidence、scores（dense/bm25/rerank/final）
- 审计字段：request_id、retrieval_trace

### 6. Scope/Namespace 隔离模型
**位置**: `design.md` 第337-362行
**内容**:
- 统一 scope 形态（global、user、agent、project、custom）
- 硬隔离要求（scope 过滤必须在检索/融合之前）
- 统一字段要求（所有 evidence 必须携带隔离标识）
- 二次校验（多用户/多租户形态的校验要求）

### 7. Prompt 注入安全约束
**位置**: `design.md` 第353-362行
**内容**:
- 不可信数据标记（[UNTRUSTED DATA]）
- 注入数量控制（top-N 上限与阈值过滤）
- 可配置要求

### 8. 检索与重排审计要求
**位置**: `design.md` 第226-229行
**内容**:
- rerank 审计（记录执行状态、provider、降级原因）
- Prompt 注入安全（不可信数据语义注入）

### 9. 生命周期/衰减（分阶段落地约束）
**位置**: `design.md` 第231-243行
**内容**:
- 阶段 1：仅 time-decay re-ranking
- 阶段 2：引入 access_count/last_accessed_at
- 事实源优先（不破坏 raw_events 可回放原则）
- 写入点约束（异步记录，避免热路径延迟）

## 更新特点

1. **标记清晰**：所有修改内容都明确标记为【修改】
2. **结构完整**：按照设计文档的逻辑结构进行组织
3. **内容对齐**：严格对应需求文档中的新增要求
4. **技术可行**：所有设计内容都具备可实现性
5. **向后兼容**：新增内容不影响现有架构设计

## 验证建议

建议进行以下验证：
1. 对照需求文档逐项检查修改内容是否完整
2. 技术评审验证修改设计的可行性
3. 架构一致性检查确保修改内容与现有设计协调
4. 实施优先级评估（MVP vs 阶段2/3）
