from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.analyzer import analyze_message
from app.main import create_app
from app.models import MessageCreate
from app.repository import InMemoryRepository
from app.telegram_login import (
    ManagedTelegramSession,
    TelegramLoginError,
    TelegramSessionManager,
)
from fastapi.testclient import TestClient


class StubTelegramManager:
    def __init__(self, _ingestion_service) -> None:
        self.owner = ""
        self.state = "wait_phone"
        self.values: list[tuple[str, str]] = []

    async def create(self, owner: str):
        self.owner = owner
        return self._description()

    async def status(self, session_id: str, owner: str):
        self._check(session_id, owner)
        return self._description()

    async def submit(self, session_id: str, owner: str, kind: str, value: str):
        self._check(session_id, owner)
        expected = {
            "wait_phone": "phone",
            "wait_code": "code",
            "wait_password": "password",
        }[self.state]
        if kind != expected:
            raise TelegramLoginError("wrong state")
        self.values.append((kind, value))
        self.state = {
            "phone": "wait_code",
            "code": "wait_password",
            "password": "ready",
        }[kind]
        return self._description()

    async def logout(self, session_id: str, owner: str):
        self._check(session_id, owner)
        self.state = "logged_out"
        return {"session_id": session_id, "status": self.state}

    async def account_id(self, session_id: str, owner: str):
        self._check(session_id, owner)
        if self.state != "ready":
            raise TelegramLoginError("not ready")
        return 123

    async def saved_chat_id(self, session_id: str, owner: str):
        return await self.account_id(session_id, owner)

    async def close(self) -> None:
        pass

    def _check(self, session_id: str, owner: str) -> None:
        if session_id != "login-1" or owner != self.owner:
            raise KeyError(session_id)

    def _description(self):
        return {
            "session_id": "login-1",
            "status": self.state,
            "telegram_account_id": 123 if self.state == "ready" else None,
            "saved_messages_chat_id": 123 if self.state == "ready" else None,
            "display_name": "Test User" if self.state == "ready" else None,
            "error": None,
            "password_hint": "hint" if self.state == "wait_password" else None,
            "code_type": "authenticationCodeTypeTelegramMessage"
            if self.state == "wait_code"
            else None,
        }


def make_app():
    return create_app(
        analyzer=analyze_message,
        repository=InMemoryRepository(),
        worker_enabled=False,
        telegram_manager_factory=StubTelegramManager,
    )


def test_phone_code_password_flow_sets_private_owner_cookie() -> None:
    with TestClient(make_app()) as client:
        created = client.post("/telegram/login")
        session_id = created.json()["session_id"]
        code = client.post(
            f"/telegram/login/{session_id}/phone", json={"value": "+84123456789"}
        )
        password = client.post(
            f"/telegram/login/{session_id}/code", json={"value": "12345"}
        )
        ready = client.post(
            f"/telegram/login/{session_id}/password",
            json={"value": "not-retained"},
        )

    assert created.status_code == 201
    assert "HttpOnly" in created.headers["set-cookie"]
    assert "SameSite=strict" in created.headers["set-cookie"]
    assert created.headers["cache-control"] == "no-store"
    assert code.json()["status"] == "wait_code"
    assert password.json()["status"] == "wait_password"
    assert ready.json()["status"] == "ready"
    assert ready.json()["telegram_account_id"] == 123


def test_login_session_requires_ownership_cookie() -> None:
    with TestClient(make_app()) as client:
        response = client.get("/telegram/login/login-1")

    assert response.status_code == 401


def test_logout_calls_manager_and_returns_terminal_state() -> None:
    with TestClient(make_app()) as client:
        client.post("/telegram/login")
        response = client.post("/telegram/login/login-1/logout")

    assert response.status_code == 200
    assert response.json() == {"session_id": "login-1", "status": "logged_out"}


