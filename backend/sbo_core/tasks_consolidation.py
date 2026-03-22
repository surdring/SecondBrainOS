"""
事件巩固任务实现 - 4.2

功能：
1. 实现 consolidate_event(event_id) 任务
2. 实现结构化信息抽取（实体/关系/偏好变化/待办等）
3. 实现实体和关系识别
4. 将抽取结果写入 extractions 表

依赖需求：3.3.1, 3.4.1
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sbo_core.tasks_framework import (
    task_wrapper, enqueue_task, QUEUE_DEFAULT, TaskPriority, TaskStatus,
    update_consolidation_job_status
)
from sbo_core.audit import audit_log
from sbo_core.database import get_database, RawEvent
from sbo_core.config import load_settings
from sbo_core.errors import ErrorCode, AppError


_logger = logging.getLogger("sbo_core.consolidation_tasks")


class ExtractionType(str, Enum):
    """提取类型枚举"""
    ENTITY = "entity"              # 实体
    RELATION = "relation"          # 关系
    PREFERENCE = "preference"      # 偏好变化
    FACT = "fact"                  # 事实
    TODO = "todo"                  # 待办事项
    EVENT = "event"                # 事件信息
    TEMPORAL = "temporal"          # 时间信息


class EntityType(str, Enum):
    """实体类型枚举"""
    PERSON = "person"              # 人物
    ORGANIZATION = "organization"  # 组织
    LOCATION = "location"        # 地点
    TIME = "time"                  # 时间
    THING = "thing"                # 物品
    CONCEPT = "concept"            # 概念
    EVENT = "event"                # 事件


class RelationType(str, Enum):
    """关系类型枚举"""
    PARTICIPATE = "participate"    # 参与
    LOCATE_AT = "locate_at"        # 发生于
    ASSOCIATE = "associate"        # 关联
    KNOW = "know"                  # 认识
    OWN = "own"                    # 拥有
    PREFER = "prefer"              # 偏好
    CONSTRAINT = "constraint"      # 约束/禁忌


@dataclass
class ExtractedEntity:
    """抽取的实体"""
    name: str
    entity_type: EntityType
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedRelation:
    """抽取的关系"""
    source: str                          # 源实体名称
    target: str                          # 目标实体名称
    relation_type: RelationType
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedPreference:
    """抽取的偏好变化"""
    category: str                        # 偏好类别（如：饮食、工作习惯）
    old_value: str | None                # 旧值（如果有）
    new_value: str                       # 新值
    confidence: float
    is_constraint: bool = False          # 是否为约束/禁忌


@dataclass
class ExtractedFact:
    """抽取的事实"""
    key: str                             # 事实键
    value: str                           # 事实值
    confidence: float
    is_stable: bool = True               # 是否为稳定事实（如证件号）


@dataclass
class ExtractedTodo:
    """抽取的待办事项"""
    content: str                         # 待办内容
    assignee: str | None = None          # 负责人
    due_hint: str | None = None          # 截止时间提示
    priority: str = "normal"             # 优先级
    confidence: float = 0.8


@dataclass
class ExtractionResult:
    """结构化抽取结果"""
    event_id: uuid.UUID
    extraction_id: uuid.UUID = field(default_factory=uuid.uuid4)
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    preferences: list[ExtractedPreference] = field(default_factory=list)
    facts: list[ExtractedFact] = field(default_factory=list)
    todos: list[ExtractedTodo] = field(default_factory=list)
    temporal_info: dict[str, Any] = field(default_factory=dict)
    overall_confidence: float = 0.0
    extraction_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json(self) -> dict[str, Any]:
        """转换为 JSON 格式用于数据库存储"""
        return {
            "entities": [
                {
                    "name": e.name,
                    "type": e.entity_type.value,
                    "confidence": e.confidence,
                    "metadata": e.metadata,
                }
                for e in self.entities
            ],
            "relations": [
                {
                    "source": r.source,
                    "target": r.target,
                    "type": r.relation_type.value,
                    "confidence": r.confidence,
                    "metadata": r.metadata,
                }
                for r in self.relations
            ],
            "preferences": [
                {
                    "category": p.category,
                    "old_value": p.old_value,
                    "new_value": p.new_value,
                    "confidence": p.confidence,
                    "is_constraint": p.is_constraint,
                }
                for p in self.preferences
            ],
            "facts": [
                {
                    "key": f.key,
                    "value": f.value,
                    "confidence": f.confidence,
                    "is_stable": f.is_stable,
                }
                for f in self.facts
            ],
            "todos": [
                {
                    "content": t.content,
                    "assignee": t.assignee,
                    "due_hint": t.due_hint,
                    "priority": t.priority,
                    "confidence": t.confidence,
                }
                for t in self.todos
            ],
            "temporal_info": self.temporal_info,
            "overall_confidence": self.overall_confidence,
            "extraction_timestamp": self.extraction_timestamp.isoformat(),
        }


class InformationExtractor:
    """结构化信息抽取器
    
    使用规则引擎 + LLM 辅助的方式抽取结构化信息
    """
    
    def __init__(self):
        self._init_patterns()
    
    def _init_patterns(self):
        """初始化抽取规则模式"""
        # 时间相关关键词
        self.temporal_keywords = [
            "今天", "明天", "后天", "昨天", "上周", "下周",
            "早上", "中午", "下午", "晚上", "凌晨",
            "周一", "周二", "周三", "周四", "周五", "周六", "周日",
            "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日",
            "点", "分", "钟", "小时", "分钟",
        ]
        
        # 地点相关关键词
        self.location_keywords = [
            "在", "去", "来", "到", "位于", "地址", "地方",
            "家", "公司", "学校", "医院", "超市", "商场", "机场", "车站",
        ]
        
        # 人物相关称谓
        self.person_titles = [
            "先生", "女士", "老师", "医生", "经理", "总监", "总裁",
            "爸爸", "妈妈", "爷爷", "奶奶", "哥哥", "姐姐", "弟弟", "妹妹",
        ]
        
        # 偏好变化关键词
        self.preference_change_keywords = [
            "喜欢", "不喜欢", "爱好", "讨厌", "想", "不想",
            "决定", "选择", "改", "变成", "换成", "改为",
            "忌口", "不能吃", "过敏", "禁止", "避免",
        ]
        
        # 待办事项关键词
        self.todo_keywords = [
            "记得", "别忘了", "要", "需要", "必须", "应该",
            "办理", "处理", "完成", "准备", "预约", "报名",
        ]
        
        # 事实陈述关键词
        self.fact_keywords = [
            "是", "有", "没有", "在", "叫", "姓名", "名字",
            "号码", "电话", "身份证", "护照", "账号", "邮箱",
        ]
    
    def extract(self, event: RawEvent) -> ExtractionResult:
        """从事件中抽取结构化信息
        
        Args:
            event: 原始事件
            
        Returns:
            抽取结果
        """
        content = event.content or ""
        
        result = ExtractionResult(
            event_id=event.id,
            extraction_timestamp=datetime.now(timezone.utc),
        )
        
        # 抽取实体
        result.entities = self._extract_entities(content)
        
        # 抽取关系
        result.relations = self._extract_relations(content, result.entities)
        
        # 抽取偏好变化
        result.preferences = self._extract_preferences(content)
        
        # 抽取经办事项
        result.todos = self._extract_todos(content)
        
        # 抽取事实
        result.facts = self._extract_facts(content)
        
        # 抽取时间信息
        result.temporal_info = self._extract_temporal_info(content, event.occurred_at)
        
        # 计算整体置信度
        result.overall_confidence = self._calculate_overall_confidence(result)
        
        return result
    
    def _extract_entities(self, content: str) -> list[ExtractedEntity]:
        """抽取实体"""
        entities = []
        
        # 简单规则：识别人名（基于称谓）
        for title in self.person_titles:
            if title in content:
                # 尝试提取称谓前的人名
                idx = content.find(title)
                if idx > 0:
                    # 向前查找可能的姓名（简化处理）
                    prefix = content[max(0, idx-4):idx].strip()
                    # 提取可能的姓氏+称谓（如：张先生、李女士）
                    if prefix:
                        # 取最后一个字作为姓氏（或整个前缀）
                        # 处理中文人名：取最后一个字或最后两个字符
                        if len(prefix) >= 2 and prefix[-1] not in "了的在和到":
                            name = prefix[-2:]
                        else:
                            name = prefix[-1:] if prefix else ""
                        if name and len(name) <= 2:  # 假设姓氏1-2个字符
                            entities.append(ExtractedEntity(
                                name=name + title,
                                entity_type=EntityType.PERSON,
                                confidence=0.7,
                                metadata={"extracted_by": "title_pattern"}
                            ))
                            break  # 找到一个即可
        
        # 识别时间实体
        for keyword in self.temporal_keywords:
            if keyword in content:
                # 提取时间上下文
                idx = content.find(keyword)
                context = content[max(0, idx-5):min(len(content), idx+10)]
                entities.append(ExtractedEntity(
                    name=context,
                    entity_type=EntityType.TIME,
                    confidence=0.6,
                    metadata={"keyword": keyword, "extracted_by": "temporal_pattern"}
                ))
                break  # 只记录一个时间实体示例
        
        # 识别地点实体
        for keyword in self.location_keywords:
            if keyword in content:
                idx = content.find(keyword)
                context = content[max(0, idx-3):min(len(content), idx+15)]
                if len(context) > 3:
                    entities.append(ExtractedEntity(
                        name=context,
                        entity_type=EntityType.LOCATION,
                        confidence=0.5,
                        metadata={"keyword": keyword, "extracted_by": "location_pattern"}
                    ))
                    break
        
        return entities
    
    def _extract_relations(self, content: str, entities: list[ExtractedEntity]) -> list[ExtractedRelation]:
        """抽取实体间关系"""
        relations = []
        
        # 简化规则：如果内容包含"和"，假设存在关联关系
        if "和" in content and len(entities) >= 2:
            relations.append(ExtractedRelation(
                source=entities[0].name,
                target=entities[1].name if len(entities) > 1 else "unknown",
                relation_type=RelationType.ASSOCIATE,
                confidence=0.5,
                metadata={"extracted_by": "conjunction_pattern"}
            ))
        
        return relations
    
    def _extract_preferences(self, content: str) -> list[ExtractedPreference]:
        """抽取偏好变化"""
        preferences = []
        
        # 检测忌口/禁忌
        constraint_keywords = ["忌口", "不能吃", "过敏", "禁止", "避免", "别吃", "不要"]
        for keyword in constraint_keywords:
            if keyword in content:
                idx = content.find(keyword)
                context = content[max(0, idx-10):min(len(content), idx+20)]
                preferences.append(ExtractedPreference(
                    category="dietary_constraint",
                    old_value=None,
                    new_value=context,
                    confidence=0.8,
                    is_constraint=True
                ))
                break
        
        # 检测偏好变化（简化规则）
        change_patterns = [
            ("喜欢", "positive"),
            ("不喜欢", "negative"),
            ("爱好", "positive"),
            ("讨厌", "negative"),
        ]
        
        for pattern, sentiment in change_patterns:
            if pattern in content:
                idx = content.find(pattern)
                context = content[max(0, idx-5):min(len(content), idx+15)]
                preferences.append(ExtractedPreference(
                    category="general_preference",
                    old_value=None,
                    new_value=context,
                    confidence=0.6,
                    is_constraint=False
                ))
                break
        
        return preferences
    
    def _extract_todos(self, content: str) -> list[ExtractedTodo]:
        """抽取待办事项"""
        todos = []
        
        todo_indicators = ["记得", "别忘了", "要", "需要", "必须"]
        for indicator in todo_indicators:
            if indicator in content:
                idx = content.find(indicator)
                # 提取后续内容作为待办
                context = content[idx:min(len(content), idx+30)]
                if len(context) > 5:
                    todos.append(ExtractedTodo(
                        content=context,
                        assignee=None,
                        due_hint=None,
                        priority="normal",
                        confidence=0.7
                    ))
                    break
        
        return todos
    
    def _extract_facts(self, content: str) -> list[ExtractedFact]:
        """抽取事实信息"""
        facts = []
        
        # 识别证件类信息（简化规则）
        id_patterns = [
            ("身份证", "id_card"),
            ("护照", "passport"),
            ("电话", "phone"),
            ("号码", "number"),
        ]
        
        for pattern, fact_type in id_patterns:
            if pattern in content:
                idx = content.find(pattern)
                context = content[max(0, idx-3):min(len(content), idx+20)]
                if len(context) > 5:
                    facts.append(ExtractedFact(
                        key=fact_type,
                        value=context,
                        confidence=0.5,
                        is_stable=(fact_type in ["id_card", "passport"])
                    ))
                    break
        
        return facts
    
    def _extract_temporal_info(self, content: str, occurred_at: datetime | None) -> dict[str, Any]:
        """抽取时间信息"""
        temporal_info = {
            "referenced_times": [],
            "event_occurred_at": occurred_at.isoformat() if occurred_at else None,
        }
        
        # 检测相对时间引用
        relative_times = ["今天", "明天", "昨天", "上周", "下周"]
        for rt in relative_times:
            if rt in content:
                temporal_info["referenced_times"].append(rt)
        
        return temporal_info
    
    def _calculate_overall_confidence(self, result: ExtractionResult) -> float:
        """计算整体抽取置信度"""
        confidences = []
        
        for entity in result.entities:
            confidences.append(entity.confidence)
        
        for pref in result.preferences:
            confidences.append(pref.confidence)
        
        for fact in result.facts:
            confidences.append(fact.confidence)
        
        for todo in result.todos:
            confidences.append(todo.confidence)
        
        if not confidences:
            return 0.0
        
        return sum(confidences) / len(confidences)


@task_wrapper(max_retries=3, timeout=300)
def consolidate_event(event_id: str, job_id: str | None = None) -> dict[str, Any]:
    """事件巩固任务 - 抽取结构化信息
    
    Args:
        event_id: 事件ID（字符串格式UUID）
        job_id: 巩固任务ID（可选）
        
    Returns:
        任务执行结果
        
    Raises:
        AppError: 当任务执行失败时
    """
    _logger.info(f"Starting consolidate_event for event_id={event_id}")
    
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError as e:
        raise AppError(
            code=ErrorCode.CONSOLIDATION_FAILED,
            message=f"Invalid event_id format: {event_id}",
            status_code=400
        ) from e
    
    # 更新任务状态
    if job_id:
        update_consolidation_job_status(job_id, TaskStatus.RUNNING)
    
    try:
        db = get_database()
        session = db.get_session()
        
        try:
            # 1. 获取原始事件
            event = session.query(RawEvent).filter(RawEvent.id == event_uuid).first()
            
            if not event:
                raise AppError(
                    code=ErrorCode.EVENT_NOT_FOUND,
                    message=f"Event not found: {event_id}",
                    status_code=404
                )
            
            if event.deleted_at:
                _logger.warning(f"Event {event_id} is soft-deleted, skipping consolidation")
                return {
                    "event_id": event_id,
                    "status": "skipped",
                    "reason": "event_soft_deleted"
                }
            
            # 2. 执行信息抽取
            extractor = InformationExtractor()
            extraction_result = extractor.extract(event)
            
            # 3. 保存抽取结果到 extractions 表
            from sbo_core.database import ConsolidationJob
            
            # 检查是否已有该事件的提取记录
            existing = session.query(ConsolidationJob).filter(
                ConsolidationJob.event_id == event_uuid,
                ConsolidationJob.job_type == "consolidate_event"
            ).first()
            
            extraction_data = extraction_result.to_json()
            
            if existing:
                # 更新现有记录
                existing.status = "succeeded"
                existing.completed_at = datetime.now(timezone.utc)
                # 确保 payload 是一个 dict
                current_payload = existing.payload if isinstance(existing.payload, dict) else {}
                existing.payload = {
                    **current_payload,
                    "extraction": extraction_data,
                    "extraction_id": str(extraction_result.extraction_id),
                }
            else:
                # 创建新记录（作为 consolidate_event 任务记录）
                job = ConsolidationJob(
                    event_id=event_uuid,
                    job_type="consolidate_event",
                    status="succeeded",
                    completed_at=datetime.now(timezone.utc),
                    payload={
                        "extraction": extraction_data,
                        "extraction_id": str(extraction_result.extraction_id),
                    }
                )
                session.add(job)
            
            # 4. 保存到 extractions 表
            from sbo_core.database import Base
            from sqlalchemy import text
            
            # 为每个提取类型创建单独的 extraction 记录
            extraction_records = []
            
            # 实体提取
            for entity in extraction_result.entities:
                extraction_records.append({
                    "extraction_id": str(uuid.uuid4()),
                    "event_id": event_id,
                    "extraction_type": ExtractionType.ENTITY.value,
                    "content": {
                        "name": entity.name,
                        "entity_type": entity.entity_type.value,
                        "metadata": entity.metadata,
                    },
                    "confidence": entity.confidence,
                })
            
            # 关系提取
            for relation in extraction_result.relations:
                extraction_records.append({
                    "extraction_id": str(uuid.uuid4()),
                    "event_id": event_id,
                    "extraction_type": ExtractionType.RELATION.value,
                    "content": {
                        "source": relation.source,
                        "target": relation.target,
                        "relation_type": relation.relation_type.value,
                        "metadata": relation.metadata,
                    },
                    "confidence": relation.confidence,
                })
            
            # 偏好提取
            for pref in extraction_result.preferences:
                extraction_records.append({
                    "extraction_id": str(uuid.uuid4()),
                    "event_id": event_id,
                    "extraction_type": ExtractionType.PREFERENCE.value,
                    "content": {
                        "category": pref.category,
                        "old_value": pref.old_value,
                        "new_value": pref.new_value,
                        "is_constraint": pref.is_constraint,
                    },
                    "confidence": pref.confidence,
                })
            
            # 事实提取
            for fact in extraction_result.facts:
                extraction_records.append({
                    "extraction_id": str(uuid.uuid4()),
                    "event_id": event_id,
                    "extraction_type": ExtractionType.FACT.value,
                    "content": {
                        "key": fact.key,
                        "value": fact.value,
                        "is_stable": fact.is_stable,
                    },
                    "confidence": fact.confidence,
                })
            
            # 待办提取
            for todo in extraction_result.todos:
                extraction_records.append({
                    "extraction_id": str(uuid.uuid4()),
                    "event_id": event_id,
                    "extraction_type": ExtractionType.TODO.value,
                    "content": {
                        "content": todo.content,
                        "assignee": todo.assignee,
                        "due_hint": todo.due_hint,
                        "priority": todo.priority,
                    },
                    "confidence": todo.confidence,
                })
            
            # 插入 extraction 记录
            for record in extraction_records:
                session.execute(
                    text("""
                        INSERT INTO extractions (extraction_id, event_id, extraction_type, content, confidence)
                        VALUES (:extraction_id, :event_id, :extraction_type, :content, :confidence)
                        ON CONFLICT (extraction_id) DO UPDATE SET
                            content = EXCLUDED.content,
                            confidence = EXCLUDED.confidence
                    """),
                    {
                        "extraction_id": record["extraction_id"],
                        "event_id": uuid.UUID(record["event_id"]),
                        "extraction_type": record["extraction_type"],
                        "content": record["content"],
                        "confidence": record["confidence"],
                    }
                )
            
            session.commit()
            
            # 5. 触发下游任务 - 档案更新
            for pref in extraction_result.preferences:
                if pref.category in ["dietary_constraint", "general_preference"]:
                    # 将偏好变化入队到 upsert_profile 任务
                    enqueue_upsert_profile(
                        extraction_id=str(extraction_result.extraction_id),
                        user_id=event.user_id,
                        priority=TaskPriority.NORMAL
                    )
                    break
            
            for fact in extraction_result.facts:
                if fact.is_stable:
                    enqueue_upsert_profile(
                        extraction_id=str(extraction_result.extraction_id),
                        user_id=event.user_id,
                        priority=TaskPriority.NORMAL
                    )
                    break
            
            # 6. 记录审计日志
            audit_log(
                event="consolidation.complete",
                outcome="success",
                details={
                    "event_id": event_id,
                    "extraction_id": str(extraction_result.extraction_id),
                    "entities_count": len(extraction_result.entities),
                    "relations_count": len(extraction_result.relations),
                    "preferences_count": len(extraction_result.preferences),
                    "facts_count": len(extraction_result.facts),
                    "todos_count": len(extraction_result.todos),
                    "overall_confidence": extraction_result.overall_confidence,
                }
            )
            
            # 更新任务状态
            if job_id:
                update_consolidation_job_status(job_id, TaskStatus.SUCCEEDED)
            
            _logger.info(f"Consolidation completed for event_id={event_id}")
            
            return {
                "event_id": event_id,
                "extraction_id": str(extraction_result.extraction_id),
                "status": "succeeded",
                "entities_count": len(extraction_result.entities),
                "relations_count": len(extraction_result.relations),
                "preferences_count": len(extraction_result.preferences),
                "facts_count": len(extraction_result.facts),
                "todos_count": len(extraction_result.todos),
                "overall_confidence": extraction_result.overall_confidence,
            }
            
        finally:
            session.close()
            
    except AppError:
        # 更新任务状态为失败
        if job_id:
            update_consolidation_job_status(job_id, TaskStatus.FAILED)
        raise
    except Exception as e:
        # 更新任务状态为失败
        if job_id:
            update_consolidation_job_status(job_id, TaskStatus.FAILED)
        
        _logger.error(f"Consolidation failed for event {event_id}: {e}")
        raise AppError(
            code=ErrorCode.CONSOLIDATION_FAILED,
            message=f"Consolidation failed: {str(e)}",
            status_code=500
        ) from e


def enqueue_consolidation(event_id: str | uuid.UUID, user_id: str | None = None) -> Any:
    """将事件巩固任务入队
    
    Args:
        event_id: 事件ID
        user_id: 用户ID（可选）
        
    Returns:
        RQ Job 实例
    """
    event_id_str = str(event_id) if isinstance(event_id, uuid.UUID) else event_id
    
    return enqueue_task(
        consolidate_event,
        event_id_str,
        queue_name=QUEUE_DEFAULT,
        priority=TaskPriority.NORMAL,
        timeout=300,
        job_meta={"user_id": user_id} if user_id else {}
    )


def enqueue_upsert_profile(extraction_id: str, user_id: str | None = None, priority: TaskPriority = TaskPriority.NORMAL) -> Any:
    """将档案更新任务入队
    
    Args:
        extraction_id: 提取ID
        user_id: 用户ID（可选）
        priority: 任务优先级
        
    Returns:
        RQ Job 实例
    """
    # 延迟导入避免循环依赖
    from sbo_core.tasks_profile import upsert_profile
    
    return enqueue_task(
        upsert_profile,
        extraction_id,
        user_id=user_id,
        queue_name=QUEUE_DEFAULT,
        priority=priority,
        timeout=300,
        job_meta={"extraction_id": extraction_id, "user_id": user_id} if (extraction_id or user_id) else {}
    )
