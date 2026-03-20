from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from pydantic import AliasChoices
from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    weknora_time_decay_rate: float = Field(0.0, alias="WEKNORA_TIME_DECAY_RATE")
    weknora_semantic_weight: float = Field(0.0, alias="WEKNORA_SEMANTIC_WEIGHT")
    weknora_time_weight: float = Field(0.0, alias="WEKNORA_TIME_WEIGHT")

    @model_validator(mode="before")
    @classmethod
    def _normalize_empty_strings(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        if data.get("WEKNORA_RETRIEVAL_THRESHOLD") == "":
            data["WEKNORA_RETRIEVAL_THRESHOLD"] = None
        if data.get("weknora_retrieval_threshold") == "":
            data["weknora_retrieval_threshold"] = None

        return data

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


def load_settings() -> Settings:
    return Settings()
