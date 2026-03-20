from __future__ import annotations

from sbo_core.config import Settings
from sbo_core.rq import get_queue


def test_get_queue_uses_default_name(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/secondbrainos")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("NEO4J_URI", "neo4j://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "password")
    monkeypatch.setenv("LLM_LLAMA_BASE_URL", "http://localhost:11434")

    settings = Settings(_env_file=None)
    q = get_queue(settings)
    assert q.name == settings.rq_queue_name


def test_get_queue_uses_override_name(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/secondbrainos")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("NEO4J_URI", "neo4j://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "password")
    monkeypatch.setenv("LLM_LLAMA_BASE_URL", "http://localhost:11434")

    settings = Settings(_env_file=None)
    q = get_queue(settings, name="custom")
    assert q.name == "custom"
