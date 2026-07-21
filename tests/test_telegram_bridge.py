from __future__ import annotations

import json
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import MagicMock, patch

from telegram.backend_client import BackendClient, BackendResponse
from telegram.bridge import TelegramBackendBridge
from telegram.normalization import (
    NormalizationError,
    normalize_new_text_message,
)
from telegram.tdjson_client import TdJsonClient


def new_message_update(
    *,
    content: dict[str, object] | None = None,
    sender: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "@type": "updateNewMessage",
        "message": {
            "id": 123,
            "chat_id": 100,
            "date": 1_700_000_000,
            "is_outgoing": True,
            "sender_id": sender
            or {"@type": "messageSenderUser", "user_id": 100},
            "content": content
            or {
                "@type": "messageText",
                "text": {"@type": "formattedText", "text": "bridge test"},
            },
        },
    }


class RecordingBackend:
    def __init__(self, status_code: int = 202) -> None:
        self.status_code = status_code
        self.payloads: list[dict[str, object]] = []

    def post_message(self, payload: dict[str, object]) -> BackendResponse:
        self.payloads.append(dict(payload))
        return BackendResponse(self.status_code, {"status": "created"})


class NormalizationTests(unittest.TestCase):
    def test_normalizes_saved_messages_shaped_text_update(self) -> None:
        payload = normalize_new_text_message(new_message_update(), 100)

        self.assertEqual(
            payload,
            {
                "telegram_account_id": 100,
                "chat_id": 100,
                "message_id": 123,
                "sender_id": 100,
                "text": "bridge test",
                "sent_at": "2023-11-14T22:13:20Z",
            },
        )

    def test_accepts_chat_sender(self) -> None:
        event = new_message_update(
            sender={"@type": "messageSenderChat", "chat_id": -900},
        )
        payload = normalize_new_text_message(event, 100)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["sender_id"], -900)

    def test_ignores_non_text_and_blank_text(self) -> None:
        media = new_message_update(content={"@type": "messagePhoto"})
        blank = new_message_update(
            content={"@type": "messageText", "text": {"text": "  "}},
        )

        self.assertIsNone(normalize_new_text_message(media, 100))
        self.assertIsNone(normalize_new_text_message(blank, 100))

    def test_rejects_malformed_relevant_update(self) -> None:
        event = new_message_update(sender={"@type": "unexpectedSender"})

        with self.assertRaises(NormalizationError):
            normalize_new_text_message(event, 100)


class UpdateSubscriptionTests(unittest.TestCase):
    def test_dispatch_forwards_new_message_to_registered_handler(self) -> None:
        client = object.__new__(TdJsonClient)
        client._update_handlers_lock = threading.Lock()
        client._update_handlers = []
        received: list[dict[str, object]] = []
        client.add_update_handler(received.append)

        event = new_message_update()
        client._dispatch(event)
        client.remove_update_handler(received.append)
        client._dispatch(event)

        self.assertEqual(received, [event])


class BackendClientTests(unittest.TestCase):
    def test_posts_backend_contract_as_json(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 202
        response.read.return_value = b'{"status":"created"}'
        payload = normalize_new_text_message(new_message_update(), 100)
        self.assertIsNotNone(payload)

        with patch("telegram.backend_client.urlopen", return_value=response) as send:
            result = BackendClient("http://127.0.0.1:8000").post_message(payload)

        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8000/messages")
        self.assertEqual(json.loads(request.data), payload)
        self.assertTrue(result.accepted)


class BridgeFlowTests(unittest.TestCase):
    def test_saved_messages_update_reaches_backend_client(self) -> None:
        backend = RecordingBackend()
        bridge = TelegramBackendBridge(backend, telegram_account_id=100)
        bridge.enqueue_update(new_message_update())

        with redirect_stdout(StringIO()):
            processed = bridge.run_once()

        self.assertTrue(processed)
        self.assertEqual(len(backend.payloads), 1)
        self.assertEqual(backend.payloads[0]["text"], "bridge test")
        self.assertFalse(bridge.run_once())

    def test_non_text_update_does_not_reach_backend(self) -> None:
        backend = RecordingBackend()
        bridge = TelegramBackendBridge(backend, telegram_account_id=100)
        bridge.enqueue_update(
            new_message_update(content={"@type": "messagePhoto"})
        )

        self.assertTrue(bridge.run_once())
        self.assertEqual(backend.payloads, [])


if __name__ == "__main__":
    unittest.main()
