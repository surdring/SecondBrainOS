"""
图谱更新任务实现 - 4.8

功能：
1. 实现 upsert_graph(extraction_id) 任务
2. 实现 Neo4j 节点和关系 MERGE
3. 添加 source_event_id 和时间戳
4. 添加关系权重时间衰减机制

依赖需求：3.3.1
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sbo_core.tasks_framework import (
    task_wrapper, enqueue_task, QUEUE_DEFAULT, TaskPriority, TaskStatus,
    update_consolidation_job_status
)
from sbo_core.audit import audit_log
from sbo_core.database import get_database, RawEvent
from sbo_core.config import load_settings
from sbo_core.errors import ErrorCode, AppError
from sbo_core.neo4j_graph import (
    get_driver, ensure_schema, upsert_entity, create_relation,
    GraphEntity, GraphRelation, NODE_LABELS, REL_TYPES
)

_logger = logging.getLogger("sbo_core.graph_tasks")


class GraphUpdateResult:
    """图谱更新结果"""
    def __init__(
        self,
        extraction_id: str,
        success: bool,
        nodes_created: int = 0,
        nodes_updated: int = 0,
        relations_created: int = 0,
        relations_updated: int = 0,
        error_message: str | None = None,
    ):
        self.extraction_id = extraction_id
        self.success = success
        self.nodes_created = nodes_created
        self.nodes_updated = nodes_updated
        self.relations_created = relations_created
        self.relations_updated = relations_updated
        self.error_message = error_message


# 关系权重衰减配置
RELATION_DECAY_RATE = 0.05  # 每日衰减率
RELATION_MAX_DAYS = 365     # 最大考虑天数


def calculate_relation_weight_decay(
    occurred_at: datetime | None,
    reference_time: datetime | None = None,
) -> float:
    """
    计算关系权重衰减值
    
    使用指数衰减公式: weight = exp(-decay_rate * days_ago)
    
    Args:
        occurred_at: 关系发生时间
        reference_time: 参考时间（默认当前时间）
        
    Returns:
        衰减后的权重值 (0-1)
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    
    if occurred_at is None:
        # 没有时间信息，返回默认权重
        return 1.0
    
    # 确保时区一致
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    
    # 计算天数差
    days_ago = (reference_time - occurred_at).days
    days_ago = max(0, min(days_ago, RELATION_MAX_DAYS))
    
    # 指数衰减
    weight = math.exp(-RELATION_DECAY_RATE * days_ago)
    
    return round(weight, 4)


def _extract_graph_entities(extraction_content: dict[str, Any], event_id: str, occurred_at: datetime | None) -> list[GraphEntity]:
    """
    从抽取内容中提取图谱实体
    
    Args:
        extraction_content: 抽取内容
        event_id: 源事件ID
        occurred_at: 事件发生时间
        
    Returns:
        图谱实体列表
    """
    entities = []
    
    # 从实体抽取中提取
    if "name" in extraction_content and "entity_type" in extraction_content:
        entity_type = extraction_content.get("entity_type", "THING").upper()
        
        # 映射到支持的标签
        label_mapping = {
            "PERSON": "Person",
            "ORGANIZATION": "Person",  # 简化处理，组织也映射为 Person
            "LOCATION": "Location",
            "TIME": "Thing",  # 时间映射为 Thing
            "THING": "Thing",
            "CONCEPT": "Thing",
            "EVENT": "Event",
        }
        label = label_mapping.get(entity_type, "Thing")
        
        if label in NODE_LABELS:
            entity_id = f"{extraction_content['name']}_{entity_type}"
            entities.append(GraphEntity(
                label=label,
                entity_id=entity_id,
                name=extraction_content["name"],
                source_event_id=event_id,
                occurred_at=occurred_at,
            ))
    
    return entities


