from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Query, Response, status

from .analyzer import Analyzer, analyze_message
from .models import (
    AnalysisResult,
    HealthResponse,
    MessageCreate,
    MessageIngestResponse,
    MessageReport,
    StoredMessage,
    WorkerRunResponse,
)
from .worker import InMemoryAnalysisWorker, MessageKey


def create_app(analyzer: Analyzer = analyze_message) -> FastAPI:
    app = FastAPI(
        title="tech4city backend",
        version="0.2.0",
        description="Minimal offline skeleton for the system's main API contracts.",
    )
    messages: dict[MessageKey, StoredMessage] = {}
    analyses: dict[MessageKey, AnalysisResult] = {}
    worker = InMemoryAnalysisWorker(messages, analyses, analyzer)

    def message_key(message: MessageCreate) -> MessageKey:
        return (
            message.telegram_account_id,
            message.chat_id,
            message.message_id,
        )

    def conversation(telegram_account_id: int, chat_id: int) -> list[StoredMessage]:
        matching = [
            message
            for message in messages.values()
            if message.telegram_account_id == telegram_account_id
            and message.chat_id == chat_id
        ]
        return sorted(
            matching,
            key=lambda message: (message.sent_at, message.message_id),
        )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            storage="memory",
            analyzer="fake-v1",
        )

    @app.post("/messages", response_model=MessageIngestResponse)
    async def ingest_message(
        message: MessageCreate,
        response: Response,
    ) -> MessageIngestResponse:
        key = message_key(message)
        existing = messages.get(key)

        if existing is not None:
            if existing.model_dump(exclude={"received_at"}) != message.model_dump():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="message identifier already exists with different content",
                )
            return MessageIngestResponse(
                status="duplicate",
                message=existing,
                analysis=analyses.get(key),
                analysis_job=worker.job_for(key),
            )

        stored = StoredMessage(
            **message.model_dump(),
            received_at=datetime.now(UTC),
        )
        messages[key] = stored
        job = worker.enqueue(key)
        response.status_code = status.HTTP_202_ACCEPTED
        return MessageIngestResponse(
            status="created",
            message=stored,
            analysis=None,
            analysis_job=job,
        )

    @app.post(
        '/internal/worker/run-once',
        response_model=WorkerRunResponse,
    )
    async def run_worker_once() -> WorkerRunResponse:
        result = await worker.run_once()
        if result is None:
            return WorkerRunResponse(status='idle')

        job, analysis = result
        return WorkerRunResponse(
            status='processed',
            analysis_job=job,
            analysis=analysis,
        )

    @app.get(
        "/chats/{chat_id}/messages",
        response_model=list[StoredMessage],
    )
    async def list_chat_messages(
        chat_id: int,
        telegram_account_id: int = Query(...),
    ) -> list[StoredMessage]:
        return conversation(telegram_account_id, chat_id)

    @app.get(
        "/messages/{message_id}/report",
        response_model=MessageReport,
    )
    async def get_message_report(
        message_id: int,
        telegram_account_id: int = Query(...),
        chat_id: int = Query(...),
    ) -> MessageReport:
        key = (telegram_account_id, chat_id, message_id)
        message = messages.get(key)
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="message not found",
            )
        return MessageReport(
            message=message,
            analysis=analyses.get(key),
            analysis_job=worker.job_for(key),
        )

    return app


app = create_app()
