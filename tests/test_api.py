from __future__ import annotations

from fastapi.testclient import TestClient

from server.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["mode"] in {"demo", "live"}
    assert "asr" in data


def test_index_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "ئاينۇر" in response.text


def test_turn_with_text():
    response = client.post(
        "/api/turn", data={"text": "سىز كىم؟", "session_id": "api-test"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reply_ug"]
    assert data["category"] in {"normal", "medical", "emergency", "religion", "policy", "unclear"}


def test_turn_requires_input():
    response = client.post("/api/turn", data={"session_id": "api-test"})
    assert response.status_code == 400


def test_tts_requires_text():
    response = client.post("/api/tts", json={})
    assert response.status_code == 400


def test_settings_roundtrip():
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert "llm_api_key" in response.json()

    saved = client.post("/api/settings", json={"daily_limit": 42})
    assert saved.status_code == 200
    assert saved.json()["daily_limit"] == 42
    client.post("/api/settings", json={"daily_limit": 60})


def test_profile_roundtrip():
    saved = client.post("/api/profile", json={"title": "ئاپا", "city": "乌鲁木齐"})
    assert saved.status_code == 200
    assert saved.json()["title"] == "ئاپا"

    reset = client.post("/api/profile/reset")
    assert reset.status_code == 200


def test_failures_endpoint():
    response = client.get("/api/failures?limit=5")
    assert response.status_code == 200
    assert "items" in response.json()


def test_export():
    response = client.get("/api/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
