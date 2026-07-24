"""Real-time bridge from TDLib new-text updates to the FastAPI backend."""

from __future__ import annotations

import os
import queue
import sys
import threading
from dataclasses import dataclass
from typing import Any

from .auth import AuthorizationError, authorize
from .backend_client import BackendClient, BackendUnavailable
from .config import ConfigurationError, TdlibConfig
from .normalization import (
    NormalizationError,
    NormalizedMessage,
    message_identity,
    normalize_new_text_message,
)
from .tdjson_client import TdJsonClient


@dataclass(frozen=True)
class BridgeConfig:
    backend_url: str
    request_timeout: float
    initial_backoff: float
    max_backoff: float
    allowed_chat_ids: frozenset[int]

    @classmethod
    def load(cls) -> BridgeConfig:
        return cls(
            backend_url=os.getenv(
                "TECH4CITY_BACKEND_URL",
                "http://127.0.0.1:8765",
            ).strip(),
            request_timeout=_positive_float(
                "TECH4CITY_BRIDGE_TIMEOUT_SECONDS",
                default=10.0,
            ),
            initial_backoff=_positive_float(
                "TECH4CITY_BRIDGE_INITIAL_BACKOFF_SECONDS",
                default=0.5,
            ),
            max_backoff=_positive_float(
                "TECH4CITY_BRIDGE_MAX_BACKOFF_SECONDS",
                default=30.0,
            ),
            allowed_chat_ids=_chat_id_allowlist("TECH4CITY_BRIDGE_ALLOWED_CHAT_IDS"),
        )


class TelegramBackendBridge:
    """Queue TDLib updates quickly and deliver normalized messages in order."""

    def __init__(
        self,
        backend: BackendClient,
        *,
        telegram_account_id: int | None = None,
        allowed_chat_ids: frozenset[int] | set[int] = frozenset(),
        initial_backoff: float = 0.5,
        max_backoff: float = 30.0,
    ) -> None:
        if initial_backoff <= 0 or max_backoff <= 0:
            raise ValueError("bridge backoff values must be positive")
        if initial_backoff > max_backoff:
            raise ValueError("initial bridge backoff cannot exceed maximum backoff")
        self._backend = backend
        self._telegram_account_id = telegram_account_id
        self._allowed_chat_ids = frozenset(allowed_chat_ids)
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._updates: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stop = threading.Event()

    def set_telegram_account_id(self, account_id: int) -> None:
        if not isinstance(account_id, int) or isinstance(account_id, bool):
            raise ValueError("Telegram account ID must be an integer")
        self._telegram_account_id = account_id

    def enqueue_update(self, event: dict[str, Any]) -> None:
        """Queue only explicitly allowed TDLib new-message events."""
        if event.get("@type") != "updateNewMessage":
            return
        message = event.get("message")
        chat_id = message.get("chat_id") if isinstance(message, dict) else None
        if (
            not isinstance(chat_id, int)
            or isinstance(chat_id, bool)
            or chat_id not in self._allowed_chat_ids
        ):
            return
        self._updates.put_nowait(dict(event))

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        if self._telegram_account_id is None:
            raise RuntimeError("Telegram account ID is not initialized")
        while not self._stop.is_set():
            self.run_once(timeout=0.25)

    def run_once(self, *, timeout: float = 0.0) -> bool:
        """Process one queued TDLib update; primarily useful for tests."""
        if self._telegram_account_id is None:
            raise RuntimeError("Telegram account ID is not initialized")
        try:
            event = self._updates.get(timeout=timeout)
        except queue.Empty:
            return False
        try:
            payload = normalize_new_text_message(
                event,
                self._telegram_account_id,
            )
            if payload is not None:
                self._deliver(payload)
        except NormalizationError as exc:
            print(f"Skipped malformed TDLib text update: {exc}")
        finally:
            self._updates.task_done()
        return True

    def _deliver(self, payload: NormalizedMessage) -> None:
        identity = message_identity(payload)
        delay = self._initial_backoff
        while not self._stop.is_set():
            try:
                response = self._backend.post_message(payload)
            except BackendUnavailable:
                print(
                    f"Backend unavailable for message {identity}; "
                    f"retrying in {delay:g}s."
                )
            else:
                if response.accepted:
                    print(
                        f"Delivered message {identity} (HTTP {response.status_code})."
                    )
                    return
                if not response.transient:
                    print(
                        f"Backend rejected message {identity} permanently "
                        f"(HTTP {response.status_code})."
                    )
                    return
                print(
                    f"Backend temporarily rejected message {identity} "
                    f"(HTTP {response.status_code}); retrying in {delay:g}s."
                )
            if self._stop.wait(delay):
                return
            delay = min(delay * 2, self._max_backoff)


def main() -> int:
    try:
        tdlib_config = TdlibConfig.load()
        bridge_config = BridgeConfig.load()
        backend = BackendClient(
            bridge_config.backend_url,
            timeout=bridge_config.request_timeout,
        )
        health = backend.health()
        if health.status_code != 200:
            raise RuntimeError(
                f"Backend health check returned HTTP {health.status_code}."
            )

        bridge = TelegramBackendBridge(
            backend,
            allowed_chat_ids=bridge_config.allowed_chat_ids,
            initial_backoff=bridge_config.initial_backoff,
            max_backoff=bridge_config.max_backoff,
        )
        with TdJsonClient(tdlib_config.tdjson_path) as client:
            client.add_update_handler(bridge.enqueue_update)
            version = client.start()
            print(f"Loaded TDLib {version} from {tdlib_config.tdjson_path}")
            authorize(client, tdlib_config)
            me = client.request({"@type": "getMe"})
            bridge.set_telegram_account_id(me["id"])
            print(
                "Bridge ready for "
                f"{len(bridge_config.allowed_chat_ids)} allowed chat(s). "
                f"Messages will be sent to {backend.base_url}. "
                "Press Ctrl+C to stop."
            )
            bridge.run_forever()
        return 0
    except KeyboardInterrupt:
        print("\nStopping Telegram backend bridge...")
        return 130
    except (
        AuthorizationError,
        BackendUnavailable,
        ConfigurationError,
        FileNotFoundError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _chat_id_allowlist(name: str) -> frozenset[int]:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        raise ConfigurationError(
            f"{name} must contain at least one comma-separated Telegram chat ID"
        )
    chat_ids: set[int] = set()
    for raw_chat_id in raw_value.split(","):
        value = raw_chat_id.strip()
        if not value:
            raise ConfigurationError(f"{name} contains an empty chat ID")
        try:
            chat_ids.add(int(value))
        except ValueError as exc:
            raise ConfigurationError(
                f"{name} must contain only comma-separated integer chat IDs"
            ) from exc
    return frozenset(chat_ids)


def _positive_float(name: str, *, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