def _extract_graph_relations(
    extraction_content: dict[str, Any],
    event_id: str,
    occurred_at: datetime | None,
    source_entity: GraphEntity | None = None
) -> list[GraphRelation]:
    """
    从抽取内容中提取图谱关系
    
    Args:
        extraction_content: 抽取内容
        event_id: 源事件ID
        occurred_at: 事件发生时间
        source_entity: 源实体（可选）
        
    Returns:
        图谱关系列表
    """
    relations = []
    
    # 从关系抽取中提取
    if "source" in extraction_content and "target" in extraction_content and "relation_type" in extraction_content:
        relation_type_str = extraction_content.get("relation_type", "RELATED_TO").upper()
        
        # 映射到支持的关系类型
        rel_mapping = {
            "PARTICIPATE": "PARTICIPATED_IN",
            "LOCATE_AT": "OCCURRED_AT",
            "ASSOCIATE": "RELATED_TO",
            "KNOW": "KNOWS",
            "OWN": "RELATED_TO",
            "PREFER": "RELATED_TO",
            "CONSTRAINT": "RELATED_TO",
        }
        rel_type = rel_mapping.get(relation_type_str, "RELATED_TO")
        
        if rel_type in REL_TYPES:
            # 确定节点标签（简化处理，默认使用 Thing）
            from_label = "Thing"
            to_label = "Thing"
            
            # 如果源实体已知，使用其标签
            if source_entity:
                from_label = source_entity.label
            
            relations.append(GraphRelation(
                rel_type=rel_type,
                from_label=from_label,
                from_entity_id=f"{extraction_content['source']}_ENTITY",
                to_label=to_label,
                to_entity_id=f"{extraction_content['target']}_ENTITY",
                source_event_id=event_id,
                occurred_at=occurred_at,
            ))
    
    return relations


def _get_occurred_at_from_event(event: RawEvent | None) -> datetime | None:
    """从事件中获取发生时间"""
    if event and event.occurred_at:
        return event.occurred_at
    return None


