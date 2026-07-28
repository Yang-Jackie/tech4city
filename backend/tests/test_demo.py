from __future__ import annotations

from app.analyzer import analyze_message
from app.demo import create_demo_app as create_backend_demo_app
from app.repository import InMemoryRepository
from fastapi.testclient import TestClient


def create_demo_app(**options):
    options.setdefault("analyzer", analyze_message)
    options.setdefault("repository", InMemoryRepository())
    return create_backend_demo_app(**options)


def test_root_redirects_to_demo() -> None:
    with TestClient(create_demo_app(worker_enabled=False)) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/demo/"


def test_demo_frontend_assets_are_served() -> None:
    with TestClient(create_demo_app(worker_enabled=False)) as client:
        page = client.get("/demo/")
        script = client.get("/demo/app.js")
        styles = client.get("/demo/styles.css")

    assert page.status_code == 200
    assert "Conversation review" in page.text
    assert 'id="chat-list"' in page.text
    assert 'id="view-analysis"' in page.text
    assert script.status_code == 200
    assert "No approved explanation is available for this output." in script.text
    assert "Analyzer version" in script.text
    assert "minimumFractionDigits: 2" in script.text
    assert "Boolean(state.telegramSessionId)" in script.text
    assert "chatListRequestId" in script.text
    assert '"Cancel login"' in script.text
    assert styles.status_code == 200
    assert "--primary: oklch(" in styles.text
    assert "279.1" not in styles.text


def test_demo_and_backend_share_one_application() -> None:
    with TestClient(create_demo_app(worker_enabled=False)) as client:
        created = client.post(
            "/messages",
            json={
                "telegram_account_id": 100,
                "chat_id": 200,
                "message_id": 1,
                "sender_id": 100,
                "text": "Sanitized outgoing message",
                "sent_at": "2026-07-20T10:00:00Z",
            },
        )
        chats = client.get("/chats", params={"telegram_account_id": 100})
        conversation = client.get(
            "/chats/200/messages",
            params={"telegram_account_id": 100},
        )

    assert created.status_code == 202
    assert chats.status_code == 200
    assert chats.json()[0]["chat_id"] == 200
    assert conversation.status_code == 200
    assert conversation.json()[0]["text"] == "Sanitized outgoing message"
