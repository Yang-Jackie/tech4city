from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.analyzer import Layer1Analyzer
from app.main import create_app


def message_payload(
    *,
    message_id: int = 1,
    text: str = "A test message",
    sent_at: str = "2026-07-13T10:00:00Z",
) -> dict[str, object]:
    return {
        "telegram_account_id": 100,
        "chat_id": 200,
        "message_id": message_id,
        "sender_id": 300,
        "text": text,
        "sent_at": sent_at,
    }


def test_health() -> None:
    with TestClient(create_app(worker_enabled=False)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "storage": "memory",
        "analyzer": "fake-v1",
    }


def test_ingest_and_list_messages_in_chronological_order() -> None:
    with TestClient(create_app(worker_enabled=False)) as client:
        later = client.post(
            "/messages",
            json=message_payload(
                message_id=2,
                text="Second",
                sent_at="2026-07-13T10:01:00Z",
            ),
        )
        earlier = client.post(
            "/messages",
            json=message_payload(
                message_id=1,
                text="First",
                sent_at="2026-07-13T10:00:00Z",
            ),
        )
        conversation = client.get(
            "/chats/200/messages",
            params={"telegram_account_id": 100},
        )

    assert later.status_code == 202
    assert earlier.status_code == 202
    assert earlier.json()["analysis"] is None
    assert earlier.json()["analysis_job"]["status"] == "pending"
    assert conversation.status_code == 200
    assert [message["text"] for message in conversation.json()] == ["First", "Second"]


def test_duplicate_message_is_idempotent() -> None:
    payload = message_payload()

    with TestClient(create_app(worker_enabled=False)) as client:
        created = client.post("/messages", json=payload)
        duplicate = client.post("/messages", json=payload)
        conversation = client.get(
            "/chats/200/messages",
            params={"telegram_account_id": 100},
        )

    assert created.status_code == 202
    assert created.json()["status"] == "created"
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    assert len(conversation.json()) == 1


def test_reused_message_id_with_different_content_conflicts() -> None:
    with TestClient(create_app(worker_enabled=False)) as client:
        client.post("/messages", json=message_payload(text="Original"))
        response = client.post("/messages", json=message_payload(text="Changed"))

    assert response.status_code == 409


def test_invalid_message_is_rejected() -> None:
    payload = message_payload(text=" ")
    payload["unexpected"] = True

    with TestClient(create_app(worker_enabled=False)) as client:
        response = client.post("/messages", json=payload)

    assert response.status_code == 422


def test_worker_completes_pending_analysis() -> None:
    with TestClient(create_app(worker_enabled=False)) as client:
        client.post("/messages", json=message_payload())
        pending_report = client.get(
            "/messages/1/report",
            params={"telegram_account_id": 100, "chat_id": 200},
        )
        worker_response = client.post("/internal/worker/run-once")
        completed_report = client.get(
            "/messages/1/report",
            params={"telegram_account_id": 100, "chat_id": 200},
        )

    assert pending_report.status_code == 200
    assert pending_report.json()["analysis"] is None
    assert pending_report.json()["analysis_job"]["status"] == "pending"
    assert worker_response.status_code == 200
    assert worker_response.json()["status"] == "processed"
    assert worker_response.json()["analysis_job"]["attempts"] == 1
    assert completed_report.json()["message"]["text"] == "A test message"
    assert completed_report.json()["analysis_job"]["status"] == "completed"
    assert completed_report.json()["analysis"] == {
        "harmful": False,
        "bully_probability": 0.0,
        "severity": "none",
        "categories": [],
        "explanation": "Fake analyzer only; no model evaluation was performed.",
        "pipeline_version": "fake-v1",
        "layer1": None,
    }


def test_worker_is_idle_when_no_jobs_are_queued() -> None:
    with TestClient(create_app(worker_enabled=False)) as client:
        response = client.post("/internal/worker/run-once")

    assert response.status_code == 200
    assert response.json() == {
        "status": "idle",
        "analysis_job": None,
        "analysis": None,
    }


def test_worker_processes_jobs_in_ingestion_order() -> None:
    with TestClient(create_app(worker_enabled=False)) as client:
        client.post("/messages", json=message_payload(message_id=1))
        client.post("/messages", json=message_payload(message_id=2))
        processed = client.post("/internal/worker/run-once")
        second_report = client.get(
            "/messages/2/report",
            params={"telegram_account_id": 100, "chat_id": 200},
        )

    assert processed.json()["analysis_job"]["message_id"] == 1
    assert second_report.json()["analysis_job"]["status"] == "pending"


def test_worker_records_a_safe_failure() -> None:
    async def failing_analyzer(_message, _context):
        raise RuntimeError("private provider error")

    with TestClient(
        create_app(analyzer=failing_analyzer, worker_enabled=False)
    ) as client:
        client.post("/messages", json=message_payload())
        processed = client.post("/internal/worker/run-once")
        report = client.get(
            "/messages/1/report",
            params={"telegram_account_id": 100, "chat_id": 200},
        )

    assert processed.json()["analysis"] is None
    assert report.json()["analysis_job"] == {
        "job_id": "100:200:1",
        "telegram_account_id": 100,
        "chat_id": 200,
        "message_id": 1,
        "status": "failed",
        "attempts": 1,
        "error": "analysis failed",
    }


def test_missing_message_report_returns_not_found() -> None:
    with TestClient(create_app(worker_enabled=False)) as client:
        response = client.get(
            "/messages/999/report",
            params={"telegram_account_id": 100, "chat_id": 200},
        )

    assert response.status_code == 404


def test_background_worker_processes_new_messages_automatically() -> None:
    with TestClient(create_app()) as client:
        created = client.post("/messages", json=message_payload())
        deadline = time.monotonic() + 2
        while True:
            report = client.get(
                "/messages/1/report",
                params={"telegram_account_id": 100, "chat_id": 200},
            )
            if report.json()["analysis_job"]["status"] == "completed":
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)

    assert created.status_code == 202
    assert report.status_code == 200
    assert report.json()["analysis"]["pipeline_version"] == "fake-v1"


class StubLayer1:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def predict(self, text: str) -> dict[str, object]:
        self.calls.append(text)
        return {
            "status": "need_to_investigate",
            "raw_label": "uncertain",
            "normal_score": 0.25,
            "bully_score": 0.75,
        }


def test_background_worker_persists_layer1_result() -> None:
    layer = StubLayer1()
    analyzer = Layer1Analyzer(
        pipeline_version="layer1-api-test-v1",
        layer_factory=lambda: layer,
    )
    with TestClient(create_app(analyzer=analyzer)) as client:
        created = client.post("/messages", json=message_payload())
        deadline = time.monotonic() + 2
        while True:
            report = client.get(
                "/messages/1/report",
                params={"telegram_account_id": 100, "chat_id": 200},
            )
            if report.json()["analysis_job"]["status"] == "completed":
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)

    analysis = report.json()["analysis"]
    assert created.status_code == 202
    assert report.json()["analysis_job"]["status"] == "completed"
    assert analysis == {
        "harmful": None,
        "bully_probability": None,
        "severity": None,
        "categories": None,
        "explanation": None,
        "pipeline_version": "layer1-api-test-v1",
        "layer1": {
            "status": "need_to_investigate",
            "raw_label": "uncertain",
            "normal_score": 0.25,
            "bully_score": 0.75,
        },
    }
    assert layer.calls == ["A test message"]
