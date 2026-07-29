"""Public schemas for browser-driven Telegram authorization."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=256)


class TelegramLoginStatus(BaseModel):
    session_id: str
    status: str
    telegram_account_id: int | None = None
    saved_messages_chat_id: int | None = None
    selected_chat_id: int | None = None
    display_name: str | None = None
    error: str | None = None
    password_hint: str | None = None
    code_type: str | None = None


class TelegramChatSummary(BaseModel):
    chat_id: int
    title: str
    chat_type: Literal["private", "basic_group", "supergroup", "secret", "unknown"]
    unread_count: int = Field(ge=0)
    last_message_at: datetime | None = None
    last_message_preview: str = ""
    is_saved_messages: bool = False


class TelegramChatOpenStatus(BaseModel):
    session_id: str
    chat_id: int
    history_message_count: int = Field(ge=0)
    message_count: int = Field(ge=0)
    new_message_count: int = Field(ge=0)


class TelegramLogoutStatus(BaseModel):
    session_id: str
    status: str