def test_connected_chat_routes_are_cookie_owned() -> None:
    with TestClient(make_app()) as owner:
        for chat_id, message_id in ((123, 1), (999, 2)):
            created = owner.post(
                "/messages",
                json={
                    "telegram_account_id": 123,
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "sender_id": 123,
                    "text": f"Chat {chat_id}",
                    "sent_at": "2026-07-28T10:00:00Z",
                },
            )
            assert created.status_code == 202
        owner.post("/telegram/login")
        owner.post("/telegram/login/login-1/phone", json={"value": "+84123"})
        owner.post("/telegram/login/login-1/code", json={"value": "12345"})
        owner.post("/telegram/login/login-1/password", json={"value": "password"})
        owned = owner.get("/telegram/login/login-1/chats")

        with TestClient(make_app()) as stranger:
            denied = stranger.get("/telegram/login/login-1/chats")

    assert owned.status_code == 200
    assert [chat["chat_id"] for chat in owned.json()] == [123]
    assert denied.status_code == 401


def test_ready_initialization_materializes_saved_messages_before_history(
    tmp_path,
) -> None:
    calls: list[dict] = []

    class FakeIngestion:
        async def process(self, _message):
            raise AssertionError("empty history should not ingest")

    class FakeClient:
        authorization_state = {"@type": "authorizationStateReady"}
        authorization_version = 1
        handler = None

        def request(self, query, _timeout=30):
            calls.append(query)
            if query["@type"] == "getMe":
                return {"id": 123, "first_name": "Test", "last_name": "User"}
            if query["@type"] == "createPrivateChat":
                return {"id": 999}
            if query["@type"] == "getChatHistory":
                assert query["chat_id"] == 999
                return {"messages": []}
            raise AssertionError(query)

        def add_update_handler(self, handler):
            self.handler = handler

        def remove_update_handler(self, handler):
            assert self.handler is handler
            self.handler = None

    async def run() -> None:
        manager = TelegramSessionManager(FakeIngestion(), root=tmp_path)
        now = datetime.now(UTC)
        session = ManagedTelegramSession(
            session_id="session",
            owner_token="owner",
            directory_name="directory",
            client=FakeClient(),
            created_at=now,
            expires_at=now + timedelta(minutes=15),
        )
        await manager._initialize_ready(session)
        await manager._stop_live_ingestion(session)
        manager._registry.close()
        assert session.saved_messages_chat_id == 999

    asyncio.run(run())
    assert [call["@type"] for call in calls] == [
        "getMe",
        "createPrivateChat",
        "getChatHistory",
    ]


def test_live_ingestion_is_ordered_and_retries_transient_failures(tmp_path) -> None:
    attempts = 0
    ingested: list[MessageCreate] = []
    completed: asyncio.Event | None = None

    class FakeIngestion:
        async def process(self, message):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary storage failure")
            ingested.append(message)
            assert completed is not None
            completed.set()

    class FakeClient:
        authorization_state = {"@type": "authorizationStateReady"}
        authorization_version = 1
        handler = None

        def request(self, query, _timeout=30):
            if query["@type"] == "getMe":
                return {"id": 123, "first_name": "Test", "last_name": "User"}
            if query["@type"] == "createPrivateChat":
                return {"id": 999}
            if query["@type"] == "getChatHistory":
                return {"messages": []}
            raise AssertionError(query)

        def add_update_handler(self, handler):
            self.handler = handler

        def remove_update_handler(self, handler):
            assert self.handler is handler
            self.handler = None

    async def run() -> None:
        nonlocal completed
        completed = asyncio.Event()
        manager = TelegramSessionManager(FakeIngestion(), root=tmp_path)
        now = datetime.now(UTC)
        client = FakeClient()
        session = ManagedTelegramSession(
            session_id="session",
            owner_token="owner",
            directory_name="directory",
            client=client,
            created_at=now,
            expires_at=now + timedelta(minutes=15),
        )
        await manager._initialize_ready(session)
        assert client.handler is not None
        client.handler(
            {
                "@type": "updateNewMessage",
                "message": {
                    "id": 10,
                    "chat_id": 999,
                    "date": 1_753_697_600,
                    "sender_id": {
                        "@type": "messageSenderUser",
                        "user_id": 123,
                    },
                    "content": {
                        "@type": "messageText",
                        "text": {"text": "Retry me"},
                    },
                },
            }
        )
        await asyncio.wait_for(completed.wait(), timeout=2)
        await manager._stop_live_ingestion(session)
        manager._registry.close()

    asyncio.run(run())
    assert attempts == 2
    assert [message.text for message in ingested] == ["Retry me"]
