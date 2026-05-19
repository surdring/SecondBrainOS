"""
图谱更新任务单元测试 - 4.9

测试内容：
1. 图谱节点创建和更新
2. 关系建立和维护
3. 数据溯源机制

依赖需求：3.3.1
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from sbo_core.tasks_graph import (
    upsert_graph,
    enqueue_upsert_graph,
    get_graph_stats,
    _extract_graph_entities,
    _extract_graph_relations,
)
from sbo_core.errors import ErrorCode, AppError
from sbo_core.database import RawEvent
from sbo_core.neo4j_graph import GraphEntity, GraphRelation


class TestExtractGraphEntities:
    """测试图谱实体提取"""
    
    def test_extract_person_entity(self):
        """测试提取人物实体"""
        content = {
            "name": "张三",
            "entity_type": "person",
        }
        
        entities = _extract_graph_entities(content, "event-123", datetime.now(timezone.utc))
        
        assert len(entities) == 1
        assert entities[0].label == "Person"
        assert entities[0].name == "张三"
        assert entities[0].source_event_id == "event-123"
        assert entities[0].occurred_at is not None
    
    def test_extract_location_entity(self):
        """测试提取地点实体"""
        content = {
            "name": "北京",
            "entity_type": "location",
        }
        
        entities = _extract_graph_entities(content, "event-123", datetime.now(timezone.utc))
        
        assert len(entities) == 1
        assert entities[0].label == "Location"
        assert entities[0].name == "北京"
    
    def test_extract_unknown_entity_type(self):
        """测试未知实体类型映射到 Thing"""
        content = {
            "name": "神秘物品",
            "entity_type": "unknown",
        }
        
        entities = _extract_graph_entities(content, "event-123", datetime.now(timezone.utc))
        
        assert len(entities) == 1
        assert entities[0].label == "Thing"
    
    def test_extract_organization_entity(self):
        """测试组织实体映射为 Person"""
        content = {
            "name": "ABC公司",
            "entity_type": "organization",
        }
        
        entities = _extract_graph_entities(content, "event-123", datetime.now(timezone.utc))
        
        assert len(entities) == 1
        assert entities[0].label == "Person"
    
    def test_extract_entity_without_name(self):
        """测试缺少 name 字段时不提取"""
        content = {
            "entity_type": "person",
        }
        
        entities = _extract_graph_entities(content, "event-123", datetime.now(timezone.utc))
        
        assert len(entities) == 0


class TestExtractGraphRelations:
    """测试图谱关系提取"""
    
    def test_extract_associate_relation(self):
        """测试提取关联关系"""
        content = {
            "source": "张三",
            "target": "李四",
            "relation_type": "associate",
        }
        
        relations = _extract_graph_relations(content, "event-123", datetime.now(timezone.utc))
        
        assert len(relations) == 1
        assert relations[0].rel_type == "RELATED_TO"
        assert relations[0].from_entity_id == "张三_ENTITY"
        assert relations[0].to_entity_id == "李四_ENTITY"
    
    def test_extract_participate_relation(self):
        """测试提取参与关系"""
        content = {
            "source": "张三",
            "target": "会议",
            "relation_type": "participate",
        }
        
        relations = _extract_graph_relations(content, "event-123", datetime.now(timezone.utc))
        
        assert len(relations) == 1
        assert relations[0].rel_type == "PARTICIPATED_IN"
    
    def test_extract_know_relation(self):
        """测试提取认识关系"""
        content = {
            "source": "张三",
            "target": "李四",
            "relation_type": "know",
        }
        
        relations = _extract_graph_relations(content, "event-123", datetime.now(timezone.utc))
        
        assert len(relations) == 1
        assert relations[0].rel_type == "KNOWS"
    
    def test_extract_relation_with_source_entity(self):
        """测试使用源实体标签的关系提取"""
        content = {
            "source": "张三",
            "target": "北京",
            "relation_type": "locate_at",
        }
        source_entity = GraphEntity(
            label="Person",
            entity_id="user_123",
            name="张三",
        )
        
        relations = _extract_graph_relations(
            content, "event-123", datetime.now(timezone.utc), source_entity
        )
        
        assert len(relations) == 1
        assert relations[0].from_label == "Person"  # 使用 source_entity 的标签
        assert relations[0].rel_type == "OCCURRED_AT"
    
    def test_extract_relation_without_fields(self):
        """测试缺少必要字段时不提取"""
        content = {
            "source": "张三",
        }
        
        relations = _extract_graph_relations(content, "event-123", datetime.now(timezone.utc))
        
        assert len(relations) == 0


class TestUpsertGraphTask:
    """upsert_graph 任务测试"""
    
    def _create_mock_db_with_extraction(self, event=None, extraction_type="entity", extraction_content=None):
        """创建模拟数据库会话"""
        mock_session = MagicMock()
        
        if event:
            mock_session.query.return_value.filter.return_value.first.return_value = event
        
        # 模拟 extraction 查询
        extraction_result = MagicMock()
        extraction_result.extraction_id = uuid.uuid4()
        extraction_result.event_id = event.id if event else uuid.uuid4()
        extraction_result.extraction_type = extraction_type
        extraction_result.content = extraction_content or {"name": "张三", "entity_type": "person"}
        extraction_result.confidence = 0.8
        
        mock_session.execute.return_value.fetchone.return_value = extraction_result
        mock_session.commit.return_value = None
        mock_session.close.return_value = None
        
        mock_db = MagicMock()
        mock_db.get_session.return_value = mock_session
        
        return mock_db, mock_session
    
    @patch("sbo_core.tasks_graph.load_settings")
    def test_upsert_graph_neo4j_disabled(self, mock_settings):
        """测试 Neo4j 禁用时跳过"""
        mock_settings.return_value = MagicMock(neo4j_enable=False)
        
        result = upsert_graph(str(uuid.uuid4()))
        
        assert result["status"] == "skipped"
        assert result["reason"] == "neo4j_disabled"
    
    @patch("sbo_core.tasks_graph.load_settings")
    def test_upsert_graph_invalid_extraction_id(self, mock_settings):
        """测试无效的 extraction_id"""
        mock_settings.return_value = MagicMock(neo4j_enable=True)
        
        with pytest.raises(AppError) as exc_info:
            upsert_graph("invalid-uuid")
        
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    
    @patch("sbo_core.tasks_graph.load_settings")
    @patch("sbo_core.tasks_graph.get_database")
    def test_upsert_graph_extraction_not_found(self, mock_get_db, mock_settings):
        """测试 extraction 不存在"""
        mock_settings.return_value = MagicMock(neo4j_enable=True)
        
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchone.return_value = None
        mock_session.close.return_value = None
        
        mock_db = MagicMock()
        mock_db.get_session.return_value = mock_session
        mock_get_db.return_value = mock_db
        
        with pytest.raises(AppError) as exc_info:
            upsert_graph(str(uuid.uuid4()))
        
        assert exc_info.value.code == ErrorCode.EXTRACTION_NOT_FOUND
    
    @patch("sbo_core.tasks_graph.load_settings")
    @patch("sbo_core.tasks_graph.get_driver")
    def test_upsert_graph_entity_extraction(self, mock_driver, mock_settings, test_db):
        """测试实体类型抽取写入图谱"""
        mock_settings.return_value = MagicMock(
            neo4j_enable=True,
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="test",
            neo4j_database="neo4j",
        )
        
        # 创建事件
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="张三今天去了北京",
            occurred_at=datetime.now(timezone.utc),
        )
        
        session = test_db.get_session()
        session.add(event)
        session.commit()
        
        # 创建 extraction 记录
        extraction_id = uuid.uuid4()
        session.execute(
            """
            INSERT INTO extractions (extraction_id, event_id, extraction_type, content, confidence)
            VALUES (:extraction_id, :event_id, :extraction_type, :content, :confidence)
            """,
            {
                "extraction_id": extraction_id,
                "event_id": event.id,
                "extraction_type": "entity",
                "content": {"name": "张三", "entity_type": "person"},
                "confidence": 0.8,
            }
        )
        session.commit()
        
        # 模拟 Neo4j driver
        mock_session = MagicMock()
        mock_driver_instance = MagicMock()
        mock_driver_instance.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver_instance.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_driver.return_value = mock_driver_instance
        
        result = upsert_graph(str(extraction_id), str(event.id), "test_user")
        
        assert result["status"] == "succeeded"
        assert result["user_id"] == "test_user"
        assert result["nodes_created"] >= 0
        
        session.close()
    
    @patch("sbo_core.tasks_graph.load_settings")
    @patch("sbo_core.tasks_graph.get_driver")
    def test_upsert_graph_preference_extraction(self, mock_driver, mock_settings, test_db):
        """测试偏好类型抽取写入图谱"""
        mock_settings.return_value = MagicMock(
            neo4j_enable=True,
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="test",
            neo4j_database="neo4j",
        )
        
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="我喜欢喝咖啡",
            occurred_at=datetime.now(timezone.utc),
        )
        
        session = test_db.get_session()
        session.add(event)
        session.commit()
        
        extraction_id = uuid.uuid4()
        session.execute(
            """
            INSERT INTO extractions (extraction_id, event_id, extraction_type, content, confidence)
            VALUES (:extraction_id, :event_id, :extraction_type, :content, :confidence)
            """,
            {
                "extraction_id": extraction_id,
                "event_id": event.id,
                "extraction_type": "preference",
                "content": {"category": "general_preference", "new_value": "喝咖啡"},
                "confidence": 0.9,
            }
        )
        session.commit()
        
        # 模拟 Neo4j driver
        mock_session = MagicMock()
        mock_driver_instance = MagicMock()
        mock_driver_instance.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver_instance.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_driver.return_value = mock_driver_instance
        
        result = upsert_graph(str(extraction_id), str(event.id), "test_user")
        
        assert result["status"] == "succeeded"
        # 偏好类型应该创建用户节点和偏好节点
        assert result["total_entities"] == 2
        assert result["total_relations"] == 1
        
        session.close()
    
    @patch("sbo_core.tasks_graph.load_settings")
    @patch("sbo_core.tasks_graph.get_driver")
    def test_upsert_graph_fact_extraction(self, mock_driver, mock_settings, test_db):
        """测试事实类型抽取写入图谱"""
        mock_settings.return_value = MagicMock(
            neo4j_enable=True,
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="test",
            neo4j_database="neo4j",
        )
        
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="我的身份证号是123456789",
            occurred_at=datetime.now(timezone.utc),
        )
        
        session = test_db.get_session()
        session.add(event)
        session.commit()
        
        extraction_id = uuid.uuid4()
        session.execute(
            """
            INSERT INTO extractions (extraction_id, event_id, extraction_type, content, confidence)
            VALUES (:extraction_id, :event_id, :extraction_type, :content, :confidence)
            """,
            {
                "extraction_id": extraction_id,
                "event_id": event.id,
                "extraction_type": "fact",
                "content": {"key": "id_card", "value": "123456789"},
                "confidence": 0.95,
            }
        )
        session.commit()
        
        # 模拟 Neo4j driver
        mock_session = MagicMock()
        mock_driver_instance = MagicMock()
        mock_driver_instance.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver_instance.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_driver.return_value = mock_driver_instance
        
        result = upsert_graph(str(extraction_id), str(event.id), "test_user")
        
        assert result["status"] == "succeeded"
        # 事实类型应该创建用户节点和事实节点
        assert result["total_entities"] == 2
        assert result["total_relations"] == 1
        
        session.close()
    
    @patch("sbo_core.tasks_graph.load_settings")
    @patch("sbo_core.tasks_graph.get_driver")
    def test_upsert_graph_no_graph_data(self, mock_driver, mock_settings, test_db):
        """测试没有图谱数据时跳过"""
        mock_settings.return_value = MagicMock(
            neo4j_enable=True,
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="test",
            neo4j_database="neo4j",
        )
        
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="Test content",
            occurred_at=datetime.now(timezone.utc),
        )
        
        session = test_db.get_session()
        session.add(event)
        session.commit()
        
        extraction_id = uuid.uuid4()
        session.execute(
            """
            INSERT INTO extractions (extraction_id, event_id, extraction_type, content, confidence)
            VALUES (:extraction_id, :event_id, :extraction_type, :content, :confidence)
            """,
            {
                "extraction_id": extraction_id,
                "event_id": event.id,
                "extraction_type": "todo",  # todo 类型不生成图谱数据
                "content": {"content": "记得买牛奶"},
                "confidence": 0.7,
            }
        )
        session.commit()
        
        result = upsert_graph(str(extraction_id), str(event.id), "test_user")
        
        assert result["status"] == "skipped"
        assert result["reason"] == "no_graph_data"
        
        session.close()
    
    @patch("sbo_core.tasks_graph.load_settings")
    @patch("sbo_core.tasks_graph.get_driver")
    def test_upsert_graph_neo4j_error(self, mock_driver, mock_settings, test_db):
        """测试 Neo4j 错误处理"""
        mock_settings.return_value = MagicMock(
            neo4j_enable=True,
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="test",
            neo4j_database="neo4j",
        )
        
        # 模拟 Neo4j driver 抛出异常
        mock_driver.side_effect = Exception("Neo4j connection failed")
        
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="Test content",
            occurred_at=datetime.now(timezone.utc),
        )
        
        session = test_db.get_session()
        session.add(event)
        session.commit()
        
        extraction_id = uuid.uuid4()
        session.execute(
            """
            INSERT INTO extractions (extraction_id, event_id, extraction_type, content, confidence)
            VALUES (:extraction_id, :event_id, :extraction_type, :content, :confidence)
            """,
            {
                "extraction_id": extraction_id,
                "event_id": event.id,
                "extraction_type": "entity",
                "content": {"name": "张三", "entity_type": "person"},
                "confidence": 0.8,
            }
        )
        session.commit()
        
        with pytest.raises(AppError) as exc_info:
            upsert_graph(str(extraction_id), str(event.id), "test_user")
        
        assert exc_info.value.code == ErrorCode.NEO4J_UNAVAILABLE
        
        session.close()
    
    @patch("sbo_core.tasks_graph.load_settings")
    def test_upsert_graph_default_user(self, mock_settings, test_db):
        """测试默认用户ID"""
        mock_settings.return_value = MagicMock(
            neo4j_enable=True,
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="test",
            neo4j_database="neo4j",
        )
        
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="Test content",
            occurred_at=datetime.now(timezone.utc),
        )
        
        session = test_db.get_session()
        session.add(event)
        session.commit()
        
        extraction_id = uuid.uuid4()
        session.execute(
            """
            INSERT INTO extractions (extraction_id, event_id, extraction_type, content, confidence)
            VALUES (:extraction_id, :event_id, :extraction_type, :content, :confidence)
            """,
            {
                "extraction_id": extraction_id,
                "event_id": event.id,
                "extraction_type": "preference",
                "content": {"category": "general", "new_value": "test"},
                "confidence": 0.8,
            }
        )
        session.commit()
        
        # 模拟 Neo4j driver
        with patch("sbo_core.tasks_graph.get_driver") as mock_driver:
            mock_session = MagicMock()
            mock_driver_instance = MagicMock()
            mock_driver_instance.session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_driver_instance.session.return_value.__exit__ = MagicMock(return_value=False)
            mock_driver.return_value = mock_driver_instance
            
            # 不提供 user_id
            result = upsert_graph(str(extraction_id), str(event.id))
            
            # 验证使用了默认用户
            assert result["user_id"] == "default_user"
        
        session.close()


class TestGraphStats:
    """图谱统计信息测试"""
    
    @patch("sbo_core.tasks_graph.load_settings")
    def test_get_graph_stats_disabled(self, mock_settings):
        """测试 Neo4j 禁用时返回禁用状态"""
        mock_settings.return_value = MagicMock(neo4j_enable=False)
        
        stats = get_graph_stats()
        
        assert stats["enabled"] is False
        assert stats["nodes"] == 0
        assert stats["relations"] == 0
    
    @patch("sbo_core.tasks_graph.load_settings")
    @patch("sbo_core.tasks_graph.get_driver")
    def test_get_graph_stats_success(self, mock_driver, mock_settings):
        """测试获取图谱统计信息"""
        mock_settings.return_value = MagicMock(
            neo4j_enable=True,
            neo4j_database="neo4j",
        )
        
        # 模拟 Neo4j driver 返回统计
        mock_session = MagicMock()
        mock_session.run.side_effect = [
            MagicMock(single=lambda: {"cnt": 10}),  # 节点数
            MagicMock(single=lambda: {"cnt": 5}),   # 关系数
            MagicMock(single=lambda: {"cnt": 4}),   # Person 节点
            MagicMock(single=lambda: {"cnt": 3}),   # Event 节点
            MagicMock(single=lambda: {"cnt": 2}),   # Location 节点
            MagicMock(single=lambda: {"cnt": 1}),   # Thing 节点
        ]
        
        mock_driver_instance = MagicMock()
        mock_driver_instance.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver_instance.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_driver.return_value = mock_driver_instance
        
        stats = get_graph_stats("test_user")
        
        assert stats["enabled"] is True
        assert stats["user_id"] == "test_user"
        assert stats["nodes"] == 10
        assert stats["relations"] == 5
        assert stats["by_label"]["Person"] == 4
    
    @patch("sbo_core.tasks_graph.load_settings")
    @patch("sbo_core.tasks_graph.get_driver")
    def test_get_graph_stats_all_users(self, mock_driver, mock_settings):
        """测试获取所有用户的图谱统计（不指定 user_id）"""
        mock_settings.return_value = MagicMock(
            neo4j_enable=True,
            neo4j_database="neo4j",
        )
        
        mock_session = MagicMock()
        mock_session.run.side_effect = [
            MagicMock(single=lambda: {"cnt": 100}),  # 节点数
            MagicMock(single=lambda: {"cnt": 50}),   # 关系数
        ]
        
        mock_driver_instance = MagicMock()
        mock_driver_instance.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver_instance.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_driver.return_value = mock_driver_instance
        
        stats = get_graph_stats()
        
        assert stats["enabled"] is True
        assert stats["nodes"] == 100
        assert stats["relations"] == 50
    
    @patch("sbo_core.tasks_graph.load_settings")
    @patch("sbo_core.tasks_graph.get_driver")
    def test_get_graph_stats_error(self, mock_driver, mock_settings):
        """测试获取统计信息失败"""
        mock_settings.return_value = MagicMock(
            neo4j_enable=True,
            neo4j_database="neo4j",
        )
        
        mock_driver.side_effect = Exception("Connection failed")
        
        stats = get_graph_stats()
        
        assert stats["enabled"] is True
        assert "error" in stats
        assert stats["nodes"] == 0
        assert stats["relations"] == 0


class TestDataProvenance:
    """数据溯源机制测试"""
    
    @patch("sbo_core.tasks_graph.load_settings")
    @patch("sbo_core.tasks_graph.get_driver")
    def test_source_event_id_in_entity(self, mock_driver, mock_settings, test_db):
        """测试实体包含源事件ID"""
        mock_settings.return_value = MagicMock(
            neo4j_enable=True,
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="test",
            neo4j_database="neo4j",
        )
        
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="张三今天去了北京",
            occurred_at=datetime.now(timezone.utc),
        )
        
        session = test_db.get_session()
        session.add(event)
        session.commit()
        
        extraction_id = uuid.uuid4()
        session.execute(
            """
            INSERT INTO extractions (extraction_id, event_id, extraction_type, content, confidence)
            VALUES (:extraction_id, :event_id, :extraction_type, :content, :confidence)
            """,
            {
                "extraction_id": extraction_id,
                "event_id": event.id,
                "extraction_type": "entity",
                "content": {"name": "张三", "entity_type": "person"},
                "confidence": 0.8,
            }
        )
        session.commit()
        
        # 捕获传递给 upsert_entity 的实体
        captured_entities = []
        
        def capture_upsert(session, user_id, entity):
            captured_entities.append(entity)
        
        mock_session = MagicMock()
        mock_driver_instance = MagicMock()
        mock_driver_instance.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver_instance.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_driver.return_value = mock_driver_instance
        
        with patch("sbo_core.tasks_graph.upsert_entity", side_effect=capture_upsert):
            result = upsert_graph(str(extraction_id), str(event.id), "test_user")
        
        assert result["status"] == "succeeded"
        assert result["event_id"] == str(event.id)
        
        # 验证实体包含源事件ID
        if captured_entities:
            assert captured_entities[0].source_event_id == str(event.id)
        
        session.close()
    
    @patch("sbo_core.tasks_graph.load_settings")
    @patch("sbo_core.tasks_graph.get_driver")
    def test_occurred_at_timestamp(self, mock_driver, mock_settings, test_db):
        """测试时间戳传递"""
        mock_settings.return_value = MagicMock(
            neo4j_enable=True,
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="test",
            neo4j_database="neo4j",
        )
        
        occurred_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="Test content",
            occurred_at=occurred_at,
        )
        
        session = test_db.get_session()
        session.add(event)
        session.commit()
        
        extraction_id = uuid.uuid4()
        session.execute(
            """
            INSERT INTO extractions (extraction_id, event_id, extraction_type, content, confidence)
            VALUES (:extraction_id, :event_id, :extraction_type, :content, :confidence)
            """,
            {
                "extraction_id": extraction_id,
                "event_id": event.id,
                "extraction_type": "entity",
                "content": {"name": "张三", "entity_type": "person"},
                "confidence": 0.8,
            }
        )
        session.commit()
        
        captured_entities = []
        
        def capture_upsert(session, user_id, entity):
            captured_entities.append(entity)
        
        mock_session = MagicMock()
        mock_driver_instance = MagicMock()
        mock_driver_instance.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver_instance.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_driver.return_value = mock_driver_instance
        
        with patch("sbo_core.tasks_graph.upsert_entity", side_effect=capture_upsert):
            result = upsert_graph(str(extraction_id), str(event.id), "test_user")
        
        assert result["status"] == "succeeded"
        
        # 验证实体包含正确的时间戳
        if captured_entities:
            assert captured_entities[0].occurred_at == occurred_at
        
        session.close()


class TestEnqueueUpsertGraph:
    """测试入队函数"""
    
    @patch("sbo_core.tasks_graph.enqueue_task")
    def test_enqueue_upsert_graph(self, mock_enqueue):
        """测试图谱更新任务入队"""
        mock_job = MagicMock()
        mock_job.id = "job-123"
        mock_enqueue.return_value = mock_job
        
        extraction_id = uuid.uuid4()
        
        result = enqueue_upsert_graph(
            extraction_id=str(extraction_id),
            event_id="event-123",
            user_id="test_user",
        )
        
        assert result == mock_job
        mock_enqueue.assert_called_once()
        
        # 验证调用参数
        call_args = mock_enqueue.call_args
        assert call_args.kwargs["event_id"] == "event-123"
        assert call_args.kwargs["user_id"] == "test_user"