@task_wrapper(max_retries=3, timeout=120)
def upsert_graph(
    extraction_id: str,
    event_id: str | None = None,
    user_id: str | None = None,
    job_id: str | None = None
) -> dict[str, Any]:
    """
    图谱更新任务 - 将抽取的结构化信息写入 Neo4j 图谱
    
    Args:
        extraction_id: 抽取记录ID（字符串格式UUID）
        event_id: 源事件ID（可选，用于溯源）
        user_id: 用户ID（可选，用于子图隔离）
        job_id: 任务ID（可选）
        
    Returns:
        任务执行结果
    """
    _logger.info(f"Starting upsert_graph for extraction_id={extraction_id}, user_id={user_id}")
    
    # 检查 Neo4j 是否启用
    settings = load_settings()
    if not settings.neo4j_enable:
        _logger.info("Neo4j is disabled, skipping graph upsert")
        return {
            "extraction_id": extraction_id,
            "status": "skipped",
            "reason": "neo4j_disabled"
        }
    
    try:
        extraction_uuid = uuid.UUID(extraction_id)
    except ValueError as e:
        raise AppError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid extraction_id format: {extraction_id}",
            status_code=400
        ) from e
    
    # 更新任务状态
    if job_id:
        update_consolidation_job_status(job_id, TaskStatus.RUNNING)
    
    # 使用默认用户ID（单机单用户场景）
    effective_user_id = user_id or "default_user"
    
    db = get_database()
    session = db.get_session()
    
    try:
        # 1. 查询抽取记录
        from sqlalchemy import text
        
        result = session.execute(
            text("""
                SELECT extraction_id, event_id, extraction_type, content, confidence
                FROM extractions
                WHERE extraction_id = :extraction_id
            """),
            {"extraction_id": extraction_uuid}
        ).fetchone()
        
        if not result:
            raise AppError(
                code=ErrorCode.EXTRACTION_NOT_FOUND,
                message=f"Extraction not found: {extraction_id}",
                status_code=404
            )
        
        extraction_type = result.extraction_type
        content = result.content
        confidence = result.confidence
        associated_event_id = str(result.event_id) if result.event_id else event_id
        
        # 2. 获取源事件信息（用于时间戳和溯源）
        event = None
        occurred_at = None
        if associated_event_id:
            try:
                event_uuid = uuid.UUID(associated_event_id)
                event = session.query(RawEvent).filter(RawEvent.id == event_uuid).first()
                occurred_at = _get_occurred_at_from_event(event)
            except ValueError:
                pass
        
        # 3. 准备图谱实体和关系
        entities: list[GraphEntity] = []
        relations: list[GraphRelation] = []
        
        # 根据抽取类型处理
        if extraction_type == "entity":
            entities = _extract_graph_entities(content, associated_event_id or extraction_id, occurred_at)
        elif extraction_type == "relation":
            relations = _extract_graph_relations(content, associated_event_id or extraction_id, occurred_at)
        elif extraction_type == "preference":
            # 偏好变化：创建/更新用户节点和偏好节点
            category = content.get("category", "general")
            new_value = content.get("new_value", "")
            
            if new_value:
                # 创建用户节点（如果还没有）
                user_entity = GraphEntity(
                    label="Person",
                    entity_id=f"user_{effective_user_id}",
                    name=effective_user_id,
                    source_event_id=associated_event_id or extraction_id,
                    occurred_at=occurred_at,
                )
                entities.append(user_entity)
                
                # 创建偏好节点
                pref_entity = GraphEntity(
                    label="Thing",
                    entity_id=f"pref_{category}_{new_value[:50]}",
                    name=new_value[:100],
                    source_event_id=associated_event_id or extraction_id,
                    occurred_at=occurred_at,
                )
                entities.append(pref_entity)
                
                # 创建关系
                relations.append(GraphRelation(
                    rel_type="RELATED_TO",
                    from_label="Person",
                    from_entity_id=user_entity.entity_id,
                    to_label="Thing",
                    to_entity_id=pref_entity.entity_id,
                    source_event_id=associated_event_id or extraction_id,
                    occurred_at=occurred_at,
                ))
        
        elif extraction_type == "fact":
            # 事实：创建事实节点
            fact_key = content.get("key", "unknown")
            fact_value = content.get("value", "")
            
            if fact_value:
                # 创建用户节点
                user_entity = GraphEntity(
                    label="Person",
                    entity_id=f"user_{effective_user_id}",
                    name=effective_user_id,
                    source_event_id=associated_event_id or extraction_id,
                    occurred_at=occurred_at,
                )
                entities.append(user_entity)
                
                # 创建事实节点
                fact_entity = GraphEntity(
                    label="Thing",
                    entity_id=f"fact_{fact_key}_{fact_value[:50]}",
                    name=f"{fact_key}: {fact_value[:100]}",
                    source_event_id=associated_event_id or extraction_id,
                    occurred_at=occurred_at,
                )
                entities.append(fact_entity)
                
                # 创建关系
                relations.append(GraphRelation(
                    rel_type="RELATED_TO",
                    from_label="Person",
                    from_entity_id=user_entity.entity_id,
                    to_label="Thing",
                    to_entity_id=fact_entity.entity_id,
                    source_event_id=associated_event_id or extraction_id,
                    occurred_at=occurred_at,
                ))
        
        # 4. 写入 Neo4j（使用事务确保原子性）
        if not entities and not relations:
            _logger.info(f"No entities or relations to upsert for extraction {extraction_id}")
            return {
                "extraction_id": extraction_id,
                "status": "skipped",
                "reason": "no_graph_data"
            }
        
        # 连接 Neo4j 并执行写入（使用事务）
        driver = get_driver(settings)
        
        nodes_created = 0
        nodes_updated = 0
        relations_created = 0
        relations_updated = 0
        
        try:
            with driver.session(database=settings.neo4j_database) as neo_session:
                # 使用显式事务确保原子性
                with neo_session.begin_transaction() as tx:
                    # 确保 schema（在事务外执行，避免 schema 操作在事务中）
                    ensure_schema(neo_session)
                    
                    # 创建/更新实体
                    for entity in entities:
                        try:
                            # 检查节点是否存在
                            check_result = tx.run(
                                f"""
                                MATCH (n:{entity.label} {{user_id: $user_id, entity_id: $entity_id}})
                                RETURN n.created_at as created_at
                                """,
                                user_id=effective_user_id,
                                entity_id=entity.entity_id
                            ).fetchone()
                            
                            if check_result:
                                nodes_updated += 1
                            else:
                                nodes_created += 1
                            
                            upsert_entity(neo_session, user_id=effective_user_id, entity=entity)
                            
                        except Exception as e:
                            _logger.warning(f"Failed to upsert entity {entity.entity_id}: {e}")
                            raise  # 重新抛出以触发事务回滚
                    
                    # 创建/更新关系
                    for relation in relations:
                        try:
                            # 检查关系是否存在
                            check_result = tx.run(
                                f"""
                                MATCH (a:{relation.from_label} {{user_id: $user_id, entity_id: $from_entity_id}})
                                MATCH (b:{relation.to_label} {{user_id: $user_id, entity_id: $to_entity_id}})
                                MATCH (a)-[r:{relation.rel_type} {{user_id: $user_id}}]->(b)
                                RETURN r.created_at as created_at
                                """,
                                user_id=effective_user_id,
                                from_entity_id=relation.from_entity_id,
                                to_entity_id=relation.to_entity_id
                            ).fetchone()
                            
                            if check_result:
                                relations_updated += 1
                            else:
                                relations_created += 1
                            
                            create_relation(
                                neo_session,
                                user_id=effective_user_id,
                                rel=relation,
                                weight=calculate_relation_weight_decay(relation.occurred_at),
                            )
                            
                        except Exception as e:
                            _logger.warning(f"Failed to create relation: {e}")
                            raise  # 重新抛出以触发事务回滚
                    
                    # 提交事务
                    tx.commit()
                
                _logger.info(
                    f"Graph upsert completed: nodes_created={nodes_created}, "
                    f"nodes_updated={nodes_updated}, relations_created={relations_created}, "
                    f"relations_updated={relations_updated}"
                )
                
                # 记录审计日志
                audit_log(
                    event="graph.upsert.complete",
                    outcome="success",
                    details={
                        "extraction_id": extraction_id,
                        "user_id": effective_user_id,
                        "event_id": associated_event_id,
                        "nodes_created": nodes_created,
                        "nodes_updated": nodes_updated,
                        "relations_created": relations_created,
                        "relations_updated": relations_updated,
                        "confidence": confidence,
                    }
                )
                
                # 更新任务状态
                if job_id:
                    update_consolidation_job_status(job_id, TaskStatus.SUCCEEDED)
                
                return {
                    "extraction_id": extraction_id,
                    "status": "succeeded",
                    "user_id": effective_user_id,
                    "event_id": associated_event_id,
                    "nodes_created": nodes_created,
                    "nodes_updated": nodes_updated,
                    "relations_created": relations_created,
                    "relations_updated": relations_updated,
                    "total_entities": len(entities),
                    "total_relations": len(relations),
                    "weight_decay_applied": True,
                }
                
        finally:
            driver.close()
        
    except AppError:
        if job_id:
            update_consolidation_job_status(job_id, TaskStatus.FAILED)
        raise
    except Exception as e:
        error_msg = f"Graph upsert failed: {str(e)}"
        _logger.error(f"{error_msg} for extraction {extraction_id}")
        
        if job_id:
            update_consolidation_job_status(job_id, TaskStatus.FAILED, error_msg)
        
        # 记录审计日志
        audit_log(
            event="graph.upsert.failed",
            outcome="fail",
            details={
                "extraction_id": extraction_id,
                "error": error_msg,
            }
        )
        
        raise AppError(
            code=ErrorCode.NEO4J_UNAVAILABLE,
            message=error_msg,
            status_code=503
        ) from e
    finally:
        session.close()


