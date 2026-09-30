"""Listado de modelos por proveedor y edición de conexiones (T-006)."""

import httpx
from sqlalchemy import select

from conftest import login

API = "/api/v1"


def test_list_models_for_new_mock_connection(client) -> None:
    headers = login(client)
    response = client.post(f"{API}/ai/models", json={"provider": "MOCK"}, headers=headers)
    assert response.status_code == 200
    ids = [m["id"] for m in response.json()]
    assert ids[0] == "mock" and "mock-fail-quota" in ids


def test_list_models_requires_key_for_real_providers(client) -> None:
    headers = login(client)
    response = client.post(f"{API}/ai/models", json={"provider": "OPENAI"}, headers=headers)
    assert response.status_code == 422


def test_openai_listing_keeps_only_chat_models(client, monkeypatch) -> None:
    payload = {
        "data": [
            {"id": "gpt-4o-mini", "created": 3},
            {"id": "text-embedding-3-small", "created": 9},
            {"id": "gpt-4o-realtime-preview", "created": 8},
            {"id": "whisper-1", "created": 7},
            {"id": "o3-mini", "created": 5},
            {"id": "dall-e-3", "created": 6},
        ]
    }

    def fake_request(method, url, **kwargs):
        assert url.endswith("/models")
        assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
        return httpx.Response(200, json=payload, request=httpx.Request(method, url))

    monkeypatch.setattr("app.ai.providers.httpx.request", fake_request)
    headers = login(client)
    response = client.post(
        f"{API}/ai/models", json={"provider": "OPENAI", "apiKey": "sk-test"}, headers=headers
    )
    assert response.status_code == 200
    assert [m["id"] for m in response.json()] == ["o3-mini", "gpt-4o-mini"]


def test_anthropic_listing_follows_pagination(client, monkeypatch) -> None:
    pages = [
        {"data": [{"id": "claude-a", "display_name": "Claude A"}], "has_more": True, "last_id": "claude-a"},
        {"data": [{"id": "claude-b", "display_name": "Claude B"}], "has_more": False, "last_id": "claude-b"},
    ]
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(kwargs.get("params"))
        return httpx.Response(200, json=pages[len(calls) - 1], request=httpx.Request(method, url))

    monkeypatch.setattr("app.ai.providers.httpx.request", fake_request)
    headers = login(client)
    response = client.post(
        f"{API}/ai/models", json={"provider": "ANTHROPIC", "apiKey": "sk-ant"}, headers=headers
    )
    assert [m["label"] for m in response.json()] == ["Claude A", "Claude B"]
    assert calls[1]["after_id"] == "claude-a"


def test_invalid_key_returns_readable_error(client, monkeypatch) -> None:
    def fake_request(method, url, **kwargs):
        return httpx.Response(401, text="bad key", request=httpx.Request(method, url))

    monkeypatch.setattr("app.ai.providers.httpx.request", fake_request)
    headers = login(client)
    response = client.post(
        f"{API}/ai/models", json={"provider": "GEMINI", "apiKey": "bad"}, headers=headers
    )
    assert response.status_code == 422
    assert "Credencial inválida" in response.json()["detail"]


def test_models_for_existing_connection_and_edit(client) -> None:
    headers = login(client)
    connection = client.post(
        f"{API}/ai/connections", json={"provider": "MOCK", "name": "Sim"}, headers=headers
    ).json()
    listed = client.get(f"{API}/ai/connections/{connection['id']}/models", headers=headers)
    assert listed.status_code == 200 and listed.json()

    edited = client.patch(
        f"{API}/ai/connections/{connection['id']}",
        json={"name": "Renombrada", "model": "mock-fail-down"},
        headers=headers,
    ).json()
    assert edited["name"] == "Renombrada"
    assert edited["model"] == "mock-fail-down"
    # Cambiar el modelo vuelve a probar la conexión.
    assert edited["test"]["ok"] is False
    assert edited["status"] == "PROVIDER_DOWN"

    other = login(client, "otra@example.com")
    assert client.get(f"{API}/ai/connections/{connection['id']}/models", headers=other).status_code == 404


def test_usage_events_record_the_model(client) -> None:
    from app.ai.models import AIUsageEvent
    from app.db import SessionLocal

    headers = login(client)
    client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers)
    client.post(f"{API}/ai/connections", json={"provider": "MOCK", "name": "Sim"}, headers=headers)
    client.post(f"{API}/classes", headers=headers)

    with SessionLocal() as db:
        models = set(db.scalars(select(AIUsageEvent.model)).all())
    assert models == {"mock"}
