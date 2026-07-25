"""Threaded ctypes wrapper around TDLib's official JSON interface."""

from __future__ import annotations

import ctypes
import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


UpdateHandler = Callable[[dict[str, Any]], None]


class TdlibError(RuntimeError):
    """An error returned by TDLib."""

    def __init__(self, response: dict[str, Any]):
        self.code = response.get("code", 0)
        self.message = response.get("message", "Unknown TDLib error")
        super().__init__(f"TDLib error {self.code}: {self.message}")


class TdlibTimeout(TimeoutError):
    """A request or state transition exceeded its timeout."""


@dataclass
class _PendingRequest:
    ready: threading.Event
    response: dict[str, Any] | None = None


class TdJsonClient:
    """Owns one TDLib client and continuously drains its ordered event stream."""

    _clients_lock = threading.Lock()
    _clients: dict[int, "TdJsonClient"] = {}
    _pump_lock = threading.Lock()
    _pump_thread: threading.Thread | None = None
    _pump_stop: threading.Event | None = None
    _pump_receive: Any = None

    def __init__(self, library_path: Path):
        self.library_path = library_path.resolve()
        self._dll_directory_handles: list[Any] = []
        self._library = self._load_library(self.library_path)
        self._configure_functions()

        self.client_id = self._td_create_client_id()
        with self._clients_lock:
            self._clients[self.client_id] = self
        self._next_request_id = 1
        self._request_lock = threading.Lock()
        self._pending: dict[int, _PendingRequest] = {}
        self._pending_lock = threading.Lock()
        self._stop = threading.Event()

        self._state_condition = threading.Condition()
        self.authorization_state: dict[str, Any] | None = None
        self.authorization_version = 0

        self._cache_lock = threading.Lock()
        self.chats: dict[int, dict[str, Any]] = {}
        self.users: dict[int, dict[str, Any]] = {}

        self._send_condition = threading.Condition()
        self._send_results: dict[int, dict[str, Any]] = {}

        self._update_handlers_lock = threading.Lock()
        self._update_handlers: list[UpdateHandler] = []

        self._ensure_receive_pump()

    def _load_library(self, path: Path) -> ctypes.CDLL:
        if not path.is_file():
            raise FileNotFoundError(f"TDLib library does not exist: {path}")
        if os.name == "nt" and hasattr(os, "add_dll_directory"):
            search_directories = [path.parent]
            dependency_dir = os.getenv("TDJSON_DEPENDENCY_PATH", "").strip()
            if dependency_dir:
                search_directories.append(Path(dependency_dir).resolve())
            for directory in search_directories:
                if directory.is_dir():
                    self._dll_directory_handles.append(os.add_dll_directory(directory))
        try:
            return ctypes.CDLL(str(path))
        except OSError as exc:
            raise RuntimeError(
                f"Could not load {path}. Verify that it is 64-bit and that its "
                f"dependent DLLs are beside it. Windows reported: {exc}"
            ) from exc

    def _configure_functions(self) -> None:
        self._td_create_client_id = self._library.td_create_client_id
        self._td_create_client_id.restype = ctypes.c_int
        self._td_create_client_id.argtypes = []

        self._td_send = self._library.td_send
        self._td_send.restype = None
        self._td_send.argtypes = [ctypes.c_int, ctypes.c_char_p]

        self._td_receive = self._library.td_receive
        self._td_receive.restype = ctypes.c_char_p
        self._td_receive.argtypes = [ctypes.c_double]

        self._td_execute = self._library.td_execute
        self._td_execute.restype = ctypes.c_char_p
        self._td_execute.argtypes = [ctypes.c_char_p]

        callback_type = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p)

        @callback_type
        def log_callback(verbosity: int, message: bytes) -> None:
            if verbosity <= 0:
                decoded = message.decode("utf-8", errors="replace")
                print(f"\nTDLib fatal log message: {decoded}")

        self._log_callback = log_callback  # Keep the ctypes callback alive.
        set_log_callback = self._library.td_set_log_message_callback
        set_log_callback.restype = None
        set_log_callback.argtypes = [ctypes.c_int, callback_type]
        set_log_callback(2, self._log_callback)
        self.execute({"@type": "setLogVerbosityLevel", "new_verbosity_level": 1})

    def execute(self, query: dict[str, Any]) -> dict[str, Any] | None:
        encoded = json.dumps(query, ensure_ascii=False).encode("utf-8")
        result = self._td_execute(encoded)
        return json.loads(result.decode("utf-8")) if result else None

    def send(self, query: dict[str, Any]) -> tuple[int, _PendingRequest]:
        with self._request_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
        payload = dict(query)
        payload["@extra"] = request_id
        pending = _PendingRequest(ready=threading.Event())
        with self._pending_lock:
            self._pending[request_id] = pending
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._td_send(self.client_id, encoded)
        return request_id, pending

    def request(
        self, query: dict[str, Any], timeout: float = 30.0
    ) -> dict[str, Any]:
        request_id, pending = self.send(query)
        if not pending.ready.wait(timeout):
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise TdlibTimeout(
                f"Timed out after {timeout:g}s waiting for {query.get('@type', 'request')}."
            )
        response = pending.response or {}
        if response.get("@type") == "error":
            raise TdlibError(response)
        return response

    def start(self) -> str:
        response = self.request({"@type": "getOption", "name": "version"})
        return str(response.get("value", "unknown"))

    def wait_for_authorization_change(
        self, after_version: int = -1, timeout: float = 60.0
    ) -> tuple[dict[str, Any], int]:
        deadline = time.monotonic() + timeout
        with self._state_condition:
            while (
                self.authorization_state is None
                or self.authorization_version <= after_version
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TdlibTimeout("Timed out waiting for an authorization state.")
                self._state_condition.wait(remaining)
            return dict(self.authorization_state), self.authorization_version

    def wait_for_send(self, old_message_id: int, timeout: float = 20.0) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        with self._send_condition:
            while old_message_id not in self._send_results:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._send_condition.wait(remaining)
            return self._send_results.pop(old_message_id)

    def snapshot_users(self) -> dict[int, dict[str, Any]]:
        with self._cache_lock:
            return {key: dict(value) for key, value in self.users.items()}

    def snapshot_chats(self) -> dict[int, dict[str, Any]]:
        with self._cache_lock:
            return {key: dict(value) for key, value in self.chats.items()}

    def add_update_handler(self, handler: UpdateHandler) -> None:
        """Subscribe a fast, non-blocking handler to unsolicited TDLib updates."""
        with self._update_handlers_lock:
            if handler not in self._update_handlers:
                self._update_handlers.append(handler)

    def remove_update_handler(self, handler: UpdateHandler) -> None:
        """Remove a previously registered update handler if it is present."""
        with self._update_handlers_lock:
            if handler in self._update_handlers:
                self._update_handlers.remove(handler)

    def _ensure_receive_pump(self) -> None:
        """Start the one process-wide thread allowed to call ``td_receive``."""
        with self._pump_lock:
            if self._pump_thread is not None and self._pump_thread.is_alive():
                return
            type(self)._pump_stop = threading.Event()
            type(self)._pump_receive = self._td_receive
            type(self)._pump_thread = threading.Thread(
                target=type(self)._receive_loop,
                name="tdlib-receiver",
                daemon=True,
            )
            self._pump_thread.start()

    @classmethod
    def _receive_loop(cls) -> None:
        stop = cls._pump_stop
        receive = cls._pump_receive
        if stop is None or receive is None:
            return
        while not stop.is_set():
            raw = receive(0.25)
            if not raw:
                continue
            try:
                event = json.loads(raw.decode("utf-8"))
                event_client_id = event.get("@client_id")
                with cls._clients_lock:
                    target = cls._clients.get(event_client_id)
                if target is not None:
                    target._dispatch(event)
            except Exception as exc:  # Keep receiving; surface diagnostics without secrets.
                print(f"\nFailed to process a TDLib event: {exc}")

    def _dispatch(self, event: dict[str, Any]) -> None:
        request_id = event.get("@extra")
        if isinstance(request_id, int):
            with self._pending_lock:
                pending = self._pending.pop(request_id, None)
            if pending is not None:
                pending.response = event
                pending.ready.set()

        event_type = event.get("@type")
        if event_type == "updateAuthorizationState":
            with self._state_condition:
                self.authorization_state = event["authorization_state"]
                self.authorization_version += 1
                self._state_condition.notify_all()
        elif event_type == "updateNewChat":
            chat = event["chat"]
            with self._cache_lock:
                self.chats[chat["id"]] = chat
        elif event_type == "updateChatTitle":
            with self._cache_lock:
                chat = self.chats.get(event["chat_id"])
                if chat is not None:
                    chat["title"] = event["title"]
        elif event_type == "updateChatLastMessage":
            with self._cache_lock:
                chat = self.chats.get(event["chat_id"])
                if chat is not None:
                    chat["last_message"] = event.get("last_message")
                    chat["positions"] = event.get("positions", chat.get("positions", []))
        elif event_type == "updateChatPosition":
            self._update_chat_position(event)
        elif event_type == "updateUser":
            user = event["user"]
            with self._cache_lock:
                self.users[user["id"]] = user
        elif event_type in {"updateMessageSendSucceeded", "updateMessageSendFailed"}:
            with self._send_condition:
                self._send_results[event["old_message_id"]] = event
                self._send_condition.notify_all()

        if isinstance(event_type, str) and event_type.startswith("update"):
            with self._update_handlers_lock:
                handlers = tuple(self._update_handlers)
            for handler in handlers:
                try:
                    handler(dict(event))
                except Exception:
                    # A consumer must never be able to stop TDLib's receive loop.
                    print("\nTDLib update handler failed.")

    def _update_chat_position(self, event: dict[str, Any]) -> None:
        with self._cache_lock:
            chat = self.chats.get(event["chat_id"])
            if chat is None:
                return
            position = event["position"]
            list_type = (position.get("list") or {}).get("@type")
            positions = [
                existing
                for existing in chat.get("positions", [])
                if (existing.get("list") or {}).get("@type") != list_type
            ]
            if position.get("order", "0") != "0" and position.get("order", 0) != 0:
                positions.append(position)
            chat["positions"] = positions

    def close(self, timeout: float = 10.0) -> None:
        if self._stop.is_set():
            return
        try:
            state_type = (self.authorization_state or {}).get("@type")
            if state_type not in {"authorizationStateClosed", "authorizationStateClosing"}:
                try:
                    self.request({"@type": "close"}, timeout=timeout)
                except (TdlibError, TdlibTimeout):
                    pass
            deadline = time.monotonic() + timeout
            with self._state_condition:
                while (
                    (self.authorization_state or {}).get("@type")
                    != "authorizationStateClosed"
                    and time.monotonic() < deadline
                ):
                    self._state_condition.wait(deadline - time.monotonic())
        finally:
            self._stop.set()
            with self._clients_lock:
                self._clients.pop(self.client_id, None)
            self._release_receive_pump_if_unused()

    @classmethod
    def _release_receive_pump_if_unused(cls) -> None:
        with cls._clients_lock:
            has_clients = bool(cls._clients)
        if has_clients:
            return
        with cls._pump_lock:
            thread = cls._pump_thread
            stop = cls._pump_stop
            if stop is not None:
                stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        with cls._pump_lock:
            if cls._pump_thread is thread:
                cls._pump_thread = None
                cls._pump_stop = None
                cls._pump_receive = None

    def __enter__(self) -> "TdJsonClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
