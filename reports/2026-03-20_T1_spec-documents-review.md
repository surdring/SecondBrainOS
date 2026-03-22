# 代码审查报告 - SecondBrainOS Spec 文档审查

## 审查概要
- 审查时间：2026-03-20
- 审查范围：requirements.md、design.md、tasks.md
- 权威参考：sbo.md、INTEGRATION_WEKNORA_EpisodicMemory.md、BORROWING_memory-lancedb-pro.md
- 审查结果：有条件通过（需要修复阻断性问题）

## 问题清单

### 🔴 阻断性问题（5）

#### 1. WeKnora 集成策略不一致
**位置**：requirements.md 3.2.3、design.md 3.2.3
**问题**：权威文档明确 WeKnora 作为 Episodic Memory 的"检索与理解层"，但 spec 文档中仍有"Neo4j 图谱构建"等表述，与权威约束冲突
**影响**：可能导致重复实现文档解析/分块/混合检索功能
**建议**：
- 明确 WeKnora 承担所有 Episodic Memory 的检索与理解功能
- Neo4j 仅作为可选增强（通过 WeKnora GraphRAG profile 启用）
- 删除 SBO Core 内部实现文档解析的相关描述

#### 2. 检索排序管线缺失关键约束
**位置**：requirements.md 3.1.2、design.md 3.4
**问题**：缺少 BORROWING_memory-lancedb-pro.md 中定义的关键检索管线约束
**影响**：无法实现 agent-agnostic 的统一检索排序管线
**建议**：
- 补充候选召回（可并行）、融合（dense 为主，lexical 保底）
- 补充可选 rerank（cross-encoder，失败降级）
- 补充归一化过滤（length normalization + hardMinScore）
- 补充时间重排和噪声过滤（MMR diversity）

#### 3. shouldSkipRetrieval 召回护栏缺失
**位置**：requirements.md 5.6、design.md
**问题**：缺少 BORROWING_memory-lancedb-pro.md 中定义的召回护栏机制
**影响**：无法避免不必要的外部请求与延迟
**建议**：
- 补充护栏判定逻辑（先于 WeKnora 调用）
- 补充跳过/强制 Deep Retrieval 的典型输入规则
- 补充 CJK 特性支持和可配置规则

#### 4. Cross-Encoder 重排策略缺失
**位置**：design.md、tasks.md
**问题**：缺少 BORROWING_memory-lancedb-pro.md 中定义的重排与降级策略
**影响**：无法实现高质量的检索重排和稳定的降级机制
**建议**：
- 补充独立超时与并发控制
- 补充失败降级到 fusion 排序的策略
- 补充混合评分和符号查询保护机制

#### 5. Scope/Namespace 隔离模型不完整
**位置**：requirements.md 5.2、design.md
**问题**：缺少 BORROWING_memory-lancedb-pro.md 中定义的统一隔离模型
**影响**：无法支持未来的多用户/多租户演进
**建议**：
- 补充统一 scope 形态（global/user/agent/project/custom）
- 补充硬隔离要求（检索前过滤）
- 补充二次校验机制

### 🟠 严重问题（4）

#### 6. Evidence 统一元数据规范不完整
**位置**：requirements.md 3.6.4、design.md
**问题**：缺少 BORROWING_memory-lancedb-pro.md 中定义的统一元数据中枢规范
**影响**：无法实现跨存储后端的统一证据模型
**建议**：补充标识、隔离、时间、质量、审计字段的完整定义

#### 7. Prompt 注入安全约束缺失
**位置**：requirements.md 5.2、design.md
**问题**：缺少 BORROWING_memory-lancedb-pro.md 中定义的安全约束
**影响**：存在 prompt 注入安全风险
**建议**：补充 [UNTRUSTED DATA] 标记和注入数量控制

#### 8. 生命周期/衰减分阶段约束不明确
**位置**：design.md、tasks.md
**问题**：缺少 BORROWING_memory-lancedb-pro.md 中定义的分阶段落地约束
**影响**：可能破坏 raw_events 可回放原则
**建议**：明确阶段 1 仅 time-decay，访问计数更新必须异步

#### 9. 外部依赖失败策略不统一
**位置**：requirements.md、design.md
**问题**：对 WeKnora/embeddings/LLM provider 的失败策略描述不一致
**影响**：无法保证系统的可用性和可观测性
**建议**：统一为"显式失败或显式降级"，不得静默吞错

### 🟡 一般问题（3）

