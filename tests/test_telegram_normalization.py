from __future__ import annotations

import threading
import unittest

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
            "sender_id": sender or {"@type": "messageSenderUser", "user_id": 100},
            "content": content
            or {
                "@type": "messageText",
                "text": {"@type": "formattedText", "text": "normalization test"},
            },
        },
    }


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
                "text": "normalization test",
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


if __name__ == "__main__":
    unittest.main()
