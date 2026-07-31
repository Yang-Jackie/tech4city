"""Application service for normalized incoming Telegram text messages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .models import AnalysisJob, AnalysisResult, MessageCreate, StoredMessage
from .repository import BackendRepository, message_key


@dataclass(frozen=True)
class IngestionResult:
    message: StoredMessage
    created: bool
    analysis_job: AnalysisJob
    analysis: AnalysisResult | None


class IncomingMessageService:
    """Persist and enqueue one normalized new-text-message event."""

    def __init__(
        self,
        repository: BackendRepository,
        notify_worker: Callable[[], None] | None = None,
        notify_event: Callable[[StoredMessage], Awaitable[None]] | None = None,
    ) -> None:
        self._repository = repository
        self._notify_worker = notify_worker or (lambda: None)
        self._notify_event = notify_event

    async def store_history(self, message: MessageCreate) -> tuple[StoredMessage, bool]:
        """Persist historical context without creating an analysis job."""
        return await self._repository.ingest_message(message)

    async def process(self, message: MessageCreate) -> IngestionResult:
        key = message_key(message)
        stored, created = await self._repository.ingest_message(message)
        job = await self._repository.ensure_job(key)
        analysis = await self._repository.get_latest_analysis(key)
        if job.status == "pending":
            self._notify_worker()
        if created and self._notify_event is not None:
            await self._notify_event(stored)
        return IngestionResult(
            message=stored,
            created=created,
            analysis_job=job,
            analysis=analysis,
        )
