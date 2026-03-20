# SecondBrainOS Spec 文档审查报告

## 审查概述

本报告基于权威文档 `sbo.md`（SecondBrainOS 需求与架构文档）和 `INTEGRATION_WEKNORA_EpisodicMemory.md`（WeKnora 集成方案）对三个项目 spec 文档进行全面审查。

**审查文档：**
- `.kiro/specs/second-brain-os/requirements.md`
- `.kiro/specs/second-brain-os/design.md`  
- `.kiro/specs/second-brain-os/tasks.md`

**审查维度：**
- 🔴 阻断性问题（Blocker）：与权威文档冲突或缺失关键需求
- 🟠 严重问题（Critical）：重要功能描述不准确或不完整
- 🟡 一般问题（Major）：细节描述不一致或需要澄清
- 🟢 优化建议（Minor）：可改进的表述或补充内容

---

## 1. Requirements.md 审查结果

### 🔴 阻断性问题（Blocker）

#### 1.1 WeKnora 集成约束缺失
**问题**：Requirements.md 第 6.1.1 节提到"WeKnora 为权威 Episodic 检索与理解层"，但缺少关键的集成约束和配置要求。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 7.2 节明确要求最低环境变量集
- 必须包含 `WEKNORA_BASE_URL`、`WEKNORA_API_KEY`、`WEKNORA_REQUEST_TIMEOUT_MS` 等

**修复建议**：
在 6.4.2 节补充完整的 WeKnora 环境变量列表，并明确其用途和默认值。

#### 1.2 真实集成原则与 WeKnora 的一致性
**问题**：第 7 节"真实集成原则"要求"所有测试必须针对真实服务运行"，但未明确 WeKnora 作为外部服务的测试策略。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 12 节要求 WeKnora 连通性验证
- 需要明确 WeKnora 不可用时的测试失败策略

**修复建议**：
在第 7 节补充 WeKnora 作为外部依赖的测试要求和失败策略。

### 🟠 严重问题（Critical）

#### 1.3 分层记忆架构描述不完整
**问题**：第 3.2.4 节对 Episodic Memory 的描述过于简化，未体现 WeKnora 的核心职责。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 2.1.1 节明确 WeKnora 负责文档解析、分块、索引、混合检索
- SBO 负责编排层：决定何时检索、何时写入、权限隔离

**修复建议**：
重写第 3.2.4 节，明确 WeKnora 与 SBO 的职责边界。

#### 1.4 API 契约中缺少 WeKnora 相关接口
**问题**：第 3.1 节 API 接口列表中未包含与 WeKnora 集成相关的管理接口。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 4.2.1 节要求文档导入接口
- 需要支持 KnowledgeBase 管理、导入作业状态查询

**修复建议**：
在第 3.1 节补充 WeKnora 集成相关的 API 接口定义。

### 🟡 一般问题（Major）

#### 1.5 时间权重重排策略缺失
**问题**：第 3.4.2 节提到"时间权重重排"但未详细说明实现策略。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 4.1.3 节详细定义了时间衰减函数
- 需要明确 `WEKNORA_TIME_DECAY_RATE`、`WEKNORA_SEMANTIC_WEIGHT` 等配置

**修复建议**：
补充时间权重重排的具体算法和配置参数。

#### 1.6 反馈纠错机制缺失
**问题**：Requirements.md 未包含记忆系统的自我修正能力。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 4.4 节要求反馈纠错机制
- 需要支持用户对错误信息的纠正和标记

**修复建议**：
在用户故事中补充反馈纠错相关的需求。

### 🟢 优化建议（Minor）

#### 1.7 演进路线图与 WeKnora 能力对齐
**建议**：第 7 节演进路线图可以更明确地说明各阶段对 WeKnora 功能的依赖程度。

---

## 2. Design.md 审查结果

### 🔴 阻断性问题（Blocker）

#### 2.1 架构边界描述与权威文档冲突
**问题**：Design.md 中 SecondBrainOS Core 的职责描述与权威文档不一致。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 2.1 节明确 WeKnora 负责检索与理解层
- SBO 不应重复实现文档解析/分块/混合检索

**当前描述问题**：
Design.md 暗示 SBO Core 包含部分检索能力，与集成约束冲突。

**修复建议**：
重写架构边界章节，明确 WeKnora 作为外部服务的定位。

#### 2.2 数据流描述缺少 WeKnora 集成
**问题**：核心工作流中的读取工作流未包含 WeKnora 检索步骤。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 4.1.1 节定义了完整的检索流程
- Deep 模式必须并发调用 WeKnora

**修复建议**：
在读取工作流中补充 WeKnora 检索的具体步骤。

### 🟠 严重问题（Critical）

#### 2.3 异步巩固架构缺少 WeKnora 写入
**问题**：异步巩固任务中未包含向 WeKnora 写入文档/摘要的流程。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 4.2.2 节要求对话归档功能
- 需要将摘要作为 Knowledge 写入 WeKnora

**修复建议**：
在异步巩固任务中补充 WeKnora 写入相关的任务类型。

#### 2.4 API 接口设计不完整
**问题**：核心 API 接口章节缺少 WeKnora 集成相关的接口定义。

**修复建议**：
补充 KnowledgeBase 管理、文档导入、导入状态查询等接口。

### 🟡 一般问题（Major）

