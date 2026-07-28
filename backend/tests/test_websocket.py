from __future__ import annotations

import asyncio

from app.analyzer import analyze_message
from app.events import LocalEventBroker
from app.main import create_app
from app.repository import InMemoryRepository
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


class ReadyTelegramManager:
    def __init__(self, _ingestion_service) -> None:
        self.owner = ""

    async def create(self, owner: str):
        self.owner = owner
        return self._status()

    async def status(self, session_id: str, owner: str):
        if session_id != "session-1" or owner != self.owner:
            raise KeyError(session_id)
        return self._status()

    async def close(self) -> None:
        pass

    @staticmethod
    def _status():
        return {
            "session_id": "session-1",
            "status": "ready",
            "telegram_account_id": 100,
            "saved_messages_chat_id": 100,
            "display_name": "Test User",
            "error": None,
        }


def make_app(**options):
    options.setdefault("analyzer", analyze_message)
    options.setdefault("repository", InMemoryRepository())
    options.setdefault("worker_enabled", False)
    return create_app(**options)


def message_payload() -> dict[str, object]:
    return {
        "telegram_account_id": 100,
        "chat_id": 200,
        "message_id": 1,
        "sender_id": 100,
        "text": "WebSocket test",
        "sent_at": "2026-07-26T10:00:00Z",
    }


def test_demo_subscription_receives_message_chat_and_analysis_events() -> None:
    with (
        TestClient(make_app()) as client,
        client.websocket_connect("/ws") as websocket,
    ):
        assert websocket.receive_json()["type"] == "connection.ready"
        websocket.send_json({"type": "subscribe", "account_id": 100})
        subscribed = websocket.receive_json()
        assert subscribed["type"] == "subscription.ready"

        response = client.post("/messages", json=message_payload())
        message = websocket.receive_json()
        chat = websocket.receive_json()

        assert response.status_code == 202
        assert message["type"] == "message.created"
        assert message["message_id"] == 1
        assert chat["type"] == "chat.updated"
        assert chat["chat_id"] == 200
        assert chat["sequence"] > message["sequence"]

        client.post("/internal/worker/run-once")
        analysis = websocket.receive_json()
        assert analysis["type"] == "analysis.updated"
        assert analysis["data"]["status"] == "completed"


def test_telegram_subscription_requires_owning_cookie() -> None:
    app = make_app(telegram_manager_factory=ReadyTelegramManager)
    with TestClient(app) as owner:
        owner.post("/telegram/login")
        with owner.websocket_connect("/ws") as websocket:
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "subscribe",
                    "telegram_session_id": "session-1",
                }
            )
            subscribed = websocket.receive_json()
            assert subscribed["type"] == "subscription.ready"
            assert subscribed["account_id"] == 100

    with (
        TestClient(make_app(telegram_manager_factory=ReadyTelegramManager)) as stranger,
        stranger.websocket_connect("/ws") as websocket,
    ):
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "subscribe",
                "telegram_session_id": "session-1",
            }
        )
        try:
            websocket.receive_json()
        except WebSocketDisconnect as exc:
            assert exc.code == 1008
        else:
            raise AssertionError("unowned Telegram subscription was accepted")


def test_websocket_rejects_cross_origin_handshake() -> None:
    with TestClient(make_app()) as client:
        try:
            with client.websocket_connect(
                "/ws", headers={"origin": "http://attacker.example"}
            ):
                raise AssertionError("cross-origin WebSocket was accepted")
        except WebSocketDisconnect as exc:
            assert exc.code == 1008


def test_websocket_rejects_non_object_command_without_crashing() -> None:
    with (
        TestClient(make_app()) as client,
        client.websocket_connect("/ws") as websocket,
    ):
        websocket.receive_json()
        websocket.send_json(["subscribe", 100])
        error = websocket.receive_json()
        assert error["type"] == "subscription.error"
        assert error["data"]["detail"] == "Command must be an object"

        websocket.send_json({"type": "subscribe", "account_id": 100})
        assert websocket.receive_json()["type"] == "subscription.ready"


def test_chat_subscription_filters_other_chats_but_keeps_account_events() -> None:
    async def run() -> None:
        broker = LocalEventBroker()
        connection = await broker.connect()
        await broker.subscribe(
            connection,
            account_id=100,
            chat_id=200,
            telegram_session_id=None,
        )

        await broker.publish("message.created", account_id=100, chat_id=201)
        assert connection.queue.empty()

        await broker.publish("account.updated", account_id=100)
        assert (await connection.queue.get())["type"] == "account.updated"

        await broker.publish("message.created", account_id=100, chat_id=200)
        matching = await connection.queue.get()
        assert matching["type"] == "message.created"
        assert matching["chat_id"] == 200

    asyncio.run(run())
