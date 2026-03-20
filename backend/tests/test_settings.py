import pytest

from sbo_core.config import Settings


def test_settings_load_success(env_base: None) -> None:
    settings = Settings(_env_file=None)
    assert settings.postgres_dsn
    assert settings.redis_url
    assert settings.neo4j_uri


def test_settings_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_USERNAME", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("LLM_LLAMA_BASE_URL", raising=False)

    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_settings_weknora_enabled_missing_required_raises(env_base: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEKNORA_ENABLE", "true")
    monkeypatch.delenv("WEKNORA_BASE_URL", raising=False)
    monkeypatch.delenv("WEKNORA_API_KEY", raising=False)
    monkeypatch.delenv("WEKNORA_REQUEST_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("WEKNORA_RETRIEVAL_TOP_K", raising=False)
    monkeypatch.delenv("WEKNORA_TIME_DECAY_RATE", raising=False)
    monkeypatch.delenv("WEKNORA_SEMANTIC_WEIGHT", raising=False)
    monkeypatch.delenv("WEKNORA_TIME_WEIGHT", raising=False)

    with pytest.raises(Exception):
        Settings(_env_file=None)


def _set_weknora_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEKNORA_ENABLE", "true")
    monkeypatch.setenv("WEKNORA_BASE_URL", "http://localhost:8080/api/v1")
    monkeypatch.setenv("WEKNORA_API_KEY", "test")
    monkeypatch.setenv("WEKNORA_REQUEST_TIMEOUT_MS", "10000")
    monkeypatch.setenv("WEKNORA_RETRIEVAL_TOP_K", "8")
    monkeypatch.setenv("WEKNORA_RETRIEVAL_THRESHOLD", "0.2")
    monkeypatch.setenv("WEKNORA_TIME_DECAY_RATE", "0.1")
    monkeypatch.setenv("WEKNORA_SEMANTIC_WEIGHT", "0.7")
    monkeypatch.setenv("WEKNORA_TIME_WEIGHT", "0.3")


def test_settings_weknora_enabled_invalid_base_url_raises(env_base: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_weknora_valid(monkeypatch)
    monkeypatch.setenv("WEKNORA_BASE_URL", "localhost:8080")
    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_settings_weknora_enabled_timeout_out_of_range_raises(env_base: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_weknora_valid(monkeypatch)
    monkeypatch.setenv("WEKNORA_REQUEST_TIMEOUT_MS", "10")
    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_settings_weknora_enabled_top_k_out_of_range_raises(env_base: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_weknora_valid(monkeypatch)
    monkeypatch.setenv("WEKNORA_RETRIEVAL_TOP_K", "0")
    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_settings_weknora_enabled_threshold_out_of_range_raises(env_base: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_weknora_valid(monkeypatch)
    monkeypatch.setenv("WEKNORA_RETRIEVAL_THRESHOLD", "1.2")
    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_settings_weknora_enabled_weights_not_sum_to_one_raises(env_base: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_weknora_valid(monkeypatch)
    monkeypatch.setenv("WEKNORA_SEMANTIC_WEIGHT", "0.6")
    monkeypatch.setenv("WEKNORA_TIME_WEIGHT", "0.3")
    with pytest.raises(Exception):
        Settings(_env_file=None)
