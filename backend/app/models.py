from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# accept sth like 
# {
#     "telegram_account_id": 100,
#     "chat_id": 200,
#     "message_id": 123,
#     "sender_id": 300,
#     "text": "Example message",
#     "sent_at": "2026-07-13T10:00:00Z"
# }

class MessageCreate(BaseModel):
    """Normalized text message accepted from TDLib gateway."""

    model_config = ConfigDict(extra="forbid")

    telegram_account_id: int
    chat_id: int
    message_id: int
    sender_id: int
    text: str = Field(min_length=1)
    sent_at: datetime

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value

    @field_validator("sent_at")
    @classmethod
    def sent_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("sent_at must include a timezone")
        return value


class StoredMessage(MessageCreate):
    received_at: datetime


class AnalysisResult(BaseModel):
    harmful: bool
    bully_probability: float = Field(ge=0, le=1)
    severity: Literal["none", "low", "medium", "high", "urgent"]
    categories: list[str]
    explanation: str
    pipeline_version: str


class AnalysisJob(BaseModel):
    job_id: str
    telegram_account_id: int
    chat_id: int
    message_id: int
    status: Literal['pending', 'completed', 'failed']
    attempts: int = Field(ge=0)
    error: str | None = None


class MessageIngestResponse(BaseModel):
    status: Literal["created", "duplicate"]
    message: StoredMessage
    analysis: AnalysisResult | None
    analysis_job: AnalysisJob


class MessageReport(BaseModel):
    message: StoredMessage
    analysis: AnalysisResult | None
    analysis_job: AnalysisJob


class WorkerRunResponse(BaseModel):
    status: Literal['processed', 'idle']
    analysis_job: AnalysisJob | None = None
    analysis: AnalysisResult | None = None


class HealthResponse(BaseModel):
    status: str
    storage: str
    analyzer: str
