from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from neo4j import Driver
from neo4j import GraphDatabase
from neo4j import Session

from sbo_core.config import Settings


@dataclass(frozen=True)
class GraphEntity:
    label: str
    entity_id: str
    name: str | None = None
    source_event_id: str | None = None
    occurred_at: datetime | None = None


@dataclass(frozen=True)
class GraphRelation:
    rel_type: str
    from_label: str
    from_entity_id: str
    to_label: str
    to_entity_id: str
    source_event_id: str | None = None
    occurred_at: datetime | None = None


NODE_LABELS: tuple[str, ...] = ("Person", "Event", "Location", "Thing")
REL_TYPES: tuple[str, ...] = ("PARTICIPATED_IN", "OCCURRED_AT", "RELATED_TO", "KNOWS")


def get_driver(settings: Settings) -> Driver:
    return GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))


def ensure_schema(session: Session) -> None:
    for label in NODE_LABELS:
        session.run(
            f"CREATE CONSTRAINT sbo_{label.lower()}_user_entity_unique IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE (n.user_id, n.entity_id) IS UNIQUE"
        )

    for label in NODE_LABELS:
        session.run(
            f"CREATE INDEX sbo_{label.lower()}_user_id_idx IF NOT EXISTS "
            f"FOR (n:{label}) ON (n.user_id)"
        )


def upsert_entity(session: Session, *, user_id: str, entity: GraphEntity) -> None:
    if entity.label not in NODE_LABELS:
        raise ValueError("Unsupported node label")

    props: dict[str, object] = {
        "user_id": user_id,
        "entity_id": entity.entity_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if entity.name is not None:
        props["name"] = entity.name
    if entity.source_event_id is not None:
        props["source_event_id"] = entity.source_event_id
    if entity.occurred_at is not None:
        props["occurred_at"] = entity.occurred_at.isoformat()

    session.run(
        f"""
        MERGE (n:{entity.label} {{user_id: $user_id, entity_id: $entity_id}})
        ON CREATE SET n.created_at = $created_at
        SET n += $props
        """.strip(),
        user_id=user_id,
        entity_id=entity.entity_id,
        created_at=datetime.utcnow().isoformat(),
        props=props,
    )


def create_relation(session: Session, *, user_id: str, rel: GraphRelation) -> None:
    if rel.rel_type not in REL_TYPES:
        raise ValueError("Unsupported relationship type")
    if rel.from_label not in NODE_LABELS or rel.to_label not in NODE_LABELS:
        raise ValueError("Unsupported node label")

    props: dict[str, object] = {
        "user_id": user_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if rel.source_event_id is not None:
        props["source_event_id"] = rel.source_event_id
    if rel.occurred_at is not None:
        props["occurred_at"] = rel.occurred_at.isoformat()

    session.run(
        f"""
        MATCH (a:{rel.from_label} {{user_id: $user_id, entity_id: $from_entity_id}})
        MATCH (b:{rel.to_label} {{user_id: $user_id, entity_id: $to_entity_id}})
        MERGE (a)-[r:{rel.rel_type} {{user_id: $user_id}}]->(b)
        ON CREATE SET r.created_at = $created_at
        SET r += $props
        """.strip(),
        user_id=user_id,
        from_entity_id=rel.from_entity_id,
        to_entity_id=rel.to_entity_id,
        created_at=datetime.utcnow().isoformat(),
        props=props,
    )


def count_nodes(session: Session, *, user_id: str) -> int:
    result = session.run(
        """
        MATCH (n) WHERE n.user_id = $user_id
        RETURN count(n) AS cnt
        """.strip(),
        user_id=user_id,
    )
    row = result.single()
    return int(row["cnt"]) if row else 0


def count_rels(session: Session, *, user_id: str) -> int:
    result = session.run(
        """
        MATCH ()-[r]->() WHERE r.user_id = $user_id
        RETURN count(r) AS cnt
        """.strip(),
        user_id=user_id,
    )
    row = result.single()
    return int(row["cnt"]) if row else 0


def delete_user_subgraph(session: Session, *, user_id: str) -> None:
    session.run(
        """
        MATCH (n) WHERE n.user_id = $user_id
        DETACH DELETE n
        """.strip(),
        user_id=user_id,
    )
