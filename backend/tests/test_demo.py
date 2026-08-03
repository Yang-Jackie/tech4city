from __future__ import annotations

from pathlib import Path

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


def test_built_frontend_assets_are_served(tmp_path: Path) -> None:
    frontend_dist = tmp_path / "dist"
    assets = frontend_dist / "assets"
    assets.mkdir(parents=True)
    (frontend_dist / "index.html").write_text(
        '<!doctype html><title>Detectives | Conversation review</title>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("window.detectives = true;", encoding="utf-8")
    (assets / "app.css").write_text(":root { color-scheme: dark; }", encoding="utf-8")

    with TestClient(
        create_demo_app(worker_enabled=False, frontend_dist_dir=frontend_dist)
    ) as client:
        page = client.get("/demo/")
        script = client.get("/demo/assets/app.js")
        styles = client.get("/demo/assets/app.css")

    assert page.status_code == 200
    assert "Conversation review" in page.text
    assert script.status_code == 200
    assert "detectives" in script.text
    assert styles.status_code == 200
    assert "color-scheme: dark" in styles.text


def test_missing_frontend_build_returns_actionable_response(tmp_path: Path) -> None:
    with TestClient(
        create_demo_app(
            worker_enabled=False,
            frontend_dist_dir=tmp_path / "missing",
        )
    ) as client:
        response = client.get("/demo/")

    assert response.status_code == 503
    assert "Frontend build required" in response.text
    assert "npm run build" in response.text


def test_frontend_source_excludes_demo_fixtures_and_aliases() -> None:
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (frontend_dir / "src").rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )

    assert not (frontend_dir / "src" / "data" / "mock-data.ts").exists()
    assert 'source: "mock"' not in source
    assert "conversation_name" not in source
    assert "getConfiguredAccountId" not in source
    assert "listBackendConversations" not in source
    assert "Meet Detectives" in source


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
