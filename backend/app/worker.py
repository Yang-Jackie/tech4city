"""Background analysis worker over the persistence contract."""

from __future__ import annotations

from .analyzer import Analyzer
from .models import AnalysisJob, AnalysisResult
from .repository import BackendRepository, MessageKey


class AnalysisWorker:
    """Claim and process one durable analysis job at a time."""

    def __init__(self, repository: BackendRepository, analyzer: Analyzer) -> None:
        self._repository = repository
        self._analyzer = analyzer

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
            return failed, None
        context = await self._repository.list_context_before(message)

        try:
            analysis = await self._analyzer(message, context)
        except Exception:
            failed = await self._repository.fail_job(key, "analysis failed")
            return failed, None

        completed = await self._repository.complete_job(key, analysis)
        return completed, analysis
