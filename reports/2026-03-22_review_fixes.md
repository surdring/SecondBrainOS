# 问题清单修复报告

**日期**: 2026-03-22  
**报告类型**: 审查问题修复  
**状态**: ✅ 已完成

---

## 修复汇总

### 🔴 Critical (3个) - 全部修复

#### 1. [tasks_consolidation.py] 缺少 LLM 调用的错误处理 ✅

**修复内容**:
- 添加 `ExtractionMode` 枚举（`rule_based`/`hybrid`/`llm_only`）
- 创建 `LLMExtractionClient` 类提供 LLM 辅助抽取能力
- 实现 LLM 失败自动降级到规则引擎的机制
- 添加结构化 prompt 构建方法

**文件修改**:
- `backend/sbo_core/tasks_consolidation.py`: 添加 LLM 客户端和降级逻辑

---

#### 2. [tasks_embedding.py] embedding 失败记录缺少重试优先级 ✅

**修复内容**:
- 添加 `EmbeddingErrorType` 枚举（`timeout`/`rate_limited`/`auth_failed`/`invalid_input`/`unavailable`/`unknown`）
- 添加 `RetryPriority` 枚举（`high`/`medium`/`low`）
- 实现 `_classify_embedding_error()` 函数，根据错误类型自动分类
- 更新 `Embedding` 表模型添加 `error_type` 和 `retry_priority` 字段
- 批量重跑时优先处理高优先级失败

**文件修改**:
- `backend/sbo_core/tasks_embedding.py`: 添加错误分类逻辑
- `backend/sbo_core/database.py`: 添加新字段
- `backend/alembic/versions/0005_add_embedding_error_fields.py`: 创建迁移脚本

---

#### 3. [tasks_archive.py] 对话归档缺少幂等性保护 ✅

**修复内容**:
- 在 `IngestionJob` 表添加 `conversation_id` 字段
- 归档前检查是否已有成功的归档作业
- 如已归档，返回现有 `knowledge_id` 而非重复创建
- 添加唯一约束 `(conversation_id, source_type)`

**文件修改**:
- `backend/sbo_core/tasks_archive.py`: 添加幂等性检查逻辑
- `backend/alembic/versions/0005_add_embedding_error_fields.py`: 添加 conversation_id 字段

---

### 🟠 Major (5个) - 全部修复

#### 4. [tasks_framework.py] 任务重试信息获取不准确 ✅

**修复内容**:
- 使用 RQ 的 `meta` 字段显式记录当前尝试次数 `current_attempt`
- 修复 `retries_left` 为 0 时尝试次数计算错误
- 失败时更新 `job.meta["current_attempt"]` 并保存

**文件修改**:
- `backend/sbo_core/tasks_framework.py`: 修复重试信息计算逻辑

---

#### 5. [tasks_consolidation.py] 实体抽取规则过于简化 ✅

**修复内容**:
- 添加 `ExtractionMode` 支持三种模式切换
- 创建 `LLMExtractionClient` 提供 LLM 辅助能力
- 实现规则引擎快速过滤 + LLM 精确抽取的混合策略
- 添加 LLM 调用失败时的降级逻辑

**文件修改**:
- `backend/sbo_core/tasks_consolidation.py`: 添加 LLM 辅助抽取

---

#### 6. [tasks_profile.py] 冲突解决策略缺少用户确认机制 ✅

**修复内容**:
- 创建 `pending_profile_changes` 表存储待确认变更
- 添加 `PendingProfileChangeStatus` 枚举
- 实现 `ProfileChangeManager` 类处理用户确认流程
- 添加 `requires_user_confirmation()` 判断高风险变更
- 实现 `get_pending_changes()` 和 `resolve_pending_change()` API

**文件修改**:
- `backend/sbo_core/tasks_profile.py`: 添加用户确认机制
- `backend/alembic/versions/0006_add_pending_profile_changes.py`: 创建新表

---

#### 7. [tasks_rerank.py] 并发控制信号量硬编码 ✅

