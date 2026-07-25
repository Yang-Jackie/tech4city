"""Public schemas for browser-driven Telegram authorization."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoginValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=256)


class TelegramLoginStatus(BaseModel):
    session_id: str
    status: str
    telegram_account_id: int | None = None
    saved_messages_chat_id: int | None = None
    display_name: str | None = None
    error: str | None = None
    password_hint: str | None = None
    code_type: str | None = None


class TelegramLogoutStatus(BaseModel):
    session_id: str
    status: str
