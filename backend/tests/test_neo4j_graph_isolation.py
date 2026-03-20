from __future__ import annotations

import uuid

import pytest
from neo4j import GraphDatabase

from sbo_core.config import Settings
from sbo_core.neo4j_graph import GraphEntity
from sbo_core.neo4j_graph import GraphRelation
from sbo_core.neo4j_graph import count_nodes
from sbo_core.neo4j_graph import count_rels
from sbo_core.neo4j_graph import create_relation
from sbo_core.neo4j_graph import delete_user_subgraph
from sbo_core.neo4j_graph import ensure_schema
from sbo_core.neo4j_graph import upsert_entity

def test_neo4j_user_id_subgraph_isolation(env_base: None) -> None:
    settings = Settings(_env_file=None)
    if not settings.neo4j_enable:
        pytest.skip("NEO4J_ENABLE is false")

    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    user_a = "user_a_" + uuid.uuid4().hex[:8]
    user_b = "user_b_" + uuid.uuid4().hex[:8]

    try:
        with driver.session(database=settings.neo4j_database) as session:
            ensure_schema(session)

            delete_user_subgraph(session, user_id=user_a)
            delete_user_subgraph(session, user_id=user_b)

            upsert_entity(session, user_id=user_a, entity=GraphEntity(label="Person", entity_id="p1", name="Alice"))
            upsert_entity(session, user_id=user_a, entity=GraphEntity(label="Event", entity_id="e1", name="Meeting"))
            create_relation(
                session,
                user_id=user_a,
                rel=GraphRelation(
                    rel_type="PARTICIPATED_IN",
                    from_label="Person",
                    from_entity_id="p1",
                    to_label="Event",
                    to_entity_id="e1",
                ),
            )

            upsert_entity(session, user_id=user_b, entity=GraphEntity(label="Person", entity_id="p2", name="Bob"))
            upsert_entity(session, user_id=user_b, entity=GraphEntity(label="Event", entity_id="e2", name="Dinner"))
            create_relation(
                session,
                user_id=user_b,
                rel=GraphRelation(
                    rel_type="PARTICIPATED_IN",
                    from_label="Person",
                    from_entity_id="p2",
                    to_label="Event",
                    to_entity_id="e2",
                ),
            )

            assert count_nodes(session, user_id=user_a) == 2
            assert count_rels(session, user_id=user_a) == 1
            assert count_nodes(session, user_id=user_b) == 2
            assert count_rels(session, user_id=user_b) == 1

            delete_user_subgraph(session, user_id=user_a)
            assert count_nodes(session, user_id=user_a) == 0
            assert count_rels(session, user_id=user_a) == 0

            assert count_nodes(session, user_id=user_b) == 2
            assert count_rels(session, user_id=user_b) == 1

    finally:
        driver.close()
