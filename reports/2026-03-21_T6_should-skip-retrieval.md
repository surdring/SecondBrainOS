# shouldSkipRetrieval 召回护栏实现验收日志

## 任务信息
- **任务编号**: 3.4.5
- **任务名称**: shouldSkipRetrieval 召回护栏实现
- **完成时间**: 2026-03-21
- **优先级**: P1

## 目标与设计约束对齐
- **护栏判定时机**：必须发生在 WeKnora（Episodic）调用之前。
- **跳过 deep 的典型输入**：问候语/寒暄/简单确认/emoji/命令等。
- **强制 deep 的典型输入**：记得/之前/上次/回顾/根据文档/查历史等。
- **CJK 特性**：中文短 query 需要独立策略。
- **可配置性**：阈值、关键词列表、最短长度可配置。

## 实现内容

### ✅ 1) shouldSkipRetrieval 判定逻辑
- 在 `RetrievalPipeline.process()` 中对 `mode=deep` 增加护栏：
  - 若命中 **强制 deep**（force）关键字：保留 deep
  - 否则若命中 **跳过 deep**（skip）规则：将 `effective_mode` 降级为 `fast`

### ✅ 2) 可配置规则
- 新增配置项（位于 `RetrievalPipeline.__init__`，便于后续改为配置系统注入）：
  - `skip_deep_min_length`
  - `skip_deep_cjk_min_length`
  - `skip_deep_exact`
  - `skip_deep_contains`
  - `skip_deep_emojis`
  - `force_deep_contains`

### ✅ 3) 可观测性（降级原因记录）
- 若 deep 被护栏跳过：在 `degraded_services` 追加
  - `skip_deep_retrieval:<reason>`

### ✅ 4) CJK 策略
- 通过 `_is_cjk()` 判定是否包含中文字符，并使用 `skip_deep_cjk_min_length` 作为独立阈值。

## 代码变更

### 📁 修改文件
- `backend/sbo_core/retrieval_pipeline.py`
  - 增加 `_should_force_deep_retrieval()`
  - 增加 `_should_skip_deep_retrieval()`
  - 增加 `_is_cjk()`
  - 在 `process()` 中引入 `effective_mode`，确保 deep 护栏在 Episodic 调用前执行

### 🧪 修改测试
- `backend/tests/test_retrieval_pipeline.py`
  - 新增：deep 模式小闲聊输入降级为 fast（不调用 episodic）
  - 新增：包含强制 deep 关键词时保留 deep（调用 episodic）

## 自动化验证

### ✅ 编译检查
```bash
.venv/bin/python -m compileall backend/sbo_core
```
结论：通过。

### ✅ 单元测试
```bash
.venv/bin/python -m pytest -q backend/tests/test_retrieval_pipeline.py
```
结论：通过。

### ✅ 冒烟测试（用户手动执行）
```bash
.venv/bin/python backend/scripts/postgres_smoke_test.py
```
结论：通过（exit code 0）。

## 零遗留项声明
- 本任务范围内无未解决 Blocker/Critical/Major 问题。
- 本任务实现不保留 TODO 类遗留项。
- 编译、单元测试、冒烟测试均已实际运行并通过。

---

**验收结论**：✅ 3.4.5 完成并通过验证。