#### 2.5 配置管理章节缺少 WeKnora 配置
**问题**：设计文档中未包含 WeKnora 相关的配置项管理。

**修复建议**：
在配置管理章节补充 WeKnora 的配置项和校验策略。

#### 2.6 错误处理策略不完整
**问题**：未明确 WeKnora 不可用时的降级策略。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 5.1 节要求失败降级策略

**修复建议**：
补充 WeKnora 服务不可用时的降级处理机制。

---

## 3. Tasks.md 审查结果

### 🔴 阻断性问题（Blocker）

#### 3.1 WeKnora 集成任务缺失
**问题**：任务列表中缺少 WeKnora 集成的关键任务。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 9 节定义了最小可行实现里程碑
- 需要包含 WeKnora 连通性验证、API 对接、检索集成等任务

**修复建议**：
在任务 1.5.1 基础上，补充完整的 WeKnora 集成任务序列。

#### 3.2 Deep 模式检索任务描述不准确
**问题**：任务 3.4.2 和 5.4 中对 Deep 模式的描述与权威文档不一致。

**权威文档要求**：
- Deep 模式必须并发检索 Semantic Memory + WeKnora
- 需要实现时间权重重排

**修复建议**：
重写相关任务的描述，明确 WeKnora 在 Deep 模式中的作用。

#### 3.3 测试任务缺少 WeKnora 集成验证
**问题**：任务 12.1.1 端到端测试未包含 WeKnora 集成的验证。

**修复建议**：
在端到端测试中补充 WeKnora 文档导入、检索、降级等场景的测试。

### 🟠 严重问题（Critical）

#### 3.4 配置任务缺少 WeKnora 环境变量
**问题**：任务 1.2 和 14.1.1 中未包含 WeKnora 相关的配置管理。

**修复建议**：
补充 WeKnora 配置项的管理和校验任务。

#### 3.5 异步任务缺少对话归档
**问题**：第 4 节异步任务处理中未包含对话归档到 WeKnora 的任务。

**权威文档要求**：
- `INTEGRATION_WEKNORA_EpisodicMemory.md` 第 4.2.2 节要求对话归档功能

**修复建议**：
在第 4 节补充对话归档相关的异步任务。

### 🟡 一般问题（Major）

#### 3.6 任务依赖关系不清晰
**问题**：WeKnora 相关任务与其他任务的依赖关系未明确标注。

**修复建议**：
明确标注哪些任务依赖 WeKnora 集成完成。

#### 3.7 阶段性开关策略不够明确
**问题**：任务中提到的"阶段性开关"策略描述不够具体。

**修复建议**：
详细说明各阶段对 WeKnora 功能的依赖程度和开关策略。

---

## 4. 总体评估与建议

### 4.1 契约一致性评估

**评分：6/10**

三个 spec 文档在整体方向上与权威文档一致，但在 WeKnora 集成的具体实现细节上存在较多缺失和不一致。

### 4.2 完整性评估

**评分：7/10**

文档覆盖了主要功能需求，但在 WeKnora 集成、反馈机制、降级策略等方面存在明显缺失。

### 4.3 可执行性评估

**评分：6/10**

任务分解较为详细，但缺少 WeKnora 集成的具体实施步骤，可能影响项目执行。

### 4.4 优先修复建议

1. **立即修复（阻断性）**：
   - 补充 WeKnora 集成的完整任务序列
   - 修正架构边界描述
   - 补充必要的环境变量配置

2. **近期修复（严重）**：
   - 完善 API 接口定义
   - 补充异步任务中的 WeKnora 写入流程
   - 完善测试策略

3. **后续优化（一般/轻微）**：
   - 优化文档表述的一致性
   - 补充详细的配置说明
   - 完善错误处理策略

---

## 5. 具体修复清单

### 5.1 Requirements.md 修复清单

- [ ] 补充 WeKnora 环境变量配置要求（6.4.2 节）
- [ ] 完善真实集成原则中的 WeKnora 测试策略（第 7 节）
- [ ] 重写 Episodic Memory 架构描述（3.2.4 节）
- [ ] 补充 WeKnora 相关 API 接口（3.1 节）
- [ ] 添加时间权重重排策略说明（3.4.2 节）
- [ ] 补充反馈纠错机制需求（新增用户故事）

### 5.2 Design.md 修复清单

- [ ] 重写架构边界与职责划分章节
- [ ] 补充读取工作流中的 WeKnora 检索步骤
- [ ] 添加异步巩固中的 WeKnora 写入任务
- [ ] 补充 WeKnora 相关 API 接口设计
- [ ] 添加 WeKnora 配置管理章节
- [ ] 补充 WeKnora 降级策略设计

### 5.3 Tasks.md 修复清单

- [ ] 补充完整的 WeKnora 集成任务序列
- [ ] 修正 Deep 模式检索任务描述（3.4.2, 5.4）
- [ ] 补充端到端测试中的 WeKnora 验证（12.1.1）
- [ ] 添加 WeKnora 配置管理任务（1.2, 14.1.1）
- [ ] 补充对话归档异步任务（第 4 节）
- [ ] 明确任务依赖关系标注
- [ ] 详化阶段性开关策略说明

---

## 6. 结论

三个 spec 文档在整体架构和功能需求上与权威文档基本一致，但在 WeKnora 集成这一关键组件的具体实现上存在较多缺失。