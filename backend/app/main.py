from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from typing import Any
from urllib.parse import urlparse

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from .analyzer import (
    Analyzer,
    Layer1Analyzer,
    Layer1Layer2Analyzer,
    Layer1Layer2Layer3Analyzer,
    Layer2SkippedAnalyzer,
    Layer3Analyzer,
    analyze_message,
    analyzer_version,
)
from .config import ConfigurationError, Settings
from .events import EventConnection, LocalEventBroker
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
from .telegram_models import (
    LoginValue,
    TelegramChatOpenStatus,
    TelegramChatSummary,
    TelegramLoginStatus,
    TelegramLogoutStatus,
)
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
        event_broker = LocalEventBroker()

        async def message_event(message: StoredMessage) -> None:
            await event_broker.publish(
                "message.created",
                account_id=message.telegram_account_id,
                chat_id=message.chat_id,
                message_id=message.message_id,
            )
            await event_broker.publish(
                "chat.updated",
                account_id=message.telegram_account_id,
                chat_id=message.chat_id,
            )

        async def analysis_event(job: Any, _analysis: Any) -> None:
            await event_broker.publish(
                "analysis.updated",
                account_id=job.telegram_account_id,
                chat_id=job.chat_id,
                message_id=job.message_id,
                data={"status": job.status},
            )

        worker = AnalysisWorker(
            active_repository,
            active_analyzer,
            notify_event=analysis_event,
        )
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
            message_event,
        )
        app.state.analyzer_version = analyzer_version(active_analyzer)
        app.state.event_broker = event_broker
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
        title="Detectives backend",
        version="0.5.0",
        description="Backend API with injectable memory or MongoDB persistence.",
        lifespan=lifespan,
    )

    def websocket_origin_allowed(websocket: WebSocket) -> bool:
        origin = websocket.headers.get("origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        expected_scheme = "https" if websocket.url.scheme == "wss" else "http"
        return (
            parsed.scheme == expected_scheme
            and parsed.netloc == websocket.headers.get("host")
        )

    async def websocket_sender(
        websocket: WebSocket, connection: EventConnection
    ) -> None:
        while True:
            await websocket.send_json(await connection.queue.get())

    @app.websocket("/ws")
    async def websocket_events(websocket: WebSocket) -> None:
        if not websocket_origin_allowed(websocket):
            await websocket.close(code=1008, reason="Origin not allowed")
            return
        await websocket.accept()
        broker: LocalEventBroker = app.state.event_broker
        connection = await broker.connect()
        sender = asyncio.create_task(
            websocket_sender(websocket, connection),
            name="websocket-event-sender",
        )
        await connection.queue.put(
            {"type": "connection.ready", "sequence": 0, "data": {}}
        )
        try:
            while True:
                command = await websocket.receive_json()
                if not isinstance(command, dict):
                    await connection.queue.put(
                        {
                            "type": "subscription.error",
                            "sequence": 0,
                            "data": {"detail": "Command must be an object"},
                        }
                    )
                    continue
                command_type = command.get("type")
                if command_type == "ping":
                    await connection.queue.put(
                        {"type": "pong", "sequence": 0, "data": {}}
                    )
                    continue
                if command_type != "subscribe":
                    await connection.queue.put(
                        {
                            "type": "subscription.error",
                            "sequence": 0,
                            "data": {"detail": "Unsupported command"},
                        }
                    )
                    continue
                session_id = command.get("telegram_session_id")
                chat_id = command.get("chat_id")
                if chat_id is not None and not isinstance(chat_id, int):
                    chat_id = None
                if session_id:
                    owner = websocket.cookies.get(
                        "detectives_owner"
                    ) or websocket.cookies.get("tech4city_owner")
                    if not owner:
                        await websocket.close(code=1008, reason="Owner missing")
                        return
                    try:
                        login = await app.state.telegram_manager.status(
                            str(session_id), owner
                        )
                    except (KeyError, TelegramLoginError):
                        await websocket.close(code=1008, reason="Session denied")
                        return
                    account_id = login.get("telegram_account_id")
                else:
                    account_id = command.get("account_id")
                    if not isinstance(account_id, int):
                        await connection.queue.put(
                            {
                                "type": "subscription.error",
                                "sequence": 0,
                                "data": {"detail": "account_id is required"},
                            }
                        )
                        continue
                await broker.subscribe(
                    connection,
                    account_id=account_id,
                    chat_id=chat_id,
                    telegram_session_id=str(session_id) if session_id else None,
                )
                await connection.queue.put(
                    {
                        "type": "subscription.ready",
                        "sequence": 0,
                        "account_id": account_id,
                        "chat_id": chat_id,
                        "telegram_session_id": session_id,
                        "data": {},
                    }
                )
        except (ValueError, WebSocketDisconnect):
            pass
        finally:
            sender.cancel()
            with suppress(
                asyncio.CancelledError,
                RuntimeError,
                WebSocketDisconnect,
            ):
                await sender
            await broker.disconnect(connection)

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

    def browser_owner(
        detectives_owner: str | None = Cookie(default=None),
        tech4city_owner: str | None = Cookie(default=None),
    ) -> str | None:
        """Return the canonical cookie, accepting the previous name during migration."""
        return detectives_owner or tech4city_owner

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

    async def publish_telegram_status(result: dict[str, Any]) -> None:
        await app.state.event_broker.publish(
            "telegram.logged_out"
            if result.get("status") == "logged_out"
            else "telegram.authorization.changed",
            telegram_session_id=result["session_id"],
            account_id=result.get("telegram_account_id"),
            data=result,
        )

    @app.post(
        "/telegram/login",
        response_model=TelegramLoginStatus,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_telegram_login(
        response: Response,
        owner_cookie: str | None = Depends(browser_owner),
    ) -> TelegramLoginStatus:
        import secrets

        owner = owner_cookie or secrets.token_urlsafe(32)
        result = await telegram_action(app.state.telegram_manager.create(owner))
        await publish_telegram_status(result)
        response.set_cookie(
            "detectives_owner",
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
        owner_cookie: str | None = Depends(browser_owner),
    ) -> TelegramLoginStatus:
        result = await telegram_action(
            app.state.telegram_manager.status(session_id, require_owner(owner_cookie))
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
        await publish_telegram_status(result)
        return TelegramLoginStatus(**result)

    @app.post(
        "/telegram/login/{session_id}/phone",
        response_model=TelegramLoginStatus,
    )
    async def submit_telegram_phone(
        session_id: str,
        body: LoginValue,
        response: Response,
        owner_cookie: str | None = Depends(browser_owner),
    ) -> TelegramLoginStatus:
        response.headers["Cache-Control"] = "no-store"
        return await submit_telegram_value(session_id, owner_cookie, "phone", body)

    @app.post(
        "/telegram/login/{session_id}/code",
        response_model=TelegramLoginStatus,
    )
    async def submit_telegram_code(
        session_id: str,
        body: LoginValue,
        response: Response,
        owner_cookie: str | None = Depends(browser_owner),
    ) -> TelegramLoginStatus:
        response.headers["Cache-Control"] = "no-store"
        return await submit_telegram_value(session_id, owner_cookie, "code", body)

    @app.post(
        "/telegram/login/{session_id}/password",
        response_model=TelegramLoginStatus,
    )
    async def submit_telegram_password(
        session_id: str,
        body: LoginValue,
        response: Response,
        owner_cookie: str | None = Depends(browser_owner),
    ) -> TelegramLoginStatus:
        response.headers["Cache-Control"] = "no-store"
        return await submit_telegram_value(
            session_id, owner_cookie, "password", body
        )

    @app.post(
        "/telegram/login/{session_id}/logout",
        response_model=TelegramLogoutStatus,
    )
    async def logout_telegram(
        session_id: str,
        response: Response,
        owner_cookie: str | None = Depends(browser_owner),
    ) -> TelegramLogoutStatus:
        result = await telegram_action(
            app.state.telegram_manager.logout(
                session_id, require_owner(owner_cookie)
            )
        )
        await publish_telegram_status(result)
        response.headers["Cache-Control"] = "no-store"
        return TelegramLogoutStatus(**result)

    async def owned_telegram_account(session_id: str, owner: str | None) -> int:
        return await telegram_action(
            app.state.telegram_manager.account_id(session_id, require_owner(owner))
        )

    async def owned_selected_telegram_chat(
        session_id: str, owner: str | None, chat_id: int
    ) -> int:
        owner_token = require_owner(owner)
        account_id = await telegram_action(
            app.state.telegram_manager.account_id(session_id, owner_token)
        )
        selected_chat_id = await telegram_action(
            app.state.telegram_manager.selected_chat_id(session_id, owner_token)
        )
        if chat_id != selected_chat_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Open this Telegram chat before reading its messages",
            )
        return account_id

    @app.get(
        "/telegram/login/{session_id}/chats",
        response_model=list[TelegramChatSummary],
    )
    async def list_owned_telegram_chats(
        session_id: str,
        response: Response,
        owner_cookie: str | None = Depends(browser_owner),
    ) -> list[TelegramChatSummary]:
        chats = await telegram_action(
            app.state.telegram_manager.list_chats(
                session_id, require_owner(owner_cookie)
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return [TelegramChatSummary(**chat) for chat in chats]

    @app.post(
        "/telegram/login/{session_id}/chats/{chat_id}/open",
        response_model=TelegramChatOpenStatus,
    )
    async def open_owned_telegram_chat(
        session_id: str,
        chat_id: int,
        response: Response,
        owner_cookie: str | None = Depends(browser_owner),
    ) -> TelegramChatOpenStatus:
        result = await telegram_action(
            app.state.telegram_manager.open_chat(
                session_id,
                require_owner(owner_cookie),
                chat_id,
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return TelegramChatOpenStatus(**result)

    @app.get(
        "/telegram/login/{session_id}/chats/{chat_id}/messages",
        response_model=list[StoredMessage],
    )
    async def list_owned_telegram_messages(
        session_id: str,
        chat_id: int,
        response: Response,
        owner_cookie: str | None = Depends(browser_owner),
    ) -> list[StoredMessage]:
        account_id = await owned_selected_telegram_chat(
            session_id, owner_cookie, chat_id
        )
        response.headers["Cache-Control"] = "no-store"
        return await app.state.repository.list_chat_messages(account_id, chat_id)

    @app.get(
        "/telegram/login/{session_id}/chats/{chat_id}/reports",
        response_model=list[MessageReport],
    )
    async def list_owned_telegram_reports(
        session_id: str,
        chat_id: int,
        response: Response,
        owner_cookie: str | None = Depends(browser_owner),
    ) -> list[MessageReport]:
        account_id = await owned_selected_telegram_chat(
            session_id, owner_cookie, chat_id
        )
        messages = await app.state.repository.list_chat_messages(account_id, chat_id)

        async def build_report(message: StoredMessage) -> MessageReport:
            key = (account_id, chat_id, message.message_id)
            analysis, job = await asyncio.gather(
                app.state.repository.get_latest_analysis(key),
                app.state.repository.get_job(key),
            )
            return MessageReport(
                message=message,
                analysis=analysis,
                analysis_job=job,
            )

        response.headers["Cache-Control"] = "no-store"
        return await asyncio.gather(*(build_report(message) for message in messages))

    @app.get(
        "/telegram/login/{session_id}/chats/{chat_id}/messages/{message_id}/report",
        response_model=MessageReport,
    )
    async def get_owned_telegram_chat_report(
        session_id: str,
        chat_id: int,
        message_id: int,
        response: Response,
        owner_cookie: str | None = Depends(browser_owner),
    ) -> MessageReport:
        account_id = await owned_selected_telegram_chat(
            session_id, owner_cookie, chat_id
        )
        key = (account_id, chat_id, message_id)
        message = await app.state.repository.get_message(key)
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="message not found",
            )
        job = await app.state.repository.get_job(key)
        response.headers["Cache-Control"] = "no-store"
        return MessageReport(
            message=message,
            analysis=await app.state.repository.get_latest_analysis(key),
            analysis_job=job,
        )

    @app.get(
        "/telegram/login/{session_id}/messages/{message_id}/report",
        response_model=MessageReport,
    )
    async def get_owned_telegram_report(
        session_id: str,
        message_id: int,
        response: Response,
        owner_cookie: str | None = Depends(browser_owner),
    ) -> MessageReport:
        account_id = await owned_telegram_account(session_id, owner_cookie)
        selected_chat_id = await telegram_action(
            app.state.telegram_manager.selected_chat_id(
                session_id, require_owner(owner_cookie)
            )
        )
        key = (account_id, selected_chat_id, message_id)
        message = await app.state.repository.get_message(key)
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="message not found",
            )
        job = await app.state.repository.get_job(key)
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
    layer3 = Layer3Analyzer(
        pipeline_version=settings.layer3_pipeline_version,
        model=settings.layer3_model,
    )
    if settings.analyzer == "layer3":
        return layer3
    layer1 = Layer1Analyzer(
        pipeline_version=settings.layer1_pipeline_version,
        model_dir=settings.layer1_model_dir,
    )
    if settings.analyzer == "layer1":
        return layer1
    layer2 = Layer2SkippedAnalyzer(
        pipeline_version=settings.layer2_pipeline_version,
    )
    layer1_layer2 = Layer1Layer2Analyzer(layer1, layer2)
    if settings.analyzer == "layer1-layer2":
        return layer1_layer2
    return Layer1Layer2Layer3Analyzer(layer1_layer2, layer3)


app = create_app()
