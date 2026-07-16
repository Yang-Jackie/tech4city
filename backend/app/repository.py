"""Persistence contracts and the offline in-memory implementation."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime
from typing import Protocol

from .models import AnalysisJob, AnalysisResult, MessageCreate, StoredMessage

MessageKey = tuple[int, int, int]


class MessageConflictError(RuntimeError):
    """A message identity was reused with different immutable content."""


class BackendRepository(Protocol):
    storage_name: str

    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def ping(self) -> None: ...

    async def ingest_message(
        self, message: MessageCreate
    ) -> tuple[StoredMessage, bool]: ...

    async def ensure_job(self, key: MessageKey) -> AnalysisJob: ...

    async def get_job(self, key: MessageKey) -> AnalysisJob | None: ...

    async def claim_next_job(self) -> AnalysisJob | None: ...

    async def complete_job(
        self, key: MessageKey, analysis: AnalysisResult
    ) -> AnalysisJob: ...

    async def fail_job(self, key: MessageKey, error: str) -> AnalysisJob: ...

    async def get_message(self, key: MessageKey) -> StoredMessage | None: ...

    async def list_chat_messages(
        self, telegram_account_id: int, chat_id: int
    ) -> list[StoredMessage]: ...

    async def list_context_before(
        self, message: StoredMessage
    ) -> list[StoredMessage]: ...

    async def get_latest_analysis(self, key: MessageKey) -> AnalysisResult | None: ...


class InMemoryRepository:
    """Process-local repository used by default and by offline tests."""

    storage_name = "memory"

    def __init__(self) -> None:
        self._messages: dict[MessageKey, StoredMessage] = {}
        self._jobs: dict[MessageKey, AnalysisJob] = {}
        self._queue: deque[MessageKey] = deque()
        self._analysis_runs: dict[MessageKey, list[AnalysisResult]] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def ingest_message(
        self, message: MessageCreate
    ) -> tuple[StoredMessage, bool]:
        key = message_key(message)
        async with self._lock:
            existing = self._messages.get(key)
            if existing is not None:
                if existing.model_dump(exclude={"received_at"}) != message.model_dump():
                    raise MessageConflictError
                return existing.model_copy(deep=True), False

            stored = StoredMessage(
                **message.model_dump(),
                received_at=datetime.now(UTC),
            )
            self._messages[key] = stored
            return stored.model_copy(deep=True), True

    async def ensure_job(self, key: MessageKey) -> AnalysisJob:
        async with self._lock:
            existing = self._jobs.get(key)
            if existing is not None:
                return existing.model_copy(deep=True)
            account_id, chat_id, telegram_message_id = key
            job = AnalysisJob(
                job_id=job_id(key),
                telegram_account_id=account_id,
                chat_id=chat_id,
                message_id=telegram_message_id,
                status="pending",
                attempts=0,
            )
            self._jobs[key] = job
            self._queue.append(key)
            return job.model_copy(deep=True)

    async def get_job(self, key: MessageKey) -> AnalysisJob | None:
        async with self._lock:
            job = self._jobs.get(key)
            return job.model_copy(deep=True) if job is not None else None

    async def claim_next_job(self) -> AnalysisJob | None:
        async with self._lock:
            while self._queue:
                key = self._queue.popleft()
                job = self._jobs[key]
                if job.status != "pending":
                    continue
                job.status = "processing"
                job.attempts += 1
                job.error = None
                return job.model_copy(deep=True)
            return None

    async def complete_job(
        self, key: MessageKey, analysis: AnalysisResult
    ) -> AnalysisJob:
        async with self._lock:
            job = self._jobs[key]
            self._analysis_runs.setdefault(key, []).append(
                analysis.model_copy(deep=True)
            )
            job.status = "completed"
            job.error = None
            return job.model_copy(deep=True)

    async def fail_job(self, key: MessageKey, error: str) -> AnalysisJob:
        async with self._lock:
            job = self._jobs[key]
            job.status = "failed"
            job.error = error
            return job.model_copy(deep=True)

    async def get_message(self, key: MessageKey) -> StoredMessage | None:
        async with self._lock:
            message = self._messages.get(key)
            return message.model_copy(deep=True) if message is not None else None

    async def list_chat_messages(
        self, telegram_account_id: int, chat_id: int
    ) -> list[StoredMessage]:
        async with self._lock:
            matching = [
                message.model_copy(deep=True)
                for message in self._messages.values()
                if message.telegram_account_id == telegram_account_id
                and message.chat_id == chat_id
            ]
        return sorted(matching, key=lambda item: (item.sent_at, item.message_id))

    async def list_context_before(self, message: StoredMessage) -> list[StoredMessage]:
        async with self._lock:
            matching = [
                candidate.model_copy(deep=True)
                for candidate in self._messages.values()
                if candidate.telegram_account_id == message.telegram_account_id
                and candidate.chat_id == message.chat_id
                and (candidate.sent_at, candidate.message_id)
                < (message.sent_at, message.message_id)
            ]
        return sorted(matching, key=lambda item: (item.sent_at, item.message_id))

    async def get_latest_analysis(self, key: MessageKey) -> AnalysisResult | None:
        async with self._lock:
            runs = self._analysis_runs.get(key, [])
            return runs[-1].model_copy(deep=True) if runs else None


def message_key(message: MessageCreate) -> MessageKey:
    return (
        message.telegram_account_id,
        message.chat_id,
        message.message_id,
    )


def job_id(key: MessageKey) -> str:
    return f"{key[0]}:{key[1]}:{key[2]}"
