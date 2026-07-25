from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Cookie, FastAPI, HTTPException, Query, Response, status

from .analyzer import Analyzer, Layer1Analyzer, analyze_message, analyzer_version
from .config import ConfigurationError, Settings
from .ingestion import IncomingMessageService
from .models import (
    ChatSummary,
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
from .telegram_login import TelegramLoginError, TelegramSessionManager
from .telegram_models import LoginValue, TelegramLoginStatus, TelegramLogoutStatus
from .worker import AnalysisWorker, AnalysisWorkerRunner

TelegramManagerFactory = Callable[[Any], Any]


def create_app(
    analyzer: Analyzer | None = None,
    repository: BackendRepository | None = None,
    settings: Settings | None = None,
    worker_enabled: bool | None = None,
    telegram_manager_factory: TelegramManagerFactory | None = None,
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
        manager_factory = telegram_manager_factory or TelegramSessionManager
        app.state.telegram_manager = manager_factory(app.state.ingestion_service)
        if should_run_worker:
            runner.start()
        try:
            yield
        finally:
            await app.state.telegram_manager.close()
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
        "/chats",
        response_model=list[ChatSummary],
    )
    async def list_chats(
        telegram_account_id: int = Query(...),
    ) -> list[ChatSummary]:
        active_repository: BackendRepository = app.state.repository
        return await active_repository.list_chats(telegram_account_id)

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

    def require_owner(owner: str | None) -> str:
        if not owner:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Telegram browser session is missing",
            )
        return owner

    async def telegram_action(action: Any) -> Any:
        try:
            return await action
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Telegram login session not found",
            ) from exc
        except TelegramLoginError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except (FileNotFoundError, ConfigurationError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    @app.post(
        "/telegram/login",
        response_model=TelegramLoginStatus,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_telegram_login(
        response: Response,
        tech4city_owner: str | None = Cookie(default=None),
    ) -> TelegramLoginStatus:
        import secrets

        owner = tech4city_owner or secrets.token_urlsafe(32)
        result = await telegram_action(app.state.telegram_manager.create(owner))
        if tech4city_owner is None:
            response.set_cookie(
                "tech4city_owner",
                owner,
                httponly=True,
                samesite="strict",
                secure=False,
                path="/",
                max_age=60 * 60 * 24 * 30,
            )
        response.headers["Cache-Control"] = "no-store"
        return TelegramLoginStatus(**result)

    @app.get(
        "/telegram/login/{session_id}",
        response_model=TelegramLoginStatus,
    )
    async def telegram_login_status(
        session_id: str,
        response: Response,
        tech4city_owner: str | None = Cookie(default=None),
    ) -> TelegramLoginStatus:
        result = await telegram_action(
            app.state.telegram_manager.status(
                session_id, require_owner(tech4city_owner)
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return TelegramLoginStatus(**result)

    async def submit_telegram_value(
        session_id: str,
        owner: str | None,
        kind: str,
        body: LoginValue,
    ) -> TelegramLoginStatus:
        result = await telegram_action(
            app.state.telegram_manager.submit(
                session_id, require_owner(owner), kind, body.value
            )
        )
        return TelegramLoginStatus(**result)

    @app.post(
        "/telegram/login/{session_id}/phone",
        response_model=TelegramLoginStatus,
    )
    async def submit_telegram_phone(
        session_id: str,
        body: LoginValue,
        response: Response,
        tech4city_owner: str | None = Cookie(default=None),
    ) -> TelegramLoginStatus:
        response.headers["Cache-Control"] = "no-store"
        return await submit_telegram_value(session_id, tech4city_owner, "phone", body)

    @app.post(
        "/telegram/login/{session_id}/code",
        response_model=TelegramLoginStatus,
    )
    async def submit_telegram_code(
        session_id: str,
        body: LoginValue,
        response: Response,
        tech4city_owner: str | None = Cookie(default=None),
    ) -> TelegramLoginStatus:
        response.headers["Cache-Control"] = "no-store"
        return await submit_telegram_value(session_id, tech4city_owner, "code", body)

    @app.post(
        "/telegram/login/{session_id}/password",
        response_model=TelegramLoginStatus,
    )
    async def submit_telegram_password(
        session_id: str,
        body: LoginValue,
        response: Response,
        tech4city_owner: str | None = Cookie(default=None),
    ) -> TelegramLoginStatus:
        response.headers["Cache-Control"] = "no-store"
        return await submit_telegram_value(
            session_id, tech4city_owner, "password", body
        )

    @app.post(
        "/telegram/login/{session_id}/logout",
        response_model=TelegramLogoutStatus,
    )
    async def logout_telegram(
        session_id: str,
        response: Response,
        tech4city_owner: str | None = Cookie(default=None),
    ) -> TelegramLogoutStatus:
        result = await telegram_action(
            app.state.telegram_manager.logout(
                session_id, require_owner(tech4city_owner)
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return TelegramLogoutStatus(**result)

    async def owned_telegram_account(session_id: str, owner: str | None) -> int:
        return await telegram_action(
            app.state.telegram_manager.account_id(session_id, require_owner(owner))
        )

    @app.get(
        "/telegram/login/{session_id}/chats",
        response_model=list[ChatSummary],
    )
    async def list_owned_telegram_chats(
        session_id: str,
        response: Response,
        tech4city_owner: str | None = Cookie(default=None),
    ) -> list[ChatSummary]:
        account_id = await owned_telegram_account(session_id, tech4city_owner)
        response.headers["Cache-Control"] = "no-store"
        return await app.state.repository.list_chats(account_id)

    @app.get(
        "/telegram/login/{session_id}/chats/{chat_id}/messages",
        response_model=list[StoredMessage],
    )
    async def list_owned_telegram_messages(
        session_id: str,
        chat_id: int,
        response: Response,
        tech4city_owner: str | None = Cookie(default=None),
    ) -> list[StoredMessage]:
        account_id = await owned_telegram_account(session_id, tech4city_owner)
        saved_chat_id = await telegram_action(
            app.state.telegram_manager.saved_chat_id(
                session_id, require_owner(tech4city_owner)
            )
        )
        if chat_id != saved_chat_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Saved Messages is available",
            )
        response.headers["Cache-Control"] = "no-store"
        return await app.state.repository.list_chat_messages(account_id, chat_id)

    @app.get(
        "/telegram/login/{session_id}/messages/{message_id}/report",
        response_model=MessageReport,
    )
    async def get_owned_telegram_report(
        session_id: str,
        message_id: int,
        response: Response,
        tech4city_owner: str | None = Cookie(default=None),
    ) -> MessageReport:
        account_id = await owned_telegram_account(session_id, tech4city_owner)
        saved_chat_id = await telegram_action(
            app.state.telegram_manager.saved_chat_id(
                session_id, require_owner(tech4city_owner)
            )
        )
        key = (account_id, saved_chat_id, message_id)
        message = await app.state.repository.get_message(key)
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="message not found",
            )
        job = await app.state.repository.get_job(key)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="analysis job missing",
            )
        response.headers["Cache-Control"] = "no-store"
        return MessageReport(
            message=message,
            analysis=await app.state.repository.get_latest_analysis(key),
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
