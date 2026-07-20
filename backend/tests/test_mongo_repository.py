from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient

from app.config import Settings
from app.main import create_app
from app.models import AnalysisResult, MessageCreate
from app.mongo_repository import MongoRepository
from app.repository import MessageConflictError, message_key

MONGODB_TEST_URI = os.getenv("MONGODB_TEST_URI")


@pytest.mark.skipif(
    not MONGODB_TEST_URI,
    reason="set MONGODB_TEST_URI to run the live MongoDB persistence test",
)
def test_mongodb_persists_messages_jobs_and_analysis_across_clients() -> None:
    async def scenario() -> None:
        database_name = f"tech4city_test_{uuid4().hex}"
        message = MessageCreate(
            telegram_account_id=100,
            chat_id=200,
            message_id=300,
            sender_id=400,
            text="Sanitized persistence test",
            sent_at=datetime(2026, 7, 16, tzinfo=UTC),
        )
        key = message_key(message)
        first = MongoRepository(MONGODB_TEST_URI or "", database_name)
        second: MongoRepository | None = None
        first_closed = False
        try:
            await first.initialize()
            stored, created = await first.ingest_message(message)
            job = await first.ensure_job(key)
            assert created is True
            assert stored.text == message.text
            assert job.status == "pending"
            await first.close()
            first_closed = True

            second = MongoRepository(MONGODB_TEST_URI or "", database_name)
            await second.initialize()
            persisted = await second.get_message(key)
            claimed = await second.claim_next_job()
            assert persisted is not None
            assert persisted.text == message.text
            assert claimed is not None
            assert claimed.status == "processing"
            assert claimed.attempts == 1

            analysis = AnalysisResult(
                harmful=False,
                bully_probability=0,
                severity="none",
                categories=[],
                explanation="Sanitized fake result",
                pipeline_version="test-v1",
            )
            completed = await second.complete_job(key, analysis)
            latest = await second.get_latest_analysis(key)
            assert completed.status == "completed"
            assert latest == analysis

            duplicate, duplicate_created = await second.ingest_message(message)
            assert duplicate_created is False
            assert duplicate.received_at == persisted.received_at

            changed = message.model_copy(update={"text": "Different sanitized text"})
            with pytest.raises(MessageConflictError):
                await second.ingest_message(changed)
        finally:
            cleanup_client = AsyncMongoClient(MONGODB_TEST_URI or "")
            try:
                await cleanup_client.drop_database(database_name)
            finally:
                await cleanup_client.close()
            if not first_closed:
                await first.close()
            if second is not None:
                await second.close()

    asyncio.run(scenario())


@pytest.mark.skipif(
    not MONGODB_TEST_URI,
    reason="set MONGODB_TEST_URI to run the live MongoDB persistence test",
)
def test_fastapi_reports_survive_application_restart() -> None:
    database_name = f"tech4city_api_test_{uuid4().hex}"
    settings = Settings(
        storage="mongodb",
        mongodb_uri=MONGODB_TEST_URI,
        mongodb_database=database_name,
        worker_enabled=False,
    )
    payload = {
        "telegram_account_id": 101,
        "chat_id": 201,
        "message_id": 301,
        "sender_id": 401,
        "text": "Sanitized API persistence test",
        "sent_at": "2026-07-16T00:00:00Z",
    }
    try:
        with TestClient(create_app(settings=settings)) as client:
            created = client.post("/messages", json=payload)
            processed = client.post("/internal/worker/run-once")
        assert created.status_code == 202
        assert processed.json()["analysis_job"]["status"] == "completed"

        with TestClient(create_app(settings=settings)) as restarted_client:
            health = restarted_client.get("/health")
            report = restarted_client.get(
                "/messages/301/report",
                params={"telegram_account_id": 101, "chat_id": 201},
            )
        assert health.json()["storage"] == "mongodb"
        assert report.status_code == 200
        assert report.json()["message"]["text"] == payload["text"]
        assert report.json()["analysis_job"]["status"] == "completed"
        assert report.json()["analysis"]["pipeline_version"] == "fake-v1"
    finally:

        async def cleanup() -> None:
            client = AsyncMongoClient(MONGODB_TEST_URI or "")
            try:
                await client.drop_database(database_name)
            finally:
                await client.close()

        asyncio.run(cleanup())
