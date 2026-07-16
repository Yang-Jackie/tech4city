from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Response, status

from .analyzer import Analyzer, analyze_message
from .config import ConfigurationError, Settings
from .models import (
    HealthResponse,
    MessageCreate,
    MessageIngestResponse,
    MessageReport,
    StoredMessage,
    WorkerRunResponse,
)
from .mongo_repository import MongoRepository
from .repository import (
    BackendRepository,
    InMemoryRepository,
    MessageConflictError,
    message_key,
)
from .worker import AnalysisWorker


def create_app(
    analyzer: Analyzer = analyze_message,
    repository: BackendRepository | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active_repository = repository
        owns_repository = False
        if active_repository is None:
            active_settings = settings or Settings.load()
            active_repository = build_repository(active_settings)
            owns_repository = True

        await active_repository.initialize()
        app.state.repository = active_repository
        app.state.worker = AnalysisWorker(active_repository, analyzer)
        try:
            yield
        finally:
            if owns_repository:
                await active_repository.close()

    app = FastAPI(
        title="tech4city backend",
        version="0.3.0",
        description="Backend API with injectable memory or MongoDB persistence.",
        lifespan=lifespan,
    )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        active_repository: BackendRepository = app.state.repository
        await active_repository.ping()
        return HealthResponse(
            status="ok",
            storage=active_repository.storage_name,
            analyzer="fake-v1",
        )

    @app.post("/messages", response_model=MessageIngestResponse)
    async def ingest_message(
        message: MessageCreate,
        response: Response,
    ) -> MessageIngestResponse:
        active_repository: BackendRepository = app.state.repository
        key = message_key(message)
        try:
            stored, created = await active_repository.ingest_message(message)
        except MessageConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="message identifier already exists with different content",
            ) from exc

        job = await active_repository.ensure_job(key)
        analysis = await active_repository.get_latest_analysis(key)
        if created:
            response.status_code = status.HTTP_202_ACCEPTED
        return MessageIngestResponse(
            status="created" if created else "duplicate",
            message=stored,
            analysis=analysis,
            analysis_job=job,
        )

    @app.post(
        "/internal/worker/run-once",
        response_model=WorkerRunResponse,
    )
    async def run_worker_once() -> WorkerRunResponse:
        worker: AnalysisWorker = app.state.worker
        result = await worker.run_once()
        if result is None:
            return WorkerRunResponse(status="idle")

        job, analysis = result
        return WorkerRunResponse(
            status="processed",
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
        active_repository: BackendRepository = app.state.repository
        return await active_repository.list_chat_messages(
            telegram_account_id,
            chat_id,
        )

    @app.get(
        "/messages/{message_id}/report",
        response_model=MessageReport,
    )
    async def get_message_report(
        message_id: int,
        telegram_account_id: int = Query(...),
        chat_id: int = Query(...),
    ) -> MessageReport:
        active_repository: BackendRepository = app.state.repository
        key = (telegram_account_id, chat_id, message_id)
        message = await active_repository.get_message(key)
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="message not found",
            )
        job = await active_repository.get_job(key)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="analysis job missing",
            )
        return MessageReport(
            message=message,
            analysis=await active_repository.get_latest_analysis(key),
            analysis_job=job,
        )

    return app


def build_repository(settings: Settings) -> BackendRepository:
    if settings.storage == "memory":
        return InMemoryRepository()
    if settings.mongodb_uri is None:
        raise ConfigurationError("MONGODB_URI is required for MongoDB storage.")
    return MongoRepository(settings.mongodb_uri, settings.mongodb_database)


app = create_app()
