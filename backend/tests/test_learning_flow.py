from conftest import login

API = "/api/v1"


def _setup(client, *, model: str = "mock", email: str = "roberto@example.com") -> dict:
    headers = login(client, email)
    assert client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers).status_code == 200
    response = client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": model, "priority": 1},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return headers


def test_me_requires_auth(client) -> None:
    assert client.get(f"{API}/me").status_code == 401


def test_dev_login_creates_account_and_profile(client) -> None:
    headers = login(client)
    me = client.get(f"{API}/me", headers=headers).json()
    assert me["account"]["email"] == "roberto@example.com"
    assert me["studyProfile"]["operationalLevel"] is None
    assert me["levels"]["available"] == ["A1"]


def test_level_not_available_is_rejected(client) -> None:
    headers = login(client)
    response = client.put(f"{API}/me/level", json={"level": "C1"}, headers=headers)
    assert response.status_code == 422


def test_api_key_is_never_returned(client, monkeypatch) -> None:
    import httpx

    def offline(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.ai.providers.httpx.request", offline)
    headers = login(client)
    response = client.post(
        f"{API}/ai/connections",
        json={"provider": "OPENAI", "name": "OpenAI", "apiKey": "sk-test-1234567890ABCD"},
        headers=headers,
    )
    # La prueba inmediata falla (sin red) pero la conexión queda creada.
    assert response.status_code == 201
    assert response.json()["status"] == "NETWORK_ERROR"
    body = response.text
    assert "sk-test-1234567890ABCD" not in body
    assert response.json()["credentialHint"].endswith("ABCD")


def test_full_class_flow(client) -> None:
    headers = _setup(client)

    created = client.post(f"{API}/classes", headers=headers)
    assert created.status_code == 201, created.text
    klass = created.json()
    assert klass["status"] == "READY"
    assert len(klass["exercises"]) >= 3
    # La answer key no se expone antes de corregir.
    assert "acceptedAnswers" not in created.text

    first = klass["exercises"][0]
    saved = client.put(
        f"{API}/classes/{klass['id']}/answers/{first['id']}",
        json={"answer": "algo"},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["status"] == "IN_PROGRESS"

    reloaded = client.get(f"{API}/classes/{klass['id']}", headers=headers).json()
    assert reloaded["exercises"][0]["answer"] == "algo"

    submitted = client.post(f"{API}/classes/{klass['id']}/submit", json={}, headers=headers)
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()
    assert result["status"] == "COMPLETED"
    assert result["score"] is not None
    assert all(e["result"] is not None for e in result["exercises"])

    progress = client.get(f"{API}/progress", headers=headers).json()
    assert progress["skillsPracticed"] >= 1

    retaken = client.post(f"{API}/classes/{klass['id']}/retake", headers=headers).json()
    assert retaken["status"] == "READY"
    assert retaken["currentAttempt"] == 2
    assert retaken["history"][0]["attempt"] == 1


def test_all_providers_down_keeps_answers_and_recovers(client) -> None:
    headers = _setup(client)
    klass = client.post(f"{API}/classes", headers=headers).json()
    writing = next((e for e in klass["exercises"] if e["type"] == "short_writing"), None)
    answers = {str(e["id"]): "Every morning I get up early and I drink coffee with my family." for e in klass["exercises"]}

    # Ahora el único proveedor queda caído.
    connections = client.get(f"{API}/ai/connections", headers=headers).json()
    client.patch(
        f"{API}/ai/connections/{connections[0]['id']}",
        json={"model": "mock-fail-quota"},
        headers=headers,
    )

    submitted = client.post(
        f"{API}/classes/{klass['id']}/submit", json={"answers": answers}, headers=headers
    ).json()
    needs_ai = writing is not None or any(e["type"] in ("fill_blank", "rewrite") for e in klass["exercises"])
    if needs_ai:
        assert submitted["status"] == "AWAITING_EVALUATION"
        assert submitted["notice"]
        # Las respuestas quedaron guardadas.
        assert all(e["answer"] for e in submitted["exercises"])

        # Vuelve la IA: agregar un proveedor sano y procesar pendientes.
        client.post(
            f"{API}/ai/connections",
            json={"provider": "MOCK", "name": "Backup", "model": "mock", "priority": 2},
            headers=headers,
        )
        processed = client.post(f"{API}/classes/process-pending", headers=headers).json()
        assert processed["completed"] == 1
        final = client.get(f"{API}/classes/{klass['id']}", headers=headers).json()
        assert final["status"] == "COMPLETED"


def test_failover_uses_next_connection(client) -> None:
    headers = _setup(client, model="mock-fail-down")
    client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Backup", "model": "mock", "priority": 5},
        headers=headers,
    )
    klass = client.post(f"{API}/classes", headers=headers).json()
    assert klass["status"] == "READY"
    assert klass["generatedBy"] == "Backup"
    assert klass["generationAi"] == {
        "connectionId": klass["generationAi"]["connectionId"],
        "connection": "Backup",
        "provider": "MOCK",
        "providerLabel": "Simulado (solo desarrollo)",
        "model": "mock",
    }

    active = client.get(f"{API}/ai/active", headers=headers).json()
    assert active["default"]["connection"] == "Backup"
    assert active["default"]["model"] == "mock"

    connections = client.get(f"{API}/ai/connections", headers=headers).json()
    broken = next(c for c in connections if c["name"] == "Simulado")
    assert broken["status"] == "PROVIDER_DOWN"
    assert broken["usable"] is False


def test_generation_failure_is_persisted_and_retryable(client) -> None:
    headers = _setup(client, model="mock-fail-quota")
    klass = client.post(f"{API}/classes", headers=headers).json()
    assert klass["status"] == "GENERATION_FAILED"
    assert klass["generationError"]

    client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Backup", "model": "mock", "priority": 5},
        headers=headers,
    )
    retried = client.post(f"{API}/classes/{klass['id']}/retry-generation", headers=headers).json()
    assert retried["status"] == "READY"


def test_classes_are_isolated_between_accounts(client) -> None:
    headers_a = _setup(client, email="a@example.com")
    klass = client.post(f"{API}/classes", headers=headers_a).json()
    headers_b = _setup(client, email="b@example.com")
    assert client.get(f"{API}/classes/{klass['id']}", headers=headers_b).status_code == 404
    connections_a = client.get(f"{API}/ai/connections", headers=headers_a).json()
    assert client.delete(
        f"{API}/ai/connections/{connections_a[0]['id']}", headers=headers_b
    ).status_code == 404


def test_platform_connections_only_for_platform_owner(client) -> None:
    headers = login(client, "user@example.com")
    response = client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Plataforma", "scope": "platform"},
        headers=headers,
    )
    assert response.status_code == 403

    owner = login(client, "owner@example.com")
    assert client.get(f"{API}/me", headers=owner).json()["account"]["isPlatformOwner"]
    response = client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Plataforma", "scope": "platform"},
        headers=owner,
    )
    assert response.status_code == 201
    # Un usuario común sin conexiones propias puede usar la de plataforma.
    client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers)
    klass = client.post(f"{API}/classes", headers=headers).json()
    assert klass["status"] == "READY"
