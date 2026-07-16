"""Environment-backed backend configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = BACKEND_ROOT / ".env"


class ConfigurationError(RuntimeError):
    """Backend configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    storage: Literal["memory", "mongodb"]
    mongodb_uri: str | None
    mongodb_database: str

    @classmethod
    def load(cls, env_path: Path = DEFAULT_ENV_PATH) -> Settings:
        load_dotenv(env_path, override=False)
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

        return cls(
            storage=storage,
            mongodb_uri=mongodb_uri,
            mongodb_database=mongodb_database,
        )