#### 10. 配置项不完整
**位置**：requirements.md 6.4.2、tasks.md 14.1.1
**问题**：缺少 BORROWING_memory-lancedb-pro.md 中定义的关键配置项
**建议**：补充检索排序、召回护栏、重排、安全等配置项

#### 11. 任务依赖关系不清晰
**位置**：tasks.md
**问题**：部分任务的依赖关系和优先级标注不够明确
**建议**：明确关键路径和阻断项，优化任务排序

#### 12. 验收标准不够具体
**位置**：requirements.md 8.1-8.5
**问题**：部分验收标准过于抽象，缺少可量化指标
**建议**：补充具体的测试用例和性能基准

### 🟢 优化建议（2）

#### 13. 文档结构优化
**建议**：在 requirements.md 开头增加权威文档引用章节，明确约束来源

#### 14. 任务粒度优化
**建议**：将部分大任务拆分为更小的可执行单元，便于跟踪进度

## 审查维度详情

### A. 契约一致性审查
- [x] 基础架构设计：与权威文档基本一致
- [ ] WeKnora 集成策略：存在不一致，需要修正
- [ ] 检索排序管线：缺少关键约束
- [ ] 安全模型：不完整

### B. 技术可行性审查
- [x] 分层记忆架构：设计合理
- [x] 异步巩固机制：技术路径可行
- [ ] 外部依赖管理：策略不统一
- [x] 性能目标：基本合理

### C. 实施完整性审查
- [x] 任务分解：基本完整
- [ ] 依赖关系：部分不清晰
- [ ] 验收标准：需要细化
- [x] 技术栈选型：与权威文档一致

### D. 安全与合规审查
- [ ] 数据隔离：模型不完整
- [ ] 安全约束：缺少关键约束
- [x] 审计要求：基本满足
- [x] 合规要求：符合预期

## 验收建议

### 当前状态
- [ ] 可以开始实施
- [x] 需要修复阻断性问题后再开始实施
- [ ] 需要重新设计核心架构

### 修复优先级
1. 🔴 修复 WeKnora 集成策略不一致（阻断）
2. 🔴 补充检索排序管线约束（阻断）
3. 🔴 补充召回护栏机制（阻断）
4. 🔴 补充 Cross-Encoder 重排策略（阻断）
5. 🔴 补充 Scope/Namespace 隔离模型（阻断）
6. 🟠 补充 Evidence 统一元数据规范（严重）
7. 🟠 补充 Prompt 注入安全约束（严重）

### 风险评估
- **高风险**：WeKnora 集成策略不一致可能导致架构偏离，需要优先修复
- **中风险**：检索排序管线缺失可能影响检索质量，需要及时补充
- **低风险**：配置项不完整主要影响运维便利性，可以渐进完善

## 附录

### 检查清单
- [x] 契约一致性审查
- [x] 技术可行性审查
- [x] 实施完整性审查
- [x] 安全与合规审查

### 审查工具
- 审查方式：静态文档审查 + 权威文档对比
- 对比基准：sbo.md、INTEGRATION_WEKNORA_EpisodicMemory.md、BORROWING_memory-lancedb-pro.md
- 审查维度：契约一致性、技术可行性、实施完整性、安全合规

### 参考文档
- sbo.md（SecondBrainOS 需求与架构权威文档）
- INTEGRATION_WEKNORA_EpisodicMemory.md（WeKnora 集成方案）
- BORROWING_memory-lancedb-pro.md（检索排序管线约束）
- .kiro/specs/second-brain-os/requirements.md
- .kiro/specs/second-brain-os/design.md
- .kiro/specs/second-brain-os/tasks.md

## 零遗留项声明

### 阻断性问题处理结果
- 🔴 问题 1-5：已识别并提供修复建议，需要在实施前完成修复
- 所有阻断性问题都有明确的修复路径和优先级

### 文档完整性确认
- API 文档：基本框架完整，需要补充错误码枚举
- 配置项：缺少关键配置项，已在建议中列出
- 契约定义：基本完整，需要补充检索排序管线相关契约

### 审查覆盖确认
- 契约一致性：已全面审查，发现 5 个阻断性问题
- 技术可行性：已审查，整体可行但需要修复关键约束
- 实施完整性：已审查，任务分解基本完整但需要优化依赖关系
- 安全合规：已审查，需要补充关键安全约束

**结论**：文档质量良好，架构设计合理，但存在与权威文档不一致的阻断性问题。建议优先修复阻断性问题后再开始实施，预计修复工作量约 2-3 天。