@task_wrapper(max_retries=2, timeout=600)
def recalculate_relation_weights(
    user_id: str | None = None,
    batch_size: int = 1000,
) -> dict[str, Any]:
    """
    重新计算所有关系的权重衰减值
    
    定期执行（如每天）以更新过时关系的权重。
    
    Args:
        user_id: 用户ID（可选，不指定则处理所有）
        batch_size: 每批处理的关系数量
        
    Returns:
        处理结果统计
    """
    settings = load_settings()
    
    if not settings.neo4j_enable:
        return {
            "status": "skipped",
            "reason": "neo4j_disabled",
        }
    
    effective_user_id = user_id or "default_user"
    
    driver = get_driver(settings)
    
    try:
        with driver.session(database=settings.neo4j_database) as session:
            # 查询所有需要更新的关系（有 occurred_at 字段的）
            if user_id:
                result = session.run(
                    """
                    MATCH ()-[r {user_id: $user_id}]->()
                    WHERE r.occurred_at IS NOT NULL
                    RETURN count(r) as total
                    """,
                    user_id=effective_user_id,
                ).single()
            else:
                result = session.run(
                    """
                    MATCH ()-[r]->()
                    WHERE r.occurred_at IS NOT NULL
                    RETURN count(r) as total
                    """
                ).single()
            
            total_relations = int(result["total"]) if result else 0
            
            if total_relations == 0:
                return {
                    "status": "succeeded",
                    "processed": 0,
                    "message": "No relations with occurred_at found",
                }
            
            processed = 0
            updated = 0
            offset = 0
            
            while offset < total_relations:
                # 分批获取关系
                if user_id:
                    batch_result = session.run(
                        """
                        MATCH (a)-[r {user_id: $user_id}]->(b)
                        WHERE r.occurred_at IS NOT NULL
                        RETURN id(r) as rel_id, r.occurred_at as occurred_at
                        SKIP $skip LIMIT $limit
                        """,
                        user_id=effective_user_id,
                        skip=offset,
                        limit=batch_size,
                    )
                else:
                    batch_result = session.run(
                        """
                        MATCH ()-[r]->()
                        WHERE r.occurred_at IS NOT NULL
                        RETURN id(r) as rel_id, r.occurred_at as occurred_at
                        SKIP $skip LIMIT $limit
                        """,
                        skip=offset,
                        limit=batch_size,
                    )
                
                records = list(batch_result)
                if not records:
                    break
                
                for record in records:
                    rel_id = record["rel_id"]
                    occurred_at_str = record["occurred_at"]
                    
                    try:
                        # 解析时间
                        if occurred_at_str:
                            occurred_at = datetime.fromisoformat(occurred_at_str.replace("Z", "+00:00"))
                            new_weight = calculate_relation_weight_decay(occurred_at)
                            
                            # 更新权重
                            session.run(
                                """
                                MATCH ()-[r]->()
                                WHERE id(r) = $rel_id
                                SET r.weight = $weight, r.weight_updated_at = $now
                                """,
                                rel_id=rel_id,
                                weight=new_weight,
                                now=datetime.now(timezone.utc).isoformat(),
                            )
                            updated += 1
                        
                        processed += 1
                        
                    except Exception as e:
                        _logger.warning(f"Failed to update weight for relation {rel_id}: {e}")
                
                offset += batch_size
                
                if offset % 5000 == 0:
                    _logger.info(f"Weight recalculation progress: {offset}/{total_relations}")
            
            _logger.info(
                f"Relation weight recalculation completed: "
                f"processed={processed}, updated={updated}"
            )
            
            return {
                "status": "succeeded",
                "total_relations": total_relations,
                "processed": processed,
                "updated": updated,
                "user_id": effective_user_id,
            }
            
    except Exception as e:
        _logger.error(f"Failed to recalculate relation weights: {e}")
        return {
            "status": "failed",
            "error": str(e),
        }
    finally:
        driver.close()


