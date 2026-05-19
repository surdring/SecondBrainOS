"""
Neo4j 图谱真实集成测试

该脚本连接真实的 Neo4j 数据库进行端到端测试,验证:
1. Neo4j 连接和认证
2. Schema 创建
3. 节点创建和更新
4. 关系创建
5. 查询和统计

注意: 需要配置 NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD 环境变量
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sbo_core.neo4j_graph import (
    get_driver,
    ensure_schema,
    upsert_entity,
    create_relation,
    GraphEntity,
    GraphRelation,
    NODE_LABELS,
    REL_TYPES,
)
from sbo_core.config import load_settings


def test_neo4j_connection():
    """测试 Neo4j 连接"""
    print("\n[1/6] Testing Neo4j connection...")
    
    try:
        settings = load_settings()
        
        if not settings.neo4j_enable:
            print("  ⚠️  Neo4j is disabled in configuration")
            return False
        
        if not settings.neo4j_uri:
            print("  ⚠️  NEO4J_URI not configured")
            return False
        
        driver = get_driver(settings)
        
        # 测试连接
        driver.verify_connectivity()
        
        print(f"  ✓ Connected to Neo4j")
        print(f"    URI: {settings.neo4j_uri}")
        print(f"    Database: {settings.neo4j_database}")
        
        driver.close()
        return True
        
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        return False


def test_schema_creation():
    """测试 Schema 创建"""
    print("\n[2/6] Testing schema creation (REAL DATABASE)...")
    
    try:
        settings = load_settings()
        
        if not settings.neo4j_enable:
            print("  ⚠️  Skipped (Neo4j disabled)")
            return True
        
        driver = get_driver(settings)
        
        with driver.session(database=settings.neo4j_database) as session:
            ensure_schema(session)
            
            # 验证约束是否创建
            result = session.run("SHOW CONSTRAINTS")
            constraints = [record for record in result]
            
            print(f"  ✓ Schema created")
            print(f"    Constraints: {len(constraints)}")
            
            # 验证索引
            result = session.run("SHOW INDEXES")
            indexes = [record for record in result]
            
            print(f"    Indexes: {len(indexes)}")
        
        driver.close()
        return True
        
    except Exception as e:
        print(f"  ✗ Schema creation failed: {e}")
        return False


def test_entity_upsert():
    """测试实体创建和更新 (REAL DATABASE)"""
    print("\n[3/6] Testing entity upsert (REAL DATABASE)...")
    
    try:
        settings = load_settings()
        
        if not settings.neo4j_enable:
            print("  ⚠️  Skipped (Neo4j disabled)")
            return True
        
        driver = get_driver(settings)
        test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        test_entity_id = f"test_entity_{uuid.uuid4().hex[:8]}"
        
        with driver.session(database=settings.neo4j_database) as session:
            # 创建测试实体
            entity = GraphEntity(
                label="Person",
                entity_id=test_entity_id,
                name="测试用户",
                source_event_id=str(uuid.uuid4()),
                occurred_at=datetime.now(timezone.utc),
            )
            
            upsert_entity(session, user_id=test_user_id, entity=entity)
            
            # 验证实体是否创建
            result = session.run(
                """
                MATCH (n:Person {user_id: $user_id, entity_id: $entity_id})
                RETURN n.name as name, n.created_at as created_at
                """,
                user_id=test_user_id,
                entity_id=test_entity_id
            ).single()
            
            if not result:
                print("  ✗ Entity not found after creation")
                driver.close()
                return False
            
            print(f"  ✓ Entity created")
            print(f"    Name: {result['name']}")
            print(f"    Created at: {result['created_at']}")
            
            # 测试更新
            entity.name = "更新后的用户"
            upsert_entity(session, user_id=test_user_id, entity=entity)
            
            result = session.run(
                """
                MATCH (n:Person {user_id: $user_id, entity_id: $entity_id})
                RETURN n.name as name, n.updated_at as updated_at
                """,
                user_id=test_user_id,
                entity_id=test_entity_id
            ).single()
            
            if result['name'] != "更新后的用户":
                print(f"  ✗ Entity update failed: {result['name']}")
                driver.close()
                return False
            
            print(f"  ✓ Entity updated")
            print(f"    New name: {result['name']}")
            
            # 清理测试数据
            session.run(
                "MATCH (n {user_id: $user_id}) DETACH DELETE n",
                user_id=test_user_id
            )
        
        driver.close()
        return True
        
    except Exception as e:
        print(f"  ✗ Entity upsert failed: {e}")
        return False


def test_relation_creation():
    """测试关系创建 (REAL DATABASE)"""
    print("\n[4/6] Testing relation creation (REAL DATABASE)...")
    
    try:
        settings = load_settings()
        
        if not settings.neo4j_enable:
            print("  ⚠️  Skipped (Neo4j disabled)")
            return True
        
        driver = get_driver(settings)
        test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        
        with driver.session(database=settings.neo4j_database) as session:
            # 创建两个实体
            entity1 = GraphEntity(
                label="Person",
                entity_id=f"person1_{uuid.uuid4().hex[:8]}",
                name="张三",
                source_event_id=str(uuid.uuid4()),
                occurred_at=datetime.now(timezone.utc),
            )
            
            entity2 = GraphEntity(
                label="Person",
                entity_id=f"person2_{uuid.uuid4().hex[:8]}",
                name="李四",
                source_event_id=str(uuid.uuid4()),
                occurred_at=datetime.now(timezone.utc),
            )
            
            upsert_entity(session, user_id=test_user_id, entity=entity1)
            upsert_entity(session, user_id=test_user_id, entity=entity2)
            
            # 创建关系
            relation = GraphRelation(
                rel_type="KNOWS",
                from_label="Person",
                from_entity_id=entity1.entity_id,
                to_label="Person",
                to_entity_id=entity2.entity_id,
                source_event_id=str(uuid.uuid4()),
                occurred_at=datetime.now(timezone.utc),
            )
            
            create_relation(session, user_id=test_user_id, rel=relation)
            
            # 验证关系是否创建
            result = session.run(
                """
                MATCH (a:Person {user_id: $user_id, entity_id: $from_id})
                MATCH (b:Person {user_id: $user_id, entity_id: $to_id})
                MATCH (a)-[r:KNOWS {user_id: $user_id}]->(b)
                RETURN r.created_at as created_at
                """,
                user_id=test_user_id,
                from_id=entity1.entity_id,
                to_id=entity2.entity_id
            ).single()
            
            if not result:
                print("  ✗ Relation not found after creation")
                driver.close()
                return False
            
            print(f"  ✓ Relation created")
            print(f"    Type: KNOWS")
            print(f"    From: {entity1.name} -> To: {entity2.name}")
            print(f"    Created at: {result['created_at']}")
            
            # 清理测试数据
            session.run(
                "MATCH (n {user_id: $user_id}) DETACH DELETE n",
                user_id=test_user_id
            )
        
        driver.close()
        return True
        
    except Exception as e:
        print(f"  ✗ Relation creation failed: {e}")
        return False


def test_graph_query():
    """测试图谱查询 (REAL DATABASE)"""
    print("\n[5/6] Testing graph query (REAL DATABASE)...")
    
    try:
        settings = load_settings()
        
        if not settings.neo4j_enable:
            print("  ⚠️  Skipped (Neo4j disabled)")
            return True
        
        driver = get_driver(settings)
        test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        
        with driver.session(database=settings.neo4j_database) as session:
            # 创建测试数据：用户 -> 偏好
            user_entity = GraphEntity(
                label="Person",
                entity_id=f"user_{uuid.uuid4().hex[:8]}",
                name="测试用户",
                source_event_id=str(uuid.uuid4()),
                occurred_at=datetime.now(timezone.utc),
            )
            
            pref_entity = GraphEntity(
                label="Thing",
                entity_id=f"pref_{uuid.uuid4().hex[:8]}",
                name="喜欢喝咖啡",
                source_event_id=str(uuid.uuid4()),
                occurred_at=datetime.now(timezone.utc),
            )
            
            upsert_entity(session, user_id=test_user_id, entity=user_entity)
            upsert_entity(session, user_id=test_user_id, entity=pref_entity)
            
            relation = GraphRelation(
                rel_type="RELATED_TO",
                from_label="Person",
                from_entity_id=user_entity.entity_id,
                to_label="Thing",
                to_entity_id=pref_entity.entity_id,
                source_event_id=str(uuid.uuid4()),
                occurred_at=datetime.now(timezone.utc),
            )
            
            create_relation(session, user_id=test_user_id, rel=relation)
            
            # 查询用户的偏好
            result = session.run(
                """
                MATCH (u:Person {user_id: $user_id})-[r:RELATED_TO]->(p:Thing)
                RETURN u.name as user_name, p.name as pref_name
                """,
                user_id=test_user_id
            ).single()
            
            if not result:
                print("  ✗ Query returned no results")
                driver.close()
                return False
            
            print(f"  ✓ Query successful")
            print(f"    User: {result['user_name']}")
            print(f"    Preference: {result['pref_name']}")
            
            # 清理测试数据
            session.run(
                "MATCH (n {user_id: $user_id}) DETACH DELETE n",
                user_id=test_user_id
            )
        
        driver.close()
        return True
        
    except Exception as e:
        print(f"  ✗ Graph query failed: {e}")
        return False


def test_graph_stats():
    """测试图谱统计"""
    print("\n[6/6] Testing graph statistics...")
    
    try:
        from sbo_core.tasks_graph import get_graph_stats
        
        settings = load_settings()
        
        if not settings.neo4j_enable:
            print("  ⚠️  Skipped (Neo4j disabled)")
            return True
        
        stats = get_graph_stats()
        
        print(f"  ✓ Statistics retrieved")
        print(f"    Enabled: {stats.get('enabled')}")
        print(f"    Total nodes: {stats.get('nodes', 0)}")
        print(f"    Total relations: {stats.get('relations', 0)}")
        
        if 'by_label' in stats:
            print(f"    By label:")
            for label, count in stats['by_label'].items():
                print(f"      - {label}: {count}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Statistics failed: {e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("Neo4j Graph Real Integration Test")
    print("=" * 60)
    
    # 检查环境
    try:
        settings = load_settings()
        print(f"\nEnvironment check:")
        
        if settings.neo4j_enable:
            print(f"  Neo4j Enabled: Yes")
            print(f"  URI: {settings.neo4j_uri}")
            print(f"  Database: {settings.neo4j_database}")
            print(f"  User: {settings.neo4j_user}")
        else:
            print("  ⚠️  Neo4j is disabled")
            print("  This test will skip real database operations")
    except Exception as e:
        print(f"\n✗ Configuration error: {e}")
        return 1
    
    results = []
    
    # 执行测试
    results.append(("Neo4j Connection", test_neo4j_connection()))
    results.append(("Schema Creation", test_schema_creation()))
    results.append(("Entity Upsert", test_entity_upsert()))
    results.append(("Relation Creation", test_relation_creation()))
    results.append(("Graph Query", test_graph_query()))
    results.append(("Graph Statistics", test_graph_stats()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    failed = sum(1 for _, r in results if not r)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n🎉 All real Neo4j integration tests passed!")
        return 0
    else:
        print(f"\n⚠️ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
