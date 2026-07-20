"""Application service for normalized incoming Telegram text messages."""

from __future__ import annotations

from collections.abc import Callable
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
    ) -> None:
        self._repository = repository
        self._notify_worker = notify_worker or (lambda: None)

    async def process(self, message: MessageCreate) -> IngestionResult:
        key = message_key(message)
        stored, created = await self._repository.ingest_message(message)
        job = await self._repository.ensure_job(key)
        analysis = await self._repository.get_latest_analysis(key)
        if job.status == "pending":
            self._notify_worker()
        return IngestionResult(
            message=stored,
            created=created,
            analysis_job=job,
            analysis=analysis,
        )
