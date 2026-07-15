from __future__ import annotations

from collections import deque

from .analyzer import Analyzer
from .models import AnalysisJob, AnalysisResult, StoredMessage

MessageKey = tuple[int, int, int]


class InMemoryAnalysisWorker:
    '''Minimal FIFO job processor for demonstrating the worker boundary.'''

    def __init__(
        self,
        messages: dict[MessageKey, StoredMessage],
        analyses: dict[MessageKey, AnalysisResult],
        analyzer: Analyzer,
    ) -> None:
        self._messages = messages
        self._analyses = analyses
        self._analyzer = analyzer
        self._jobs: dict[MessageKey, AnalysisJob] = {}
        self._queue: deque[MessageKey] = deque()

    def enqueue(self, key: MessageKey) -> AnalysisJob:
        existing = self._jobs.get(key)
        if existing is not None:
            return existing

        account_id, chat_id, message_id = key
        job = AnalysisJob(
            job_id=f'{account_id}:{chat_id}:{message_id}',
            telegram_account_id=account_id,
            chat_id=chat_id,
            message_id=message_id,
            status='pending',
            attempts=0,
        )
        self._jobs[key] = job
        self._queue.append(key)
        return job

    def job_for(self, key: MessageKey) -> AnalysisJob:
        return self._jobs[key]

    async def run_once(
        self,
    ) -> tuple[AnalysisJob, AnalysisResult | None] | None:
        if not self._queue:
            return None

        key = self._queue.popleft()
        job = self._jobs[key]
        message = self._messages[key]
        job.attempts += 1

        context = sorted(
            (
                candidate
                for candidate_key, candidate in self._messages.items()
                if candidate_key != key
                and candidate.telegram_account_id == message.telegram_account_id
                and candidate.chat_id == message.chat_id
                and (candidate.sent_at, candidate.message_id)
                < (message.sent_at, message.message_id)
            ),
            key=lambda candidate: (candidate.sent_at, candidate.message_id),
        )

        try:
            analysis = await self._analyzer(message, context)
        except Exception:
            job.status = 'failed'
            job.error = 'analysis failed'
            return job, None

        self._analyses[key] = analysis
        job.status = 'completed'
        return job, analysis
