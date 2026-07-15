"""Safe terminal formatting for common TDLib objects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def partial_phone(phone_number: str) -> str:
    if not phone_number:
        return "(not available)"
    visible = min(4, len(phone_number))
    return "*" * (len(phone_number) - visible) + phone_number[-visible:]


def user_name(user: dict[str, Any] | None) -> str:
    if not user:
        return "Unknown user"
    full_name = " ".join(
        part for part in (user.get("first_name", ""), user.get("last_name", "")) if part
    ).strip()
    usernames = user.get("usernames") or {}
    active = usernames.get("active_usernames") or []
    suffix = f" (@{active[0]})" if active else ""
    return (full_name or f"User {user.get('id', '?')}") + suffix


def message_text(content: dict[str, Any]) -> str:
    content_type = content.get("@type", "unknown")
    if content_type == "messageText":
        return (content.get("text") or {}).get("text", "")

    labels = {
        "messagePhoto": "Photo",
        "messageVideo": "Video",
        "messageDocument": "Document",
        "messageAudio": "Audio",
        "messageVoiceNote": "Voice note",
        "messageVideoNote": "Video note",
        "messageAnimation": "Animation",
        "messageSticker": "Sticker",
        "messageLocation": "Location",
        "messageContact": "Contact",
        "messagePoll": "Poll",
    }
    label = labels.get(content_type, content_type.removeprefix("message") or "Unknown")
    caption = (content.get("caption") or {}).get("text", "")
    if content_type == "messageSticker":
        emoji = (content.get("sticker") or {}).get("emoji", "")
        caption = emoji or caption
    return f"[{label}]" + (f" {caption}" if caption else "")


def format_message(
    message: dict[str, Any], users: dict[int, dict[str, Any]]
) -> str:
    sender = message.get("sender_id") or {}
    if sender.get("@type") == "messageSenderUser":
        sender_id = sender.get("user_id")
        sender_label = user_name(users.get(sender_id))
    elif sender.get("@type") == "messageSenderChat":
        sender_label = f"Chat {sender.get('chat_id', '?')}"
    else:
        sender_label = "Unknown sender"

    timestamp = datetime.fromtimestamp(message.get("date", 0), tz=timezone.utc).astimezone()
    body = message_text(message.get("content") or {}).replace("\n", " ").strip()
    return f"{timestamp:%Y-%m-%d %H:%M:%S} | {sender_label}: {body}"
