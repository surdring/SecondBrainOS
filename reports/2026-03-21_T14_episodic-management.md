# 验收日志：3.6.3 Episodic 管理接口实现

- 日期：2026-03-21
- 任务：`.kiro/specs/second-brain-os/tasks.md` 中 **3.6.3 Episodic 管理接口**

## 变更摘要

- 扩展 `WeKnoraClient` 添加管理方法：
  - `list_knowledge_bases()` - 获取 KnowledgeBase 列表
  - `create_knowledge_base()` - 创建 KnowledgeBase
  - `create_ingestion()` - 创建导入任务
  - `get_ingestion()` - 获取导入任务状态
- 新增 `POST /api/v1/episodic/knowledge-bases` 创建知识库
- 新增 `GET /api/v1/episodic/knowledge-bases` 获取知识库列表
- 新增 `POST /api/v1/episodic/ingestions` 创建导入任务
- 新增 `GET /api/v1/episodic/ingestions/{ingestion_job_id}` 获取导入任务状态
- 新增 `ErrorCode.WEKNORA_NOT_FOUND` 错误码
- 调整模型 `KnowledgeBaseResponse`、`IngestionResponse`、`IngestionJobResponse` 接受字符串 ID（适配 WeKnora 格式）
- 审计日志覆盖：
  - `episodic.kb.list` - 知识库列表查询
  - `episodic.kb.create` - 知识库创建
  - `episodic.ingestion.create` - 导入任务创建
  - `episodic.ingestion.status` - 导入状态查询

## 验证与测试

### 1) 单元测试（Unit Test）

- 命令：

```bash
.venv/bin/python -m pytest backend/tests/test_episodic.py -v
```

- 结果：**9 passed**
- 覆盖要点：
  - 成功获取 knowledge base 列表
  - 成功创建 knowledge base
  - 参数校验失败返回 422
  - 成功创建 ingestion job
  - 无效 source_type 返回 422
  - 成功获取 ingestion 状态
  - ingestion job 不存在返回 404
  - WeKnora 错误返回 503

### 2) 冒烟测试（Smoke Test）

- 命令：

```bash
.venv/bin/python backend/scripts/episodic_api_smoke_test.py
```

- 结果：通过（输出 `OK`）
- 覆盖链路：
  - 真实 DB 初始化 → FastAPI app
  - `GET /api/v1/episodic/knowledge-bases`
  - `POST /api/v1/episodic/knowledge-bases`
  - `POST /api/v1/episodic/ingestions`
  - `GET /api/v1/episodic/ingestions/{id}`

## 结论

- 验收通过。
- 已将任务 **3.6.3** 在 `todo_list` 中标记为完成。
- **所有 TODO 任务已完成**。

## 零遗留项声明（Zero Technical Debt Policy）

- 阻断性问题（Blocker）：无
- 严重问题（Critical）：无
- 一般问题（Major）：无
- 优化建议（Minor）：无

- 契约确认：
  - 请求/响应模型：`KnowledgeBaseRequest`、`KnowledgeBaseResponse`、`IngestionRequest`、`IngestionResponse`、`IngestionJobResponse`
  - 错误码：`knowledge_base_failed`、`ingestion_failed`、`ingestion_job_not_found`、`ingestion_job_failed`
  - WeKnora 透传保持统一 `success/data` 响应结构
