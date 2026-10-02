"""T-042: copia excepcional de API keys por PLATFORM_OWNER."""

from sqlalchemy import select

from conftest import login
from app.ai.models import AICredentialAuditEvent
from app.db import SessionLocal

API = "/api/v1"


def _create_keyed_connection(
    client,
    headers: dict,
    *,
    name: str,
    key: str,
    scope: str = "account",
) -> int:
    response = client.post(
        f"{API}/ai/connections",
        json={
            "provider": "MOCK",
            "name": name,
            "model": "mock",
            "apiKey": key,
            "priority": 1,
            "scope": scope,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert key not in response.text
    return response.json()["id"]


def test_non_owner_cannot_copy_even_own_key(client) -> None:
    user = login(client, "user@example.com")
    connection_id = _create_keyed_connection(
        client, user, name="Personal", key="secret-user-1234"
    )

    response = client.post(
        f"{API}/ai/connections/{connection_id}/credential/copy",
        headers=user,
    )
    assert response.status_code == 403
    assert "secret-user-1234" not in response.text


def test_owner_can_copy_own_key_and_action_is_audited(client) -> None:
    owner = login(client, "owner@example.com")
    connection_id = _create_keyed_connection(
        client, owner, name="Owner personal", key="secret-owner-5678"
    )

    listed = client.get(f"{API}/ai/connections", headers=owner)
    assert listed.status_code == 200
    assert "secret-owner-5678" not in listed.text
    assert listed.json()[0]["credentialHint"].endswith("5678")

    copied = client.post(
        f"{API}/ai/connections/{connection_id}/credential/copy",
        headers=owner,
    )
    assert copied.status_code == 200
    assert copied.headers["cache-control"] == "no-store"
    assert copied.json() == {"apiKey": "secret-owner-5678"}

    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(AICredentialAuditEvent)
                .where(AICredentialAuditEvent.connection_id == connection_id)
                .order_by(AICredentialAuditEvent.id)
            )
        )
        assert [row.action for row in rows] == ["COPY"]
        assert all(row.account_id is not None for row in rows)
        assert all(row.connection_name == "Owner personal" for row in rows)
        assert all(row.owner_type == "ACCOUNT" for row in rows)


def test_owner_can_copy_platform_key(client) -> None:
    owner = login(client, "owner@example.com")
    connection_id = _create_keyed_connection(
        client,
        owner,
        name="Plataforma",
        key="platform-secret-9012",
        scope="platform",
    )

    response = client.post(
        f"{API}/ai/connections/{connection_id}/credential/copy",
        headers=owner,
    )
    assert response.status_code == 200
    assert response.json()["apiKey"] == "platform-secret-9012"


def test_owner_cannot_copy_another_accounts_byok(client) -> None:
    other = login(client, "other@example.com")
    connection_id = _create_keyed_connection(
        client, other, name="Otra cuenta", key="other-secret-3456"
    )
    owner = login(client, "owner@example.com")

    response = client.post(
        f"{API}/ai/connections/{connection_id}/credential/copy",
        headers=owner,
    )
    assert response.status_code == 404
    assert "other-secret-3456" not in response.text


def test_connection_without_key_cannot_be_copied(client) -> None:
    owner = login(client, "owner@example.com")
    response = client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Sin key", "model": "mock", "priority": 1},
        headers=owner,
    )
    assert response.status_code == 201

    copied = client.post(
        f"{API}/ai/connections/{response.json()['id']}/credential/copy",
        headers=owner,
    )
    assert copied.status_code == 409
