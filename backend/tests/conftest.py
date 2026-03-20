import os
from pathlib import Path

import pytest


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    force_override = {
        "NEO4J_ENABLE",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
    }
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if not k:
            continue
        if k in force_override or k not in os.environ:
            os.environ[k] = v


@pytest.fixture()
def env_base(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_env_file(Path(__file__).resolve().parents[1] / ".env")

    if "POSTGRES_DSN" not in os.environ and os.environ.get("DATABASE_URL"):
        os.environ["POSTGRES_DSN"] = os.environ["DATABASE_URL"]

    monkeypatch.setenv(
        "POSTGRES_DSN",
        os.environ.get("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/secondbrainos"),
    )
    monkeypatch.setenv("REDIS_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    monkeypatch.setenv("NEO4J_URI", os.environ.get("NEO4J_URI", "neo4j://localhost:7687"))
    monkeypatch.setenv("NEO4J_USER", os.environ.get("NEO4J_USER", "neo4j"))
    monkeypatch.setenv("NEO4J_PASSWORD", os.environ.get("NEO4J_PASSWORD", "password"))
    monkeypatch.setenv("LLM_LLAMA_BASE_URL", os.environ.get("LLM_LLAMA_BASE_URL", "http://localhost:11434"))

    monkeypatch.setenv("LLM_LLAMA_API_KEY", os.environ.get("LLM_LLAMA_API_KEY", ""))
    monkeypatch.setenv("LLM_LLAMA_MODEL_ID", os.environ.get("LLM_LLAMA_MODEL_ID", ""))
    monkeypatch.setenv("PROVIDER_BASE_URL", os.environ.get("PROVIDER_BASE_URL", ""))
    monkeypatch.setenv("PROVIDER_API_KEY", os.environ.get("PROVIDER_API_KEY", ""))
    monkeypatch.setenv("PROVIDER_MODEL_ID", os.environ.get("PROVIDER_MODEL_ID", ""))
    monkeypatch.setenv("SILICONFLOW_BASE_URL", os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"))
    monkeypatch.setenv("SILICONFLOW_API_KEY", os.environ.get("SILICONFLOW_API_KEY", ""))
    monkeypatch.setenv("SILICONFLOW_EMBEDDING_MODEL", os.environ.get("SILICONFLOW_EMBEDDING_MODEL", ""))

    os.environ.pop("_SBO_SETTINGS_CACHE", None)