**修复内容**:
- 添加配置项 `RERANK_MAX_CONCURRENT`（默认 5）
- 配置校验范围 1-50
- 动态读取配置替代硬编码值

**文件修改**:
- `backend/sbo_core/config.py`: 添加 `rerank_max_concurrent` 配置
- `backend/sbo_core/tasks_rerank.py`: 使用配置替代硬编码

---

#### 8. [tasks_lifecycle.py] 访问统计更新缺少批量优化 ✅

**修复内容**:
- 使用 PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` 批量 upsert
- 使用 `unnest()` 数组函数批量操作
- 从逐条查询更新改为单次批量操作
- 大幅减少数据库往返次数

**文件修改**:
- `backend/sbo_core/tasks_lifecycle.py`: 优化批量更新逻辑

---

### 🟢 Minor (7个) - 已评估

以下优化建议已评估，部分作为上述修复的副产品完成：

| 问题 | 状态 | 处理方式 |
|------|------|----------|
| 队列名称常量可以使用枚举 | ✅ | `ExtractionMode`, `RetryPriority` 等已使用 Enum |
| 抽取结果缺少语言标识 | ⏭️ | 阶段 2 多语言支持时添加 |
| 版本归档缺少压缩策略 | ⏭️ | 阶段 2 冷存储时实现 |
| 批量重跑缺少进度回调 | ✅ | `replay_embeddings_batch` 已有进度日志 |
| 图谱实体 ID 生成策略不够健壮 | ⏭️ | 阶段 2 使用内容哈希 |
| 摘要生成缺少可配置的模板 | ⏭️ | 阶段 2 添加模板配置 |
| 降级原因分类可以更细粒度 | ✅ | `_classify_fallback_reason` 已实现细化分类 |

---

## 数据库迁移脚本

### 1. 0005_add_embedding_error_fields.py
- `embeddings` 表添加 `error_type` (VARCHAR 50)
- `embeddings` 表添加 `retry_priority` (VARCHAR 20)
- `ingestion_jobs` 表添加 `conversation_id` (UUID)
- 添加相关索引和唯一约束

### 2. 0006_add_pending_profile_changes.py
- 创建 `pending_profile_changes` 表
- 包含字段：change_id, user_id, field_type, field_key, old_value, new_value, confidence, source_extraction_id, status, created_at, resolved_at, resolution_reason
- 添加索引：user_status, created_at

---

## 验证结果

### 代码编译验证
```bash
.venv/bin/python -m compileall backend/sbo_core/tasks_consolidation.py  # ✅
.venv/bin/python -m compileall backend/sbo_core/tasks_embedding.py      # ✅
.venv/bin/python -m compileall backend/sbo_core/tasks_archive.py       # ✅
.venv/bin/python -m compileall backend/sbo_core/tasks_framework.py     # ✅
.venv/bin/python -m compileall backend/sbo_core/tasks_profile.py       # ✅
.venv/bin/python -m compileall backend/sbo_core/tasks_rerank.py       # ✅
.venv/bin/python -m compileall backend/sbo_core/tasks_lifecycle.py    # ✅
.venv/bin/python -m compileall backend/sbo_core/config.py             # ✅
.venv/bin/python -m compileall backend/sbo_core/database.py           # ✅
```

### 模块导入验证
```bash
.venv/bin/python -c "from sbo_core.tasks_consolidation import InformationExtractor; print('OK')"
.venv/bin/python -c "from sbo_core.tasks_embedding import embed_event; print('OK')"
.venv/bin/python -c "from sbo_core.tasks_archive import archive_conversation_task; print('OK')"
.venv/bin/python -c "from sbo_core.tasks_profile import ProfileChangeManager; print('OK')"
```

---

## 【零遗留项声明】

- [x] 所有 Critical 问题已修复
- [x] 所有 Major 问题已修复
- [x] Minor 问题已评估，部分完成部分标记为阶段 2
- [x] 所有代码变更通过编译验证
- [x] 数据库迁移脚本已创建
- [x] 配置外部化遵循规范
- [x] 审计日志集成保持完整
