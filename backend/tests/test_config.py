from __future__ import annotations

import os
from pathlib import Path

import pytest
from app.config import ConfigurationError, Settings

ENVIRONMENT_NAMES = (
    "TECH4CITY_STORAGE",
    "MONGODB_URI",
    "MONGODB_DATABASE",
    "TECH4CITY_ANALYZER",
    "TECH4CITY_WORKER_ENABLED",
    "TECH4CITY_WORKER_POLL_SECONDS",
    "TECH4CITY_LAYER1_MODEL_DIR",
    "TECH4CITY_LAYER1_PIPELINE_VERSION",
    "TECH4CITY_LAYER2_CLASSIFIER_HEAD_PATH",
    "TECH4CITY_LAYER2_TEXT_EMBEDDING_MODEL",
    "TECH4CITY_LAYER2_PIPELINE_VERSION",
    "TECH4CITY_LAYER3_MODEL",
    "TECH4CITY_LAYER3_PIPELINE_VERSION",
    "OPENAI_API_KEY",
)
MISSING_ENV = Path(__file__).with_name("missing-test.env")


def clear_storage_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_settings_default_to_offline_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_storage_environment(monkeypatch)

    settings = Settings.load(MISSING_ENV)

    assert settings.storage == "memory"
    assert settings.mongodb_uri is None
    assert settings.mongodb_database == "tech4city"
    assert settings.analyzer == "fake"
    assert settings.worker_enabled is True
    assert settings.worker_poll_seconds == 0.25
    assert settings.layer1_model_dir.is_absolute()
    assert settings.layer1_pipeline_version == "layer1-roblox-pii-lora-synbullying-v1"
    assert settings.layer2_classifier_head_path.is_absolute()
    assert settings.layer2_text_embedding_model == "google/embeddinggemma-300m"
    assert settings.layer2_pipeline_version == "layer2-skipped-real-user-v1"
    assert settings.layer3_model == "chatgpt-answer"
    assert settings.layer3_pipeline_version == "layer3-chatgpt-answer-v1"


def test_mongodb_storage_requires_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_storage_environment(monkeypatch)
    monkeypatch.setenv("TECH4CITY_STORAGE", "mongodb")

    with pytest.raises(ConfigurationError, match="MONGODB_URI is required"):
        Settings.load(MISSING_ENV)


def test_settings_load_mongodb_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_storage_environment(monkeypatch)
    monkeypatch.setenv("TECH4CITY_STORAGE", "mongodb")
    monkeypatch.setenv("MONGODB_URI", "mongodb://database.test:27017/")
    monkeypatch.setenv("MONGODB_DATABASE", "tech4city_test")

    settings = Settings.load(MISSING_ENV)

    assert settings.storage == "mongodb"
    assert settings.mongodb_uri == "mongodb://database.test:27017/"
    assert settings.mongodb_database == "tech4city_test"


def test_settings_load_layer1_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_storage_environment(monkeypatch)
    model_dir = Path("C:/approved-model")
    monkeypatch.setenv("TECH4CITY_ANALYZER", "layer1")
    monkeypatch.setenv("TECH4CITY_WORKER_ENABLED", "false")
    monkeypatch.setenv("TECH4CITY_WORKER_POLL_SECONDS", "1.5")
    monkeypatch.setenv("TECH4CITY_LAYER1_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("TECH4CITY_LAYER1_PIPELINE_VERSION", "layer1-test-v2")

    settings = Settings.load(MISSING_ENV)

    assert settings.analyzer == "layer1"
    assert settings.worker_enabled is False
    assert settings.worker_poll_seconds == 1.5
    assert settings.layer1_model_dir == model_dir
    assert settings.layer1_pipeline_version == "layer1-test-v2"


def test_settings_load_layer1_layer2_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_storage_environment(monkeypatch)
    classifier_head = Path("C:/approved-layer2-head.pth")
    monkeypatch.setenv("TECH4CITY_ANALYZER", "layer1-layer2")
    monkeypatch.setenv("TECH4CITY_LAYER2_CLASSIFIER_HEAD_PATH", str(classifier_head))
    monkeypatch.setenv("TECH4CITY_LAYER2_TEXT_EMBEDDING_MODEL", "approved-text-encoder")
    monkeypatch.setenv("TECH4CITY_LAYER2_PIPELINE_VERSION", "layer2-test-v2")

    settings = Settings.load(MISSING_ENV)

    assert settings.analyzer == "layer1-layer2"
    assert settings.layer2_classifier_head_path == classifier_head
    assert settings.layer2_text_embedding_model == "approved-text-encoder"
    assert settings.layer2_pipeline_version == "layer2-test-v2"


def test_settings_load_layer3_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_storage_environment(monkeypatch)
    monkeypatch.setenv("TECH4CITY_ANALYZER", "layer3")
    monkeypatch.setenv("TECH4CITY_LAYER3_MODEL", "approved-layer3-model")
    monkeypatch.setenv("TECH4CITY_LAYER3_PIPELINE_VERSION", "layer3-test-v2")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    settings = Settings.load(MISSING_ENV)

    assert settings.analyzer == "layer3"
    assert settings.layer3_model == "approved-layer3-model"
    assert settings.layer3_pipeline_version == "layer3-test-v2"


def test_settings_load_repository_env_as_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clear_storage_environment(monkeypatch)
    backend_env = tmp_path / "backend.env"
    repository_env = tmp_path / "repository.env"
    backend_env.write_text("TECH4CITY_ANALYZER=layer3\n", encoding="utf-8")
    repository_env.write_text(
        "OPENAI_API_KEY=test-repository-key\n",
        encoding="utf-8",
    )

    settings = Settings.load(
        backend_env,
        repository_env_path=repository_env,
    )

    assert settings.analyzer == "layer3"
    assert os.getenv("OPENAI_API_KEY") == "test-repository-key"


def test_layer3_requires_openai_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clear_storage_environment(monkeypatch)
    env_path = tmp_path / "layer3.env"
    env_path.write_text("TECH4CITY_ANALYZER=layer3\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY is required"):
        Settings.load(env_path)


@pytest.mark.parametrize(
    ("name", "value", "match"),
    [
        ("TECH4CITY_ANALYZER", "unsupported", "must be"),
        ("TECH4CITY_WORKER_ENABLED", "sometimes", "boolean"),
        ("TECH4CITY_WORKER_POLL_SECONDS", "0", "greater than zero"),
    ],
)
def test_invalid_runtime_configuration_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    match: str,
) -> None:
    clear_storage_environment(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match=match):
        Settings.load(MISSING_ENV)