def enqueue_recalculate_weights(
    user_id: str | None = None,
    priority: TaskPriority = TaskPriority.LOW,
) -> Any:
    """
    将关系权重重新计算任务入队
    
    建议每天执行一次以更新过时关系的权重。
    
    Args:
        user_id: 用户ID（可选）
        priority: 任务优先级
        
    Returns:
        RQ Job 实例
    """
    return enqueue_task(
        recalculate_relation_weights,
        user_id=user_id,
        queue_name=QUEUE_DEFAULT,
        priority=priority,
        timeout=600,  # 10 分钟
        job_meta={"user_id": user_id}
    )


def enqueue_upsert_graph(
    extraction_id: str | uuid.UUID,
    event_id: str | None = None,
    user_id: str | None = None,
    priority: TaskPriority = TaskPriority.NORMAL
) -> Any:
    """
    将图谱更新任务入队
    
    Args:
        extraction_id: 抽取ID
        event_id: 源事件ID（可选）
        user_id: 用户ID（可选）
        priority: 任务优先级
        
    Returns:
        RQ Job 实例
    """
    extraction_id_str = str(extraction_id) if isinstance(extraction_id, uuid.UUID) else extraction_id
    
    return enqueue_task(
        upsert_graph,
        extraction_id_str,
        event_id=event_id,
        user_id=user_id,
        queue_name=QUEUE_DEFAULT,
        priority=priority,
        timeout=120,
        job_meta={"extraction_id": extraction_id_str, "user_id": user_id}
    )


