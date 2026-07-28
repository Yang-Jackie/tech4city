"""Background analysis worker over the persistence contract."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

from .analyzer import Analyzer
from .models import AnalysisJob, AnalysisResult
from .repository import BackendRepository, MessageKey


class AnalysisWorker:
    """Claim and process one durable analysis job at a time."""

    def __init__(
        self,
        repository: BackendRepository,
        analyzer: Analyzer,
        notify_event: Callable[[AnalysisJob, AnalysisResult | None], Awaitable[None]]
        | None = None,
    ) -> None:
        self._repository = repository
        self._analyzer = analyzer
        self._notify_event = notify_event

    async def run_once(
        self,
    ) -> tuple[AnalysisJob, AnalysisResult | None] | None:
        job = await self._repository.claim_next_job()
        if job is None:
            return None

        key: MessageKey = (
            job.telegram_account_id,
            job.chat_id,
            job.message_id,
        )
        message = await self._repository.get_message(key)
        if message is None:
            failed = await self._repository.fail_job(key, "analysis failed")
            await self._notify(failed, None)
            return failed, None
        context = await self._repository.list_context_before(message)

        try:
            analysis = await self._analyzer(message, context)
        except Exception:
            failed = await self._repository.fail_job(key, "analysis failed")
            await self._notify(failed, None)
            return failed, None

        completed = await self._repository.complete_job(key, analysis)
        await self._notify(completed, analysis)
        return completed, analysis

    async def _notify(self, job: AnalysisJob, analysis: AnalysisResult | None) -> None:
        if self._notify_event is not None:
            await self._notify_event(job, analysis)


class AnalysisWorkerRunner:
    """Run queued analysis jobs automatically during the application lifespan."""

    def __init__(self, worker: AnalysisWorker, poll_seconds: float) -> None:
        self._worker = worker
        self._poll_seconds = poll_seconds
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("analysis worker runner is already started")
        self._wake_event.set()
        self._task = asyncio.create_task(self._run(), name="analysis-worker")

    def notify(self) -> None:
        self._wake_event.set()

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._wake_event.set()
        await self._task
        self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self._wake_event.wait(), timeout=self._poll_seconds
                )
            self._wake_event.clear()
            while not self._stop_event.is_set():
                result = await self._worker.run_once()
                if result is None:
                    break
