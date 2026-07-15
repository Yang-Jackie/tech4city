"""Configuration loading for the standalone TDLib utility."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv, set_key


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"


class ConfigurationError(RuntimeError):
    """Raised when TDLib configuration is missing or invalid."""


def _resolve_path(value: str, default: str) -> Path:
    path = Path(value or default).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true or false, not {value!r}.")


def _ensure_database_key(env_path: Path) -> str:
    key = os.getenv("TDLIB_DATABASE_ENCRYPTION_KEY", "").strip()
    if key:
        return key

    key = secrets.token_urlsafe(32)
    env_path.touch(exist_ok=True)
    set_key(str(env_path), "TDLIB_DATABASE_ENCRYPTION_KEY", key, quote_mode="never")
    os.environ["TDLIB_DATABASE_ENCRYPTION_KEY"] = key
    print(f"Generated a persistent TDLib database encryption key in {env_path}.")
    return key


@dataclass(frozen=True)
class TdlibConfig:
    api_id: int
    api_hash: str
    tdjson_path: Path
    database_directory: Path
    files_directory: Path
    log_directory: Path
    database_encryption_key: str
    use_test_dc: bool

    @classmethod
    def load(cls, env_path: Path = DEFAULT_ENV_PATH) -> "TdlibConfig":
        env_path = env_path.resolve()
        load_dotenv(env_path, override=False)
        database_key = _ensure_database_key(env_path)

        api_id_raw = os.getenv("TELEGRAM_API_ID", "").strip()
        api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
        if not api_id_raw or not api_hash:
            raise ConfigurationError(
                f"Set TELEGRAM_API_ID and TELEGRAM_API_HASH in {env_path}. "
                "Obtain them from https://my.telegram.org."
            )
        try:
            api_id = int(api_id_raw)
        except ValueError as exc:
            raise ConfigurationError("TELEGRAM_API_ID must be an integer.") from exc
        if api_id <= 0:
            raise ConfigurationError("TELEGRAM_API_ID must be positive.")

        use_test_dc = _parse_bool(
            os.getenv("TDLIB_USE_TEST_DC", "false"), "TDLIB_USE_TEST_DC"
        )
        if use_test_dc:
            raise ConfigurationError(
                "This utility was approved for a real production account. "
                "Set TDLIB_USE_TEST_DC=false."
            )

        config = cls(
            api_id=api_id,
            api_hash=api_hash,
            tdjson_path=_resolve_path(
                os.getenv("TDJSON_PATH", ""),
                "telegram/.tdlib-build/install/bin/tdjson.dll",
            ),
            database_directory=_resolve_path(
                os.getenv("TDLIB_DATABASE_DIR", ""),
                "telegram/.tdlib/production/database",
            ),
            files_directory=_resolve_path(
                os.getenv("TDLIB_FILES_DIR", ""),
                "telegram/.tdlib/production/files",
            ),
            log_directory=_resolve_path(
                os.getenv("TDLIB_LOG_DIR", ""),
                "telegram/.tdlib/production/logs",
            ),
            database_encryption_key=database_key,
            use_test_dc=use_test_dc,
        )
        if not config.tdjson_path.is_file():
            raise ConfigurationError(
                f"TDLib library not found at {config.tdjson_path}. "
                "Run scripts/build_tdlib.ps1 first."
            )
        for directory in (
            config.database_directory,
            config.files_directory,
            config.log_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return config
