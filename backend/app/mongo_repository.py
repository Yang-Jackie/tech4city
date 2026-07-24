"""MongoDB implementation of the backend persistence contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from .models import (
    AnalysisJob,
    AnalysisResult,
    ChatSummary,
    MessageCreate,
    StoredMessage,
)
from .repository import (
    MessageConflictError,
    MessageKey,
    job_id,
    message_key,
)


class MongoRepository:
    """Persist backend state in one MongoDB database."""

    storage_name = "mongodb"

    def __init__(self, uri: str, database_name: str) -> None:
        self._client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
            uri,
            appname="tech4city-backend",
            serverSelectionTimeoutMS=5_000,
            tz_aware=True,
        )
        self._database = self._client[database_name]
        self._messages = self._database["messages"]
        self._jobs = self._database["analysis_jobs"]
        self._analysis_runs = self._database["analysis_runs"]

    async def initialize(self) -> None:
        await self.ping()
        await self._messages.create_index(
            [
                ("telegram_account_id", ASCENDING),
                ("chat_id", ASCENDING),
                ("message_id", ASCENDING),
            ],
            unique=True,
            name="message_identity_unique",
        )
        await self._messages.create_index(
            [
                ("telegram_account_id", ASCENDING),
                ("chat_id", ASCENDING),
                ("sent_at", ASCENDING),
                ("message_id", ASCENDING),
            ],
            name="conversation_chronological",
        )
        await self._jobs.create_index(
            [("status", ASCENDING), ("created_at", ASCENDING)],
            name="pending_jobs_fifo",
        )
        await self._analysis_runs.create_index(
            [
                ("telegram_account_id", ASCENDING),
                ("chat_id", ASCENDING),
                ("message_id", ASCENDING),
                ("completed_at", DESCENDING),
            ],
            name="latest_analysis_for_message",
        )

    async def close(self) -> None:
        await self._client.close()

    async def ping(self) -> None:
        await self._client.admin.command("ping")

    async def ingest_message(
        self, message: MessageCreate
    ) -> tuple[StoredMessage, bool]:
        stored = StoredMessage(
            **message.model_dump(),
            received_at=datetime.now(UTC),
        )
        document = stored.model_dump(mode="python")
        try:
            await self._messages.insert_one(document)
            return stored, True
        except DuplicateKeyError:
            existing_document = await self._messages.find_one(
                key_filter(message_key(message))
            )
            if existing_document is None:
                raise
            existing = stored_message_from_document(existing_document)
            if existing.model_dump(exclude={"received_at"}) != message.model_dump():
                raise MessageConflictError from None
            return existing, False

    async def ensure_job(self, key: MessageKey) -> AnalysisJob:
        account_id, chat_id, telegram_message_id = key
        identifier = job_id(key)
        document = await self._jobs.find_one_and_update(
            {"_id": identifier},
            {
                "$setOnInsert": {
                    "job_id": identifier,
                    "telegram_account_id": account_id,
                    "chat_id": chat_id,
                    "message_id": telegram_message_id,
                    "status": "pending",
                    "attempts": 0,
                    "error": None,
                    "created_at": datetime.now(UTC),
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return analysis_job_from_document(document)

    async def get_job(self, key: MessageKey) -> AnalysisJob | None:
        document = await self._jobs.find_one({"_id": job_id(key)})
        return analysis_job_from_document(document) if document is not None else None

    async def claim_next_job(self) -> AnalysisJob | None:
        document = await self._jobs.find_one_and_update(
            {"status": "pending"},
            {
                "$set": {"status": "processing", "error": None},
                "$inc": {"attempts": 1},
            },
            sort=[("created_at", ASCENDING), ("_id", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )
        return analysis_job_from_document(document) if document is not None else None

    async def complete_job(
        self, key: MessageKey, analysis: AnalysisResult
    ) -> AnalysisJob:
        job = await self.get_job(key)
        if job is None:
            raise KeyError(job_id(key))
        run_identifier = f"{job.job_id}:{job.attempts}"
        await self._analysis_runs.update_one(
            {"_id": run_identifier},
            {
                "$setOnInsert": {
                    "telegram_account_id": key[0],
                    "chat_id": key[1],
                    "message_id": key[2],
                    "job_id": job.job_id,
                    "attempt": job.attempts,
                    "result": analysis.model_dump(mode="python"),
                    "completed_at": datetime.now(UTC),
                }
            },
            upsert=True,
        )
        document = await self._jobs.find_one_and_update(
            {"_id": job.job_id},
            {"$set": {"status": "completed", "error": None}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            raise KeyError(job.job_id)
        return analysis_job_from_document(document)

    async def fail_job(self, key: MessageKey, error: str) -> AnalysisJob:
        document = await self._jobs.find_one_and_update(
            {"_id": job_id(key)},
            {"$set": {"status": "failed", "error": error}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            raise KeyError(job_id(key))
        return analysis_job_from_document(document)

    async def get_message(self, key: MessageKey) -> StoredMessage | None:
        document = await self._messages.find_one(key_filter(key))
        return stored_message_from_document(document) if document is not None else None

    async def list_chats(self, telegram_account_id: int) -> list[ChatSummary]:
        cursor = await self._messages.aggregate(
            [
                {"$match": {"telegram_account_id": telegram_account_id}},
                {"$sort": {"sent_at": 1, "message_id": 1}},
                {
                    "$group": {
                        "_id": "$chat_id",
                        "message_count": {"$sum": 1},
                        "sender_ids": {"$addToSet": "$sender_id"},
                        "first_message_at": {"$first": "$sent_at"},
                        "last_message_at": {"$last": "$sent_at"},
                        "last_message_preview": {"$last": "$text"},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "chat_id": "$_id",
                        "message_count": 1,
                        "participant_count": {"$size": "$sender_ids"},
                        "first_message_at": 1,
                        "last_message_at": 1,
                        "last_message_preview": 1,
                    }
                },
                {"$sort": {"last_message_at": -1, "chat_id": -1}},
            ]
        )
        documents = await cursor.to_list(length=None)
        return [ChatSummary.model_validate(document) for document in documents]

    async def list_chat_messages(
        self, telegram_account_id: int, chat_id: int
    ) -> list[StoredMessage]:
        cursor = self._messages.find(
            {"telegram_account_id": telegram_account_id, "chat_id": chat_id}
        ).sort([("sent_at", ASCENDING), ("message_id", ASCENDING)])
        documents = await cursor.to_list(length=None)
        return [stored_message_from_document(document) for document in documents]

    async def list_context_before(self, message: StoredMessage) -> list[StoredMessage]:
        cursor = self._messages.find(
            {
                "telegram_account_id": message.telegram_account_id,
                "chat_id": message.chat_id,
                "$or": [
                    {"sent_at": {"$lt": message.sent_at}},
                    {
                        "sent_at": message.sent_at,
                        "message_id": {"$lt": message.message_id},
                    },
                ],
            }
        ).sort([("sent_at", ASCENDING), ("message_id", ASCENDING)])
        documents = await cursor.to_list(length=None)
        return [stored_message_from_document(document) for document in documents]

    async def get_latest_analysis(self, key: MessageKey) -> AnalysisResult | None:
        document = await self._analysis_runs.find_one(
            key_filter(key),
            sort=[("completed_at", DESCENDING)],
        )
        if document is None:
            return None
        return AnalysisResult.model_validate(document["result"])


def key_filter(key: MessageKey) -> dict[str, int]:
    return {
        "telegram_account_id": key[0],
        "chat_id": key[1],
        "message_id": key[2],
    }


def stored_message_from_document(document: dict[str, Any]) -> StoredMessage:
    return StoredMessage.model_validate(
        {key: value for key, value in document.items() if key != "_id"}
    )


def analysis_job_from_document(document: dict[str, Any]) -> AnalysisJob:
    return AnalysisJob.model_validate(
        {
            key: document.get(key)
            for key in (
                "job_id",
                "telegram_account_id",
                "chat_id",
                "message_id",
                "status",
                "attempts",
                "error",
            )
        }
    )
