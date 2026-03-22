from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from pydantic import AliasChoices
from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sbo_core.degradation import DegradationStrategy


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        extra="ignore",
    )

    postgres_dsn: str = Field(
        ...,
        validation_alias=AliasChoices("POSTGRES_DSN", "DATABASE_URL"),
    )
    redis_url: str = Field(..., alias="REDIS_URL")
    rq_queue_name: str = Field("sbo_default", alias="RQ_QUEUE_NAME")

    neo4j_enable: bool = Field(False, alias="NEO4J_ENABLE")

    neo4j_uri: str = Field(..., alias="NEO4J_URI")
    neo4j_user: str = Field(
        ...,
        validation_alias=AliasChoices("NEO4J_USER", "NEO4J_USERNAME"),
    )
    neo4j_password: str = Field(..., alias="NEO4J_PASSWORD")
    neo4j_database: str = Field("neo4j", alias="NEO4J_DATABASE")

    llm_llama_base_url: str = Field(..., alias="LLM_LLAMA_BASE_URL")
    llm_llama_api_key: str = Field("", alias="LLM_LLAMA_API_KEY")
    llm_llama_model_id: str = Field("", alias="LLM_LLAMA_MODEL_ID")

    provider_base_url: str = Field("", alias="PROVIDER_BASE_URL")
    provider_api_key: str = Field("", alias="PROVIDER_API_KEY")
    provider_model_id: str = Field("", alias="PROVIDER_MODEL_ID")

    siliconflow_base_url: str = Field("", alias="SILICONFLOW_BASE_URL")
    siliconflow_api_key: str = Field("", alias="SILICONFLOW_API_KEY")
    siliconflow_embedding_model: str = Field("", alias="SILICONFLOW_EMBEDDING_MODEL")

    weknora_enable: bool = Field(False, alias="WEKNORA_ENABLE")
    weknora_base_url: str = Field("", alias="WEKNORA_BASE_URL")
    weknora_api_key: str = Field("", alias="WEKNORA_API_KEY")
    weknora_request_timeout_ms: int = Field(0, alias="WEKNORA_REQUEST_TIMEOUT_MS")
    weknora_retrieval_top_k: int = Field(0, alias="WEKNORA_RETRIEVAL_TOP_K")
    weknora_retrieval_threshold: float | None = Field(None, alias="WEKNORA_RETRIEVAL_THRESHOLD")
    weknora_knowledge_base_id: str = Field("", alias="WEKNORA_KNOWLEDGE_BASE_ID")
    weknora_knowledge_base_ids_raw: str = Field("", alias="WEKNORA_KNOWLEDGE_BASE_IDS")
    weknora_time_decay_rate: float = Field(0.0, alias="WEKNORA_TIME_DECAY_RATE")
    weknora_semantic_weight: float = Field(0.0, alias="WEKNORA_SEMANTIC_WEIGHT")
    weknora_time_weight: float = Field(0.0, alias="WEKNORA_TIME_WEIGHT")
    weknora_degradation_strategy: DegradationStrategy = Field(
        DegradationStrategy.FAIL,
        alias="WEKNORA_DEGRADATION_STRATEGY",
    )

    rerank_provider_url: str = Field("", alias="RERANK_PROVIDER_URL")
    rerank_api_key: str = Field("", alias="RERANK_API_KEY")
    rerank_model_id: str = Field("", alias="RERANK_MODEL_ID")
    rerank_timeout_ms: int = Field(150, alias="RERANK_TIMEOUT_MS")
    rerank_weight: float = Field(0.5, alias="RERANK_WEIGHT")
    rerank_max_candidates: int = Field(20, alias="RERANK_MAX_CANDIDATES")

    @model_validator(mode="before")
    @classmethod
    def _normalize_empty_strings(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        if data.get("WEKNORA_RETRIEVAL_THRESHOLD") == "":
            data["WEKNORA_RETRIEVAL_THRESHOLD"] = None
        if data.get("weknora_retrieval_threshold") == "":
            data["weknora_retrieval_threshold"] = None

        if data.get("WEKNORA_KNOWLEDGE_BASE_ID") == "":
            data["WEKNORA_KNOWLEDGE_BASE_ID"] = ""
        if data.get("weknora_knowledge_base_id") == "":
            data["weknora_knowledge_base_id"] = ""

        if data.get("WEKNORA_KNOWLEDGE_BASE_IDS") == "":
            data["WEKNORA_KNOWLEDGE_BASE_IDS"] = ""
        if data.get("weknora_knowledge_base_ids_raw") == "":
            data["weknora_knowledge_base_ids_raw"] = ""

        return data

    @property
    def weknora_knowledge_base_ids(self) -> list[str] | None:
        s = (self.weknora_knowledge_base_ids_raw or "").strip()
        if not s:
            return None

        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list) and all(isinstance(x, str) and x for x in parsed):
                    return parsed
            except Exception:
                return None

        parts = [p.strip() for p in s.split(",") if p.strip()]
        return parts or None

    @model_validator(mode="after")
    def _validate_weknora(self) -> "Settings":
        if not self.weknora_enable:
            return self

        missing: list[str] = []
        if not self.weknora_base_url:
            missing.append("WEKNORA_BASE_URL")
        if not self.weknora_api_key:
            missing.append("WEKNORA_API_KEY")
        if self.weknora_request_timeout_ms <= 0:
            missing.append("WEKNORA_REQUEST_TIMEOUT_MS")
        if self.weknora_retrieval_top_k <= 0:
            missing.append("WEKNORA_RETRIEVAL_TOP_K")
        if self.weknora_time_decay_rate <= 0:
            missing.append("WEKNORA_TIME_DECAY_RATE")
        if self.weknora_semantic_weight <= 0:
            missing.append("WEKNORA_SEMANTIC_WEIGHT")
        if self.weknora_time_weight <= 0:
            missing.append("WEKNORA_TIME_WEIGHT")

        if missing:
            raise ValueError(f"Missing required WeKnora settings because WEKNORA_ENABLE=true: {', '.join(missing)}")

        parsed = urlparse(self.weknora_base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Invalid WEKNORA_BASE_URL (expected http(s) URL)")

        if not (100 <= self.weknora_request_timeout_ms <= 600_000):
            raise ValueError("Invalid WEKNORA_REQUEST_TIMEOUT_MS (expected 100..600000 milliseconds)")

        if not (1 <= self.weknora_retrieval_top_k <= 100):
            raise ValueError("Invalid WEKNORA_RETRIEVAL_TOP_K (expected 1..100)")

        if self.weknora_retrieval_threshold is not None and not (0.0 <= self.weknora_retrieval_threshold <= 1.0):
            raise ValueError("Invalid WEKNORA_RETRIEVAL_THRESHOLD (expected 0..1)")

        if not (0.0 < self.weknora_time_decay_rate <= 10.0):
            raise ValueError("Invalid WEKNORA_TIME_DECAY_RATE (expected >0 and <=10)")

        if not (0.0 < self.weknora_semantic_weight <= 1.0):
            raise ValueError("Invalid WEKNORA_SEMANTIC_WEIGHT (expected >0 and <=1)")
        if not (0.0 < self.weknora_time_weight <= 1.0):
            raise ValueError("Invalid WEKNORA_TIME_WEIGHT (expected >0 and <=1)")

        weight_sum = self.weknora_semantic_weight + self.weknora_time_weight
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError("Invalid WeKnora weights: WEKNORA_SEMANTIC_WEIGHT + WEKNORA_TIME_WEIGHT must equal 1")

        return self

    @model_validator(mode="after")
    def _validate_rerank(self) -> "Settings":
        if not self.rerank_provider_url:
            return self

        parsed = urlparse(self.rerank_provider_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Invalid RERANK_PROVIDER_URL (expected http(s) URL)")

        if not (50 <= self.rerank_timeout_ms <= 60_000):
            raise ValueError("Invalid RERANK_TIMEOUT_MS (expected 50..60000 milliseconds)")

        if not (0.0 <= self.rerank_weight <= 1.0):
            raise ValueError("Invalid RERANK_WEIGHT (expected 0..1)")

        if not (1 <= self.rerank_max_candidates <= 100):
            raise ValueError("Invalid RERANK_MAX_CANDIDATES (expected 1..100)")

        return self


def load_settings() -> Settings:
    return Settings()
