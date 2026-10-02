"""T-006: gestión de IA de plataforma, límites de consumo y registro de uso."""

import pytest
from conftest import login

API = "/api/v1"
OWNER = "owner@example.com"


def _platform_connection(client, owner_headers, **extra) -> dict:
    response = client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Plataforma", "scope": "platform", "priority": 1, **extra},
        headers=owner_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def membership(monkeypatch):
    """Simula T-004: una membresía que habilita la IA de la plataforma a cualquier alumno.

    Desde T-003 los alumnos usan solo sus conexiones propias; estos tests cubren los límites
    de consumo, que aplican cuando la plataforma sí está habilitada.
    """
    monkeypatch.setattr("app.ai.service.ai_sources", lambda db, account: (True, True))


def _student(client, email: str) -> dict:
    headers = login(client, email)
    assert client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers).status_code == 200
    return headers


def test_overview_is_only_for_platform_owner(client) -> None:
    user = login(client, "user@example.com")
    assert client.get(f"{API}/platform/overview", headers=user).status_code == 403
    owner = login(client, OWNER)
    response = client.get(f"{API}/platform/overview", headers=owner)
    assert response.status_code == 200
    body = response.json()
    assert len(body["daily"]) == 14
    assert body["accounts"] == 2


def test_limits_only_allowed_on_platform_connections(client) -> None:
    user = login(client, "user@example.com")
    response = client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Mía", "dailyRequestLimit": 5},
        headers=user,
    )
    assert response.status_code == 422


def test_per_account_limit_blocks_only_that_account(client, membership) -> None:
    owner = login(client, OWNER)
    connection = _platform_connection(client, owner, perAccountDailyLimit=1)
    assert connection["perAccountDailyLimit"] == 1

    alice = _student(client, "alice@example.com")
    first = client.post(f"{API}/classes", headers=alice).json()
    assert first["status"] == "READY"
    second = client.post(f"{API}/classes", headers=alice).json()
    assert second["status"] == "GENERATION_FAILED"
    assert "límite" in second["generationError"]

    # Otra cuenta todavía tiene cupo.
    bob = _student(client, "bob@example.com")
    assert client.post(f"{API}/classes", headers=bob).json()["status"] == "READY"

    # El límite no marca la conexión como caída.
    listed = client.get(f"{API}/ai/connections?scope=platform", headers=owner).json()[0]
    assert listed["status"] == "AVAILABLE"
    assert listed["usage24h"] == 2


def test_total_limit_falls_back_to_next_connection(client, membership) -> None:
    owner = login(client, OWNER)
    _platform_connection(client, owner, dailyRequestLimit=1)
    client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Respaldo", "scope": "platform", "priority": 2},
        headers=owner,
    )
    student = _student(client, "alice@example.com")
    assert client.post(f"{API}/classes", headers=student).json()["generatedBy"] == "Plataforma"
    assert client.post(f"{API}/classes", headers=student).json()["generatedBy"] == "Respaldo"


def test_limit_can_be_changed_and_cleared(client) -> None:
    owner = login(client, OWNER)
    connection = _platform_connection(client, owner, dailyRequestLimit=10)
    updated = client.patch(
        f"{API}/ai/connections/{connection['id']}",
        json={"dailyRequestLimit": 50, "perAccountDailyLimit": 3},
        headers=owner,
    ).json()
    assert (updated["dailyRequestLimit"], updated["perAccountDailyLimit"]) == (50, 3)

    cleared = client.patch(
        f"{API}/ai/connections/{connection['id']}",
        json={"dailyRequestLimit": None},
        headers=owner,
    ).json()
    assert cleared["dailyRequestLimit"] is None
    assert cleared["perAccountDailyLimit"] == 3


def test_usage_is_recorded_and_reported(client, membership) -> None:
    owner = login(client, OWNER)
    _platform_connection(client, owner)
    student = _student(client, "alice@example.com")
    client.post(f"{API}/classes", headers=student)

    overview = client.get(f"{API}/platform/overview", headers=owner).json()
    assert overview["last24h"]["platform"]["successful"] == 1
    assert overview["last24h"]["classesCreated"] == 1
    assert overview["topAccounts24h"][0] == {"email": "alice@example.com", "requests": 1}
    assert overview["connections"][0]["last24h"]["requests"] == 1
    # El health check al crear la conexión no cuenta como consumo.
    assert sum(day["requests"] for day in overview["daily"]) == 1


def test_student_cannot_manage_platform_connections(client) -> None:
    owner = login(client, OWNER)
    connection = _platform_connection(client, owner)
    student = login(client, "alice@example.com")
    assert client.get(f"{API}/ai/connections?scope=platform", headers=student).status_code == 403
    assert (
        client.patch(
            f"{API}/ai/connections/{connection['id']}",
            json={"dailyRequestLimit": 1},
            headers=student,
        ).status_code
        == 404
    )