def get_graph_stats(user_id: str | None = None) -> dict[str, Any]:
    """
    获取图谱统计信息
    
    Args:
        user_id: 用户ID（可选，不指定则统计所有）
        
    Returns:
        统计信息字典
    """
    settings = load_settings()
    
    if not settings.neo4j_enable:
        return {
            "enabled": False,
            "nodes": 0,
            "relations": 0,
        }
    
    effective_user_id = user_id or "default_user"
    
    try:
        driver = get_driver(settings)
        
        with driver.session(database=settings.neo4j_database) as session:
            # 统计节点数
            if user_id:
                node_result = session.run(
                    "MATCH (n {user_id: $user_id}) RETURN count(n) as cnt",
                    user_id=effective_user_id
                ).single()
            else:
                node_result = session.run(
                    "MATCH (n) RETURN count(n) as cnt"
                ).single()
            
            node_count = int(node_result["cnt"]) if node_result else 0
            
            # 统计关系数
            if user_id:
                rel_result = session.run(
                    "MATCH ()-[r {user_id: $user_id}]->() RETURN count(r) as cnt",
                    user_id=effective_user_id
                ).single()
            else:
                rel_result = session.run(
                    "MATCH ()-[r]->() RETURN count(r) as cnt"
                ).single()
            
            rel_count = int(rel_result["cnt"]) if rel_result else 0
            
            # 按标签统计节点
            label_stats = {}
            for label in NODE_LABELS:
                if user_id:
                    result = session.run(
                        f"MATCH (n:{label} {{user_id: $user_id}}) RETURN count(n) as cnt",
                        user_id=effective_user_id
                    ).single()
                else:
                    result = session.run(
                        f"MATCH (n:{label}) RETURN count(n) as cnt"
                    ).single()
                
                count = int(result["cnt"]) if result else 0
                if count > 0:
                    label_stats[label] = count
            
            driver.close()
            
            return {
                "enabled": True,
                "user_id": effective_user_id,
                "nodes": node_count,
                "relations": rel_count,
                "by_label": label_stats,
            }
            
    except Exception as e:
        _logger.error(f"Failed to get graph stats: {e}")
        return {
            "enabled": True,
            "error": str(e),
            "nodes": 0,
            "relations": 0,
        }
