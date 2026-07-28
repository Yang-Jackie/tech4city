"""Backend-managed, concurrent TDLib authorization sessions."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import shutil
import sqlite3
import sys
import threading
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import MessageCreate

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from telegram.config import TdlibConfig  # noqa: E402
from telegram.normalization import (  # noqa: E402
    NormalizationError,
    normalize_new_text_message,
)
from telegram.tdjson_client import (  # noqa: E402
    TdJsonClient,
    TdlibError,
    TdlibTimeout,
)


class TelegramLoginError(RuntimeError):
    """A safe error that can be returned to the browser."""


STATE_NAMES = {
    "authorizationStateWaitPhoneNumber": "wait_phone",
    "authorizationStateWaitCode": "wait_code",
    "authorizationStateWaitPassword": "wait_password",
    "authorizationStateReady": "ready",
    "authorizationStateLoggingOut": "logging_out",
    "authorizationStateClosing": "logging_out",
    "authorizationStateClosed": "logged_out",
    "authorizationStateWaitRegistration": "registration_required",
    "authorizationStateWaitEmailAddress": "unsupported",
    "authorizationStateWaitEmailCode": "unsupported",
    "authorizationStateWaitOtherDeviceConfirmation": "unsupported",
}

LIVE_INGESTION_QUEUE_SIZE = 1_000
LIVE_INGESTION_INITIAL_BACKOFF_SECONDS = 0.25
LIVE_INGESTION_MAX_BACKOFF_SECONDS = 30.0


@dataclass
class ManagedTelegramSession:
    session_id: str
    owner_token: str
    directory_name: str
    client: TdJsonClient
    created_at: datetime
    expires_at: datetime
    telegram_account_id: int | None = None
    saved_messages_chat_id: int | None = None
    display_name: str | None = None
    error: str | None = None
    ready_initialized: bool = False
    credential_attempts: int = 0
    update_handler: Any = None
    ingestion_queue: asyncio.Queue[dict[str, Any]] | None = None
    ingestion_task: asyncio.Task[None] | None = None
    ingestion_error: str | None = None
    action_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    initialization_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TelegramSessionRegistry:
    """Small local registry containing no phone numbers or credentials."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_sessions (
                    session_id TEXT PRIMARY KEY,
                    owner_hash TEXT NOT NULL,
                    directory_name TEXT NOT NULL UNIQUE,
                    telegram_account_id INTEGER,
                    display_name TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row[1]
                for row in self._connection.execute(
                    "PRAGMA table_info(telegram_sessions)"
                )
            }
            if "saved_messages_chat_id" not in columns:
                self._connection.execute(
                    "ALTER TABLE telegram_sessions "
                    "ADD COLUMN saved_messages_chat_id INTEGER"
                )

    def save(self, session: ManagedTelegramSession, status: str) -> None:
        now = datetime.now(UTC).isoformat()
        owner_hash = hashlib.sha256(session.owner_token.encode()).hexdigest()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO telegram_sessions
                    (session_id, owner_hash, directory_name, telegram_account_id,
                    display_name, status, created_at, updated_at,
                    saved_messages_chat_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    telegram_account_id=excluded.telegram_account_id,
                    display_name=excluded.display_name,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    saved_messages_chat_id=excluded.saved_messages_chat_id
                """,
                (
                    session.session_id,
                    owner_hash,
                    session.directory_name,
                    session.telegram_account_id,
                    session.display_name,
                    status,
                    session.created_at.isoformat(),
                    now,
                    session.saved_messages_chat_id,
                ),
            )

    def mark_logged_out(self, session_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE telegram_sessions SET status='logged_out', updated_at=? "
                "WHERE session_id=?",
                (datetime.now(UTC).isoformat(), session_id),
            )

    def get_active(self, session_id: str, owner_token: str) -> dict[str, Any] | None:
        owner_hash = hashlib.sha256(owner_token.encode()).hexdigest()
        with self._lock:
            row = self._connection.execute(
                """
                SELECT directory_name, telegram_account_id, display_name,
                       created_at, saved_messages_chat_id
                FROM telegram_sessions
                WHERE session_id=? AND owner_hash=? AND status!='logged_out'
                """,
                (session_id, owner_hash),
            ).fetchone()
        if row is None:
            return None
        return {
            "directory_name": row[0],
            "telegram_account_id": row[1],
            "display_name": row[2],
            "created_at": row[3],
            "saved_messages_chat_id": row[4],
        }

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class TelegramSessionManager:
    """Own one TDLib client per concurrent Telegram authorization."""

    def __init__(self, ingestion_service: Any, root: Path | None = None) -> None:
        self._ingestion_service = ingestion_service
        self._root = root or (REPO_ROOT / "telegram" / ".tdlib" / "web")
        self._root.mkdir(parents=True, exist_ok=True)
        self._registry = TelegramSessionRegistry(self._root / "sessions.sqlite3")
        self._sessions: dict[str, ManagedTelegramSession] = {}
        self._lock = asyncio.Lock()
        self._loop = asyncio.get_running_loop()
        self._config: TdlibConfig | None = None

    def _load_config(self) -> TdlibConfig:
        if self._config is None:
            self._config = TdlibConfig.load()
        return self._config

    async def create(self, owner_token: str) -> dict[str, Any]:
        config = self._load_config()
        session_id = secrets.token_urlsafe(24)
        directory_name = secrets.token_hex(16)
        database_dir = self._root / directory_name / "database"
        files_dir = self._root / directory_name / "files"
        database_dir.mkdir(parents=True)
        files_dir.mkdir(parents=True)
        try:
            client = await asyncio.to_thread(
                self._start_client,
                config,
                session_id,
                database_dir,
                files_dir,
            )
        except Exception:
            shutil.rmtree(database_dir.parent, ignore_errors=True)
            raise
        now = datetime.now(UTC)
        session = ManagedTelegramSession(
            session_id=session_id,
            owner_token=owner_token,
            directory_name=directory_name,
            client=client,
            created_at=now,
            expires_at=now + timedelta(minutes=15),
        )
        async with self._lock:
            self._sessions[session_id] = session
        self._registry.save(session, self._status_name(session))
        return self.describe(session)

    async def submit(
        self, session_id: str, owner_token: str, kind: str, value: str
    ) -> dict[str, Any]:
        session = await self._owned(session_id, owner_token)
        expected, request_type, field_name = {
            "phone": ("wait_phone", "setAuthenticationPhoneNumber", "phone_number"),
            "code": ("wait_code", "checkAuthenticationCode", "code"),
            "password": ("wait_password", "checkAuthenticationPassword", "password"),
        }[kind]
        if self._status_name(session) != expected:
            raise TelegramLoginError(f"Telegram is not waiting for {kind}.")
        if not value.strip():
            raise TelegramLoginError(f"{kind.capitalize()} must not be blank.")
        async with session.action_lock:
            session.credential_attempts += 1
            if session.credential_attempts > 10:
                raise TelegramLoginError(
                    "Too many authentication attempts; log out and start again."
                )
            old_version = session.client.authorization_version
            try:
                await asyncio.to_thread(
                    session.client.request,
                    {"@type": request_type, field_name: value.strip()},
                    20,
                )
                with suppress(TdlibTimeout):
                    await asyncio.to_thread(
                        session.client.wait_for_authorization_change,
                        old_version,
                        20,
                    )
            except TdlibError as exc:
                session.error = self._safe_tdlib_error(exc)
                raise TelegramLoginError(session.error) from exc
            session.error = None
            if self._status_name(session) == "ready":
                await self._initialize_ready(session)
            self._registry.save(session, self._status_name(session))
            return self.describe(session)

    async def status(self, session_id: str, owner_token: str) -> dict[str, Any]:
        session = await self._owned(session_id, owner_token)
        if (
            datetime.now(UTC) > session.expires_at
            and self._status_name(session) != "ready"
        ):
            await self.logout(session_id, owner_token)
            raise TelegramLoginError("Login session expired.")
        if self._status_name(session) == "ready" and not session.ready_initialized:
            await self._initialize_ready(session)
        return self.describe(session)

    async def account_id(self, session_id: str, owner_token: str) -> int:
        session = await self._owned(session_id, owner_token)
        if self._status_name(session) != "ready":
            raise TelegramLoginError("Telegram login is not ready.")
        if not session.ready_initialized:
            await self._initialize_ready(session)
        if session.telegram_account_id is None:
            raise TelegramLoginError("Telegram account identity is unavailable.")
        return session.telegram_account_id

    async def saved_chat_id(self, session_id: str, owner_token: str) -> int:
        session = await self._owned(session_id, owner_token)
        await self.account_id(session_id, owner_token)
        if session.saved_messages_chat_id is None:
            raise TelegramLoginError("Saved Messages identity is unavailable.")
        return session.saved_messages_chat_id

    async def logout(self, session_id: str, owner_token: str) -> dict[str, Any]:
        session = await self._owned(session_id, owner_token)
        async with session.action_lock, session.initialization_lock:
            await self._stop_live_ingestion(session)
            with suppress(TdlibError, TdlibTimeout):
                await asyncio.to_thread(
                    session.client.request, {"@type": "logOut"}, 20
                )
            await asyncio.to_thread(session.client.close)
            async with self._lock:
                self._sessions.pop(session_id, None)
            self._registry.mark_logged_out(session_id)
            shutil.rmtree(self._root / session.directory_name, ignore_errors=True)
        return {"session_id": session_id, "status": "logged_out"}

    async def close(self) -> None:
        sessions = list(self._sessions.values())
        for session in sessions:
            await self._stop_live_ingestion(session)
            await asyncio.to_thread(session.client.close)
        self._sessions.clear()
        self._registry.close()

    def describe(self, session: ManagedTelegramSession) -> dict[str, Any]:
        state = session.client.authorization_state or {}
        status = self._status_name(session)
        result: dict[str, Any] = {
            "session_id": session.session_id,
            "status": status,
            "telegram_account_id": session.telegram_account_id,
            "saved_messages_chat_id": session.saved_messages_chat_id,
            "display_name": session.display_name,
            "error": session.error or session.ingestion_error,
        }
        if status == "wait_password":
            result["password_hint"] = state.get("password_hint") or None
        code_info = state.get("code_info") or {}
        if status == "wait_code":
            result["code_type"] = (code_info.get("type") or {}).get("@type")
        return result

    async def _owned(self, session_id: str, owner_token: str) -> ManagedTelegramSession:
        session = self._sessions.get(session_id)
        if session is not None and secrets.compare_digest(
            session.owner_token, owner_token
        ):
            return session
        saved = self._registry.get_active(session_id, owner_token)
        if saved is None:
            raise KeyError(session_id)
        config = self._load_config()
        session_root = self._root / saved["directory_name"]
        client = await asyncio.to_thread(
            self._start_client,
            config,
            session_id,
            session_root / "database",
            session_root / "files",
        )
        created_at = datetime.fromisoformat(saved["created_at"])
        session = ManagedTelegramSession(
            session_id=session_id,
            owner_token=owner_token,
            directory_name=saved["directory_name"],
            client=client,
            created_at=created_at,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
            telegram_account_id=saved["telegram_account_id"],
            display_name=saved["display_name"],
            saved_messages_chat_id=saved["saved_messages_chat_id"],
        )
        async with self._lock:
            existing = self._sessions.setdefault(session_id, session)
        if existing is not session:
            await asyncio.to_thread(client.close)
            session = existing
        return session

    @staticmethod
    def _start_client(
        config: TdlibConfig,
        session_id: str,
        database_dir: Path,
        files_dir: Path,
    ) -> TdJsonClient:
        database_dir.mkdir(parents=True, exist_ok=True)
        files_dir.mkdir(parents=True, exist_ok=True)
        key = hmac.new(
            config.database_encryption_key.encode(),
            session_id.encode(),
            hashlib.sha256,
        ).digest()
        client = TdJsonClient(config.tdjson_path)
        client.start()
        version = -1
        while True:
            state, version = client.wait_for_authorization_change(version, 30)
            if state.get("@type") != "authorizationStateWaitTdlibParameters":
                return client
            client.request(
                {
                    "@type": "setTdlibParameters",
                    "use_test_dc": False,
                    "database_directory": str(database_dir),
                    "files_directory": str(files_dir),
                    "database_encryption_key": base64.b64encode(key).decode(),
                    "use_file_database": True,
                    "use_chat_info_database": True,
                    "use_message_database": True,
                    "use_secret_chats": False,
                    "api_id": config.api_id,
                    "api_hash": config.api_hash,
                    "system_language_code": "en",
                    "device_model": "Tech4City web",
                    "system_version": "Windows",
                    "application_version": "0.5.0",
                }
            )

    def _status_name(self, session: ManagedTelegramSession) -> str:
        state_type = (session.client.authorization_state or {}).get("@type")
        return STATE_NAMES.get(state_type, "starting")

    async def _initialize_ready(self, session: ManagedTelegramSession) -> None:
        async with session.initialization_lock:
            if session.ready_initialized:
                return
            me = await asyncio.to_thread(
                session.client.request, {"@type": "getMe"}, 20
            )
            account_id = int(me["id"])
            session.telegram_account_id = account_id
            session.display_name = (
                " ".join(
                    part
                    for part in (me.get("first_name"), me.get("last_name"))
                    if part
                )
                or me.get("username")
                or f"Telegram {account_id}"
            )

            try:
                saved_chat = await asyncio.to_thread(
                    session.client.request,
                    {
                        "@type": "createPrivateChat",
                        "user_id": account_id,
                        "force": False,
                    },
                    20,
                )
            except (TdlibError, TdlibTimeout) as exc:
                session.error = "Could not initialize Saved Messages."
                raise TelegramLoginError(session.error) from exc
            session.saved_messages_chat_id = int(saved_chat["id"])
            session.ingestion_queue = asyncio.Queue(
                maxsize=LIVE_INGESTION_QUEUE_SIZE
            )

            def on_update(event: dict[str, Any]) -> None:
                if event.get("@type") != "updateNewMessage":
                    return
                self._loop.call_soon_threadsafe(
                    self._enqueue_live_update, session, dict(event)
                )

            session.update_handler = on_update
            session.client.add_update_handler(on_update)
            try:
                try:
                    history = await asyncio.to_thread(
                        session.client.request,
                        {
                            "@type": "getChatHistory",
                            "chat_id": session.saved_messages_chat_id,
                            "from_message_id": 0,
                            "offset": 0,
                            "limit": 100,
                            "only_local": False,
                        },
                        30,
                    )
                except (TdlibError, TdlibTimeout):
                    history = {"messages": []}
                for message in reversed(history.get("messages") or []):
                    await self._ingest_event(
                        session, {"@type": "updateNewMessage", "message": message}
                    )
            except Exception:
                await self._stop_live_ingestion(session)
                raise

            session.ready_initialized = True
            session.expires_at = datetime.max.replace(tzinfo=UTC)
            session.ingestion_task = asyncio.create_task(
                self._drain_live_ingestion(session),
                name=f"telegram-ingestion-{session.session_id}",
            )
            self._registry.save(session, "ready")

    def _enqueue_live_update(
        self, session: ManagedTelegramSession, event: dict[str, Any]
    ) -> None:
        queue = session.ingestion_queue
        if queue is None:
            return
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            session.ingestion_error = (
                "Telegram message ingestion is overloaded; reconnect to resynchronize."
            )
            print(
                "Telegram live-ingestion queue is full for session "
                f"{session.session_id}; reconnect is required."
            )

    async def _drain_live_ingestion(self, session: ManagedTelegramSession) -> None:
        queue = session.ingestion_queue
        if queue is None:
            return
        while True:
            event = await queue.get()
            delay = LIVE_INGESTION_INITIAL_BACKOFF_SECONDS
            try:
                while True:
                    try:
                        await self._ingest_event(session, event)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        session.ingestion_error = (
                            "Telegram message ingestion is temporarily unavailable."
                        )
                        print(
                            "Telegram message ingestion failed for session "
                            f"{session.session_id} ({type(exc).__name__}); "
                            f"retrying in {delay:g}s."
                        )
                        await asyncio.sleep(delay)
                        delay = min(
                            delay * 2,
                            LIVE_INGESTION_MAX_BACKOFF_SECONDS,
                        )
                    else:
                        session.ingestion_error = None
                        break
            finally:
                queue.task_done()

    async def _stop_live_ingestion(self, session: ManagedTelegramSession) -> None:
        if session.update_handler is not None:
            session.client.remove_update_handler(session.update_handler)
            session.update_handler = None
        task = session.ingestion_task
        session.ingestion_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        session.ingestion_queue = None

    async def _ingest_event(
        self, session: ManagedTelegramSession, event: dict[str, Any]
    ) -> None:
        if session.telegram_account_id is None:
            return
        try:
            payload = normalize_new_text_message(event, session.telegram_account_id)
        except NormalizationError:
            return
        if payload is None or payload["chat_id"] != session.saved_messages_chat_id:
            return
        await self._ingestion_service.process(MessageCreate(**payload))

    @staticmethod
    def _safe_tdlib_error(exc: TdlibError) -> str:
        safe = str(exc.message).replace("\n", " ").strip()
        return safe[:240] or "Telegram rejected the request."
