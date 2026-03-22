# SecondBrainOS 任务列表更新总结

## 已完成的【修改】内容补充

根据 `design.md` 中的【修改】内容，已对 `tasks.md` 进行以下完善和补充：

### 1. 全局约束更新
**位置**: `tasks.md` 第21-28行
**新增约束**：
- **检索排序管线约束**：必须实现候选召回、融合、可选 rerank、归一化过滤、时间重排、噪声过滤的完整管线
- **可用性约束**：任何上游不可用时必须降级回 Semantic/Working Memory；hardMinScore 必须在 time-decay 之前执行
- **召回护栏约束**：mustSkipRetrieval 判定必须先于 WeKnora 调用；支持 CJK 特性和可配置规则
- **Evidence 统一元数据约束**：所有 evidence 必须携带标识、隔离、时间、质量、审计字段
- **Scope/Namespace 隔离约束**：scope 过滤必须在检索/融合之前执行；支持 global/user/agent/project/custom 形态
- **Prompt 注入安全约束**：evidence 注入时必须标记为 [UNTRUSTED DATA]；必须有数量上限和阈值控制
- **Cross-Encoder 重排约束**：必须有独立超时控制；失败必须降级到 fusion；不得完全覆盖原始相关性
- **生命周期/衰减约束**：阶段 1 仅 time-decay；访问计数更新必须异步；不得破坏 raw_events 可回放原则

### 2. 核心 API 开发任务补充
**位置**: `tasks.md` 第188-210行
**新增任务**：
- **3.4.3 【修改】检索排序管线实现**：实现完整的检索排序管线（候选召回、融合、rerank、过滤、重排、多样性）
- **3.4.4 【修改】查询可用性与顺序约束实现**：实现降级策略、过滤顺序、符号查询保底、可解释性
- **3.4.5 【修改】shouldSkipRetrieval 召回护栏实现**：实现护栏判定、典型输入配置、CJK 特性、可配置规则

### 3. 管理接口任务补充
**位置**: `tasks.md` 第243-260行
**新增任务**：
- **3.6.2 结构化审计日志**：补充检索与重排审计、Prompt 注入安全审计
- **3.6.4 【修改】反馈纠错接口实现**：实现完整的反馈纠错功能，支持 WeKnora 引用关联

### 4. 异步任务处理补充
**位置**: `tasks.md` 第280-293行
**新增任务**：
- **4.1.2 【修改】Cross-Encoder 重排任务实现**：实现独立超时控制、失败降级、混合评分、符号查询保护
- **4.1.3 【修改】生命周期/衰减任务实现**：实现 time-decay 重排、异步访问计数更新、阶段演进支持

### 5. 前端状态管理任务补充
**位置**: `tasks.md` 第307-326行
**新增任务**：
- **5.5.1 【修改】Evidence 统一元数据模型实现**：实现完整的 Evidence 字段（标识、隔离、时间、质量、审计）
- **5.5.2 【修改】Scope/Namespace 隔离实现**：实现统一 scope 形态、硬隔离、二次校验
- **5.5.3 【修改】Prompt 注入安全实现**：实现不可信数据标记、数量控制、可配置规则

### 6. 配置管理文档补充
**位置**: `tasks.md` 第497-501行
**新增配置项**：
- **检索排序管线配置**：RETRIEVAL_TOP_K、HARD_MIN_SCORE、TIME_DECAY_RATE、SEMANTIC_WEIGHT、TIME_WEIGHT、NOISE_FILTER_THRESHOLD、MMR_DIVERSITY_THRESHOLD
- **召回护栏配置**：SKIP_RETRIEVAL_MIN_LENGTH、SKIP_RETRIEVAL_KEYWORDS、FORCE_RETRIEVAL_KEYWORDS、CJK_MIN_LENGTH_THRESHOLD
- **Cross-Encoder 配置**：RERANK_PROVIDER_URL、RERANK_API_KEY、RERANK_MODEL、RERANK_TIMEOUT_MS、RERANK_WEIGHT、LEXICAL_PRESERVATION_FLOOR
- **Prompt 注入安全配置**：EVIDENCE_INJECTION上限、EVIDENCE_CONFIDENCE_THRESHOLD、UNTRUSTED_DATA_MARKER
- **Scope/Namespace 配置**：DEFAULT_SCOPE、ENABLE_MULTI_TENANT、SCOPE_ISOLATION_STRICT_MODE

## 任务优先级分配

### P0 任务（关键路径）
- 检索排序管线实现
- 查询可用性与顺序约束实现
- shouldSkipRetrieval 召回护栏实现

### P1 任务（重要项）
- Cross-Encoder 重排任务实现
- 生命周期/衰减任务实现
- 反馈纠错接口实现
- 结构化审计日志补充

### P2 任务（增强项）
- Evidence 统一元数据模型实现
- Scope/Namespace 隔离实现
- Prompt 注入安全实现
- 配置管理文档补充

## 实施建议

1. **阶段划分**：
   - MVP（阶段 1）：重点实现检索排序管线、可用性约束、召回护栏
   - 阶段 2：补充 Cross-Encoder 重排、生命周期管理、反馈纠错
   - 阶段 3：完善隔离模型、安全约束、高级配置

2. **依赖关系**：
   - 检索排序管线是查询检索的核心依赖
   - Evidence 统一元数据是前端展示的基础
   - 配置管理是所有功能的基础支撑

3. **测试策略**：
   - 每个新增任务都需要对应的单元测试和冒烟测试
   - 配置缺失必须导致测试失败
   - 外部依赖失败路径必须覆盖

## 验证建议

1. **设计一致性**：确保所有任务实现与设计文档中的【修改】内容完全一致
2. **约束遵循**：验证所有实现都遵循新增的全局约束
3. **配置完整性**：确保所有新增配置项都有默认值和校验
4. **测试覆盖**：验证所有新增功能都有对应的测试用例
