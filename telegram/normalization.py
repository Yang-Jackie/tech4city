"""Normalize TDLib updates into the backend's strict message contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict


class NormalizationError(ValueError):
    """A relevant TDLib update cannot satisfy the backend contract."""


class NormalizedMessage(TypedDict):
    telegram_account_id: int
    chat_id: int
    message_id: int
    sender_id: int
    text: str
    sent_at: str


def normalize_new_text_message(
    event: dict[str, Any],
    telegram_account_id: int,
) -> NormalizedMessage | None:
    """Return a backend payload for a new text message, or ``None`` to ignore it."""
    if event.get("@type") != "updateNewMessage":
        return None

    message = event.get("message")
    if not isinstance(message, dict):
        raise NormalizationError("updateNewMessage is missing its message object")

    content = message.get("content")
    if not isinstance(content, dict) or content.get("@type") != "messageText":
        return None

    formatted_text = content.get("text")
    if not isinstance(formatted_text, dict):
        raise NormalizationError("messageText is missing its formatted text object")
    text = formatted_text.get("text")
    if not isinstance(text, str):
        raise NormalizationError("messageText text must be a string")
    if not text.strip():
        return None

    sender = message.get("sender_id")
    if not isinstance(sender, dict):
        raise NormalizationError("message is missing its sender")
    sender_type = sender.get("@type")
    if sender_type == "messageSenderUser":
        sender_id = _required_int(sender, "user_id")
    elif sender_type == "messageSenderChat":
        sender_id = _required_int(sender, "chat_id")
    else:
        raise NormalizationError(f"unsupported message sender type: {sender_type!r}")

    sent_at = datetime.fromtimestamp(
        _required_int(message, "date"),
        tz=UTC,
    ).isoformat().replace("+00:00", "Z")

    return {
        "telegram_account_id": _validate_int(
            telegram_account_id,
            "telegram_account_id",
        ),
        "chat_id": _required_int(message, "chat_id"),
        "message_id": _required_int(message, "id"),
        "sender_id": sender_id,
        "text": text,
        "sent_at": sent_at,
    }


def message_identity(payload: NormalizedMessage) -> str:
    """Return a log-safe stable identity without including message content."""
    return (
        f"{payload['telegram_account_id']}:"
        f"{payload['chat_id']}:"
        f"{payload['message_id']}"
    )


def _required_int(source: dict[str, Any], name: str) -> int:
    if name not in source:
        raise NormalizationError(f"message is missing {name}")
    return _validate_int(source[name], name)


def _validate_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise NormalizationError(f"{name} must be an integer")
    return value


__all__ = [
    "NormalizationError",
    "NormalizedMessage",
    "message_identity",
    "normalize_new_text_message",
]
