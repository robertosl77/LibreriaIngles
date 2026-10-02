"""T-004 etapa 1: servicios (vínculo × fuente de IA) otorgados por sr.macros."""

from datetime import timedelta

from conftest import login
from sqlalchemy import select

API = "/api/v1"
OWNER = "owner@example.com"


def _student(client, email: str = "alice@example.com") -> dict:
    headers = login(client, email)
    assert client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers).status_code == 200
    return headers


def _connection(client, headers, name: str, *, platform: bool = False, **extra) -> dict:
    body = {"provider": "MOCK", "name": name, "priority": 1, **extra}
    if platform:
        body["scope"] = "platform"
    response = client.post(f"{API}/ai/connections", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _services(client, owner) -> dict:
    response = client.get(f"{API}/platform/services", headers=owner)
    assert response.status_code == 200, response.text
    return {s["code"]: s for s in response.json()}


def _account_id(client, owner, email: str) -> int:
    rows = client.get(f"{API}/platform/accounts", params={"q": email}, headers=owner).json()
    return next(r["id"] for r in rows if r["email"] == email)


def _grant(client, owner, email: str, service_id: int, days: int | None = None) -> dict:
    response = client.post(
        f"{API}/platform/accounts/{_account_id(client, owner, email)}/service",
        json={"serviceId": service_id, "days": days},
        headers=owner,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _new_class(client, headers) -> dict:
    return client.post(f"{API}/classes", headers=headers).json()


def test_default_service_is_personal_byok(client) -> None:
    alice = _student(client)
    service = client.get(f"{API}/me", headers=alice).json()["service"]
    assert service["code"] == "INDIVIDUAL_BYOK"
    assert service["source"] == "BYOK"
    assert service["linkType"] == "PERSONAL"
    assert service["granted"] is False
    assert service["usesOwnKeys"] is True and service["usesPlatform"] is False
    assert service["ownKeys"] == "required"


def test_owner_is_shown_as_platform_owner(client) -> None:
    owner = login(client, OWNER)
    service = client.get(f"{API}/me", headers=owner).json()["service"]
    assert service["name"] == "Dueño de la plataforma"
    assert service["usesOwnKeys"] is True and service["usesPlatform"] is True


def test_portal_is_only_for_platform_owner(client) -> None:
    alice = _student(client)
    assert client.get(f"{API}/platform/services", headers=alice).status_code == 403
    assert client.get(f"{API}/platform/accounts", headers=alice).status_code == 403
    owner = login(client, OWNER)
    assert set(_services(client, owner)) >= {
        "INDIVIDUAL_BYOK",
        "INDIVIDUAL_PLATFORM",
        "INDIVIDUAL_HYBRID",
    }


def test_source_decides_which_keys_are_used(client) -> None:
    owner = login(client, OWNER)
    _connection(client, owner, "Plataforma", platform=True)
    alice = _student(client)
    _connection(client, alice, "Mía")
    services = _services(client, owner)

    # Sin servicio: solo propias.
    assert _new_class(client, alice)["generatedBy"] == "Mía"

    # Plataforma: ignora las propias.
    _grant(client, owner, "alice@example.com", services["INDIVIDUAL_PLATFORM"]["id"])
    assert client.get(f"{API}/me", headers=alice).json()["service"]["ownKeys"] == "unused"
    assert _new_class(client, alice)["generatedBy"] == "Plataforma"

    # Volver a propias keys.
    account_id = _account_id(client, owner, "alice@example.com")
    revoked = client.delete(f"{API}/platform/accounts/{account_id}/service", headers=owner)
    assert revoked.json()["service"]["granted"] is False
    assert _new_class(client, alice)["generatedBy"] == "Mía"


def test_without_service_platform_is_never_used(client) -> None:
    owner = login(client, OWNER)
    _connection(client, owner, "Plataforma", platform=True)
    alice = _student(client)
    created = _new_class(client, alice)
    assert created["status"] == "GENERATION_FAILED"


def test_hybrid_uses_own_first_then_platform(client) -> None:
    owner = login(client, OWNER)
    _connection(client, owner, "Plataforma", platform=True)
    alice = _student(client)
    _connection(client, alice, "Mía rota", model="mock-fail-quota")
    _grant(client, owner, "alice@example.com", _services(client, owner)["INDIVIDUAL_HYBRID"]["id"])
    assert _new_class(client, alice)["generatedBy"] == "Plataforma"


def test_service_daily_cap_limits_platform_usage(client) -> None:
    owner = login(client, OWNER)
    _connection(client, owner, "Plataforma", platform=True)
    created = client.post(
        f"{API}/platform/services",
        json={"name": "Prueba 1 por día", "source": "PLATFORM", "dailyRequestLimit": 1},
        headers=owner,
    )
    assert created.status_code == 201, created.text
    alice = _student(client)
    _grant(client, owner, "alice@example.com", created.json()["id"])
    assert _new_class(client, alice)["status"] == "READY"
    second = _new_class(client, alice)
    assert second["status"] == "GENERATION_FAILED"
    assert "tope" in second["generationError"]
    me = client.get(f"{API}/me", headers=alice).json()["service"]
    assert me["dailyRequestLimit"] == 1 and me["platformRequests24h"] == 1


def test_granted_days_expire_back_to_own_keys(client) -> None:
    from app.db import SessionLocal
    from app.subscriptions.models import Subscription

    owner = login(client, OWNER)
    _connection(client, owner, "Plataforma", platform=True)
    alice = _student(client)
    _connection(client, alice, "Mía")
    granted = _grant(
        client, owner, "alice@example.com", _services(client, owner)["INDIVIDUAL_PLATFORM"]["id"], 3
    )
    assert granted["service"]["expiresAt"] is not None
    assert _new_class(client, alice)["generatedBy"] == "Plataforma"

    with SessionLocal() as db:
        subscription = db.scalars(select(Subscription)).one()
        subscription.expires_at = subscription.started_at + timedelta(seconds=1) - timedelta(days=1)
        db.commit()

    service = client.get(f"{API}/me", headers=alice).json()["service"]
    assert service["code"] == "INDIVIDUAL_BYOK"
    assert service["expired"]["name"] == "Individual · Plataforma"
    assert _new_class(client, alice)["generatedBy"] == "Mía"


def test_corporate_services_wait_for_companies(client) -> None:
    owner = login(client, OWNER)
    response = client.post(
        f"{API}/platform/services",
        json={"name": "Empresa", "source": "BYOK", "linkType": "CORPORATE"},
        headers=owner,
    )
    assert response.status_code == 422
