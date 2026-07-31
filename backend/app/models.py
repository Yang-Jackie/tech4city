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


class ChatSummary(BaseModel):
    """Factual chat metadata derived from stored messages."""

    chat_id: int
    message_count: int = Field(ge=1)
    participant_count: int = Field(ge=1)
    first_message_at: datetime
    last_message_at: datetime
    last_message_preview: str


class Layer1Result(BaseModel):
    """Unmodified software contract exposed by the local Layer 1 classifier."""

    status: str
    raw_label: str
    normal_score: float = Field(ge=0, le=1)
    bully_score: float = Field(ge=0, le=1)


class Layer2Result(BaseModel):
    """Layer 2 stage result, including an explicit no-score skipped state."""

    status: str
    raw_label: str | None = None
    normal_score: float | None = Field(default=None, ge=0, le=1)
    bully_score: float | None = Field(default=None, ge=0, le=1)
    user_embedding_strategy: str | None = None
    skip_reason: str | None = None


class Layer3Category(BaseModel):
    label: str
    evidence_strength: str
    message_ids: list[str]
    why: str


class Layer3Evidence(BaseModel):
    message_ids: list[str]
    category: str
    sanitized_excerpt: str
    why_it_matters: str


class Layer3PatternAnalysis(BaseModel):
    is_targeted: bool
    is_repeated: bool
    shows_escalation: bool
    has_power_or_group_dynamic: bool
    notes: str


class Layer3Analysis(BaseModel):
    """Validated conversation analysis returned by the existing Layer 3 contract."""

    is_suspected_cyberbullying: bool
    confidence: float = Field(ge=0, le=1)
    severity: Literal["none", "low", "medium", "high", "urgent"]
    target_user_ids: list[str]
    suspected_actor_user_ids: list[str]
    categories: list[Layer3Category]
    evidence: list[Layer3Evidence]
    pattern_analysis: Layer3PatternAnalysis
    explanation_for_target: str
    uncertainty: list[str]
    recommended_next_steps: list[str]


class Layer3Result(BaseModel):
    layer: Literal[3]
    explanation: str
    analysis: Layer3Analysis
    model: str


class AnalysisResult(BaseModel):
    harmful: bool | None = None
    bully_probability: float | None = Field(default=None, ge=0, le=1)
    severity: Literal["none", "low", "medium", "high", "urgent"] | None = None
    categories: list[str] | None = None
    explanation: str | None = None
    pipeline_version: str
    layer1: Layer1Result | None = None
    layer2: Layer2Result | None = None
    layer3: Layer3Result | None = None


class AnalysisJob(BaseModel):
    job_id: str
    telegram_account_id: int
    chat_id: int
    message_id: int
    status: Literal["pending", "processing", "completed", "failed"]
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
    analysis_job: AnalysisJob | None


class WorkerRunResponse(BaseModel):
    status: Literal["processed", "idle"]
    analysis_job: AnalysisJob | None = None
    analysis: AnalysisResult | None = None


class HealthResponse(BaseModel):
    status: str
    storage: str
    analyzer: str
