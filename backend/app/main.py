from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Response, status

from .analyzer import Analyzer, Layer1Analyzer, analyze_message, analyzer_version
from .config import ConfigurationError, Settings
from .ingestion import IncomingMessageService
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
)
from .worker import AnalysisWorker, AnalysisWorkerRunner


def create_app(
    analyzer: Analyzer | None = None,
    repository: BackendRepository | None = None,
    settings: Settings | None = None,
    worker_enabled: bool | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active_settings = settings or Settings.load()
        active_repository = repository
        owns_repository = False
        if active_repository is None:
            active_repository = build_repository(active_settings)
            owns_repository = True

        await active_repository.initialize()
        active_analyzer = analyzer or build_analyzer(active_settings)
        worker = AnalysisWorker(active_repository, active_analyzer)
        runner = AnalysisWorkerRunner(worker, active_settings.worker_poll_seconds)
        should_run_worker = (
            active_settings.worker_enabled if worker_enabled is None else worker_enabled
        )
        app.state.repository = active_repository
        app.state.worker = worker
        app.state.worker_runner = runner
        app.state.ingestion_service = IncomingMessageService(
            active_repository,
            runner.notify if should_run_worker else None,
        )
        app.state.analyzer_version = analyzer_version(active_analyzer)
        if should_run_worker:
            runner.start()
        try:
            yield
        finally:
            if should_run_worker:
                await runner.stop()
            if owns_repository:
                await active_repository.close()

    app = FastAPI(
        title="tech4city backend",
        version="0.4.0",
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
            analyzer=app.state.analyzer_version,
        )

    @app.post("/messages", response_model=MessageIngestResponse)
    async def ingest_message(
        message: MessageCreate,
        response: Response,
    ) -> MessageIngestResponse:
        service: IncomingMessageService = app.state.ingestion_service
        try:
            result = await service.process(message)
        except MessageConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="message identifier already exists with different content",
            ) from exc

        if result.created:
            response.status_code = status.HTTP_202_ACCEPTED
        return MessageIngestResponse(
            status="created" if result.created else "duplicate",
            message=result.message,
            analysis=result.analysis,
            analysis_job=result.analysis_job,
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


def build_analyzer(settings: Settings) -> Analyzer:
    if settings.analyzer == "fake":
        return analyze_message
    return Layer1Analyzer(
        pipeline_version=settings.layer1_pipeline_version,
        model_dir=settings.layer1_model_dir,
    )


app = create_app()
