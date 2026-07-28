"""Single-process WebSocket event broker for the local application."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EventSubscription:
    account_id: int | None = None
    chat_id: int | None = None
    telegram_session_id: str | None = None


@dataclass(eq=False)
class EventConnection:
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=100)
    )
    subscription: EventSubscription = field(default_factory=EventSubscription)


class LocalEventBroker:
    """Fan out sequenced events within one Uvicorn process."""

    def __init__(self) -> None:
        self._connections: set[EventConnection] = set()
        self._sequence = 0
        self._lock = asyncio.Lock()

    async def connect(self) -> EventConnection:
        connection = EventConnection()
        async with self._lock:
            self._connections.add(connection)
        return connection

    async def disconnect(self, connection: EventConnection) -> None:
        async with self._lock:
            self._connections.discard(connection)

    async def subscribe(
        self,
        connection: EventConnection,
        *,
        account_id: int | None,
        chat_id: int | None,
        telegram_session_id: str | None,
    ) -> None:
        connection.subscription = EventSubscription(
            account_id=account_id,
            chat_id=chat_id,
            telegram_session_id=telegram_session_id,
        )

    async def publish(
        self,
        event_type: str,
        *,
        account_id: int | None = None,
        chat_id: int | None = None,
        message_id: int | None = None,
        telegram_session_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        async with self._lock:
            self._sequence += 1
            event = {
                "type": event_type,
                "sequence": self._sequence,
                "account_id": account_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "telegram_session_id": telegram_session_id,
                "data": data or {},
            }
            for connection in tuple(self._connections):
                if not self._matches(connection.subscription, event):
                    continue
                if connection.queue.full():
                    while not connection.queue.empty():
                        connection.queue.get_nowait()
                    connection.queue.put_nowait(
                        {
                            "type": "resync.required",
                            "sequence": self._sequence,
                            "data": {},
                        }
                    )
                else:
                    connection.queue.put_nowait(event)

    @staticmethod
    def _matches(subscription: EventSubscription, event: dict[str, Any]) -> bool:
        event_session = event.get("telegram_session_id")
        if event_session is not None:
            return event_session == subscription.telegram_session_id
        event_account = event.get("account_id")
        if subscription.account_id is None or event_account is None:
            return False
        if event_account != subscription.account_id:
            return False
        event_chat = event.get("chat_id")
        return (
            subscription.chat_id is None
            or event_chat is None
            or event_chat == subscription.chat_id
        )
