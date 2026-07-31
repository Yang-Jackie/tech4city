"""Environment-backed backend configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = BACKEND_ROOT / ".env"
DEFAULT_REPOSITORY_ENV_PATH = BACKEND_ROOT.parent / ".env"
DEFAULT_LAYER1_MODEL_DIR = (
    BACKEND_ROOT.parent
    / "Layer"
    / "cyberbully-roblox-pii-lora-synbullying"
    / "best_model"
)
DEFAULT_LAYER2_CLASSIFIER_HEAD_PATH = (
    BACKEND_ROOT.parent / "data" / "ntu_layer2_classifier_head.pth"
)


class ConfigurationError(RuntimeError):
    """Backend configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    storage: Literal["memory", "mongodb"]
    mongodb_uri: str | None
    mongodb_database: str
    analyzer: Literal[
        "fake", "layer1", "layer1-layer2", "layer3", "layer1-layer2-layer3"
    ] = "fake"
    worker_enabled: bool = True
    worker_poll_seconds: float = 0.25
    layer1_model_dir: Path = DEFAULT_LAYER1_MODEL_DIR
    layer1_pipeline_version: str = "layer1-roblox-pii-lora-synbullying-v1"
    layer2_classifier_head_path: Path = DEFAULT_LAYER2_CLASSIFIER_HEAD_PATH
    layer2_text_embedding_model: str = "google/embeddinggemma-300m"
    layer2_pipeline_version: str = "layer2-skipped-real-user-v1"
    layer3_model: str = "chatgpt-answer"
    layer3_pipeline_version: str = "layer3-chatgpt-answer-v1"

    @classmethod
    def load(
        cls,
        env_path: Path = DEFAULT_ENV_PATH,
        *,
        repository_env_path: Path | None = None,
    ) -> Settings:
        load_dotenv(env_path, override=False)
        fallback_env_path = repository_env_path
        if fallback_env_path is None and env_path == DEFAULT_ENV_PATH:
            fallback_env_path = DEFAULT_REPOSITORY_ENV_PATH
        if fallback_env_path is not None and fallback_env_path != env_path:
            load_dotenv(fallback_env_path, override=False)
        storage = os.getenv("TECH4CITY_STORAGE", "memory").strip().lower()
        if storage not in {"memory", "mongodb"}:
            raise ConfigurationError(
                "TECH4CITY_STORAGE must be either 'memory' or 'mongodb'."
            )

        mongodb_uri = os.getenv("MONGODB_URI", "").strip() or None
        mongodb_database = os.getenv("MONGODB_DATABASE", "tech4city").strip()
        if not mongodb_database:
            raise ConfigurationError("MONGODB_DATABASE must not be blank.")
        if storage == "mongodb" and mongodb_uri is None:
            raise ConfigurationError(
                "MONGODB_URI is required when TECH4CITY_STORAGE=mongodb."
            )
        analyzer = os.getenv("TECH4CITY_ANALYZER", "fake").strip().lower()
        if analyzer not in {
            "fake",
            "layer1",
            "layer1-layer2",
            "layer3",
            "layer1-layer2-layer3",
        }:
            raise ConfigurationError(
                "TECH4CITY_ANALYZER must be 'fake', 'layer1', 'layer1-layer2', "
                "'layer3', or 'layer1-layer2-layer3'."
            )
        if "layer3" in analyzer and not os.getenv("OPENAI_API_KEY", "").strip():
            raise ConfigurationError(
                "OPENAI_API_KEY is required when TECH4CITY_ANALYZER includes Layer 3."
            )
        worker_enabled = _read_bool("TECH4CITY_WORKER_ENABLED", default=True)
        worker_poll_seconds = _read_positive_float(
            "TECH4CITY_WORKER_POLL_SECONDS", default=0.25
        )
        configured_model_dir = os.getenv("TECH4CITY_LAYER1_MODEL_DIR", "").strip()
        layer1_model_dir = (
            Path(configured_model_dir)
            if configured_model_dir
            else DEFAULT_LAYER1_MODEL_DIR
        )
        layer1_pipeline_version = os.getenv(
            "TECH4CITY_LAYER1_PIPELINE_VERSION",
            "layer1-roblox-pii-lora-synbullying-v1",
        ).strip()
        if not layer1_pipeline_version:
            raise ConfigurationError(
                "TECH4CITY_LAYER1_PIPELINE_VERSION must not be blank."
            )
        configured_layer2_head = os.getenv(
            "TECH4CITY_LAYER2_CLASSIFIER_HEAD_PATH", ""
        ).strip()
        layer2_classifier_head_path = (
            Path(configured_layer2_head)
            if configured_layer2_head
            else DEFAULT_LAYER2_CLASSIFIER_HEAD_PATH
        )
        layer2_text_embedding_model = os.getenv(
            "TECH4CITY_LAYER2_TEXT_EMBEDDING_MODEL",
            "google/embeddinggemma-300m",
        ).strip()
        if not layer2_text_embedding_model:
            raise ConfigurationError(
                "TECH4CITY_LAYER2_TEXT_EMBEDDING_MODEL must not be blank."
            )
        layer2_pipeline_version = os.getenv(
            "TECH4CITY_LAYER2_PIPELINE_VERSION",
            "layer2-skipped-real-user-v1",
        ).strip()
        if not layer2_pipeline_version:
            raise ConfigurationError(
                "TECH4CITY_LAYER2_PIPELINE_VERSION must not be blank."
            )
        layer3_model = os.getenv("TECH4CITY_LAYER3_MODEL", "chatgpt-answer").strip()
        if not layer3_model:
            raise ConfigurationError("TECH4CITY_LAYER3_MODEL must not be blank.")
        layer3_pipeline_version = os.getenv(
            "TECH4CITY_LAYER3_PIPELINE_VERSION", "layer3-chatgpt-answer-v1"
        ).strip()
        if not layer3_pipeline_version:
            raise ConfigurationError(
                "TECH4CITY_LAYER3_PIPELINE_VERSION must not be blank."
            )

        return cls(
            storage=storage,
            mongodb_uri=mongodb_uri,
            mongodb_database=mongodb_database,
            analyzer=analyzer,
            worker_enabled=worker_enabled,
            worker_poll_seconds=worker_poll_seconds,
            layer1_model_dir=layer1_model_dir,
            layer1_pipeline_version=layer1_pipeline_version,
            layer2_classifier_head_path=layer2_classifier_head_path,
            layer2_text_embedding_model=layer2_text_embedding_model,
            layer2_pipeline_version=layer2_pipeline_version,
            layer3_model=layer3_model,
            layer3_pipeline_version=layer3_pipeline_version,
        )


def _read_bool(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean value.")


def _read_positive_float(name: str, *, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return value
