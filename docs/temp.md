### 3.5 embeddings 接入策略与失败策略
#### 3.5.1 接入边界
- embeddings 必须作为 SecondBrainOS Core 的内部能力，对调用方（Web App/
OpenClaw）透明。
- OpenClaw/前端不得直接持有 embeddings 的 API key。
#### 3.5.2 失败策略（必须）
- embedding 失败不得影响 `raw_events` 落库与其它抽取步骤的执行。
- 系统必须支持对历史事件批量重跑 embedding（从 `raw_events` 回放），并可重试且
可审计。
### 3.6 数据模型
#### 3.6.1 原始事件（Raw Events）
- event_id：事件唯一标识
- user_id：用户标识
- source：来源渠道（telegram/webchat/whatsapp...）
- content：原始内容
- occurred_at：发生时间
- created_at：创建时间
- metadata：元数据
- 作为事实源 append-only（支持软删字段），其余派生表/索引可重建
#### 3.6.2 结构化记忆（Structured Memory）
- memory_id：记忆唯一标识
- type：记忆类型（preference/fact/event）
- content：记忆内容
- confidence：置信度
- source_events：来源事件列表
- created_at：创建时间
- updated_at：更新时间
#### 3.6.3 用户档案（User Profile）
- user_id：用户标识
- preferences：偏好信息
- facts：事实信息
- constraints：约束条件
- version：版本号
- updated_at：更新时间
#### 3.6.4 前端状态模型
- **Memory**：id、content、type（preference | fact | event）、timestamp
- **Message**：id、role（user | assistant | system）、content、
timestamp、evidence[]（可选）
- **Evidence**：evidence_id、type（raw_event | profile_fact | 
graph_fact）、text、occurred_at、source、confidence、refs