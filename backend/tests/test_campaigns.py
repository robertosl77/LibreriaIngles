"""T-004 etapa 2: campañas configurables y otorgamiento idempotente."""

from datetime import datetime, timezone

from conftest import login
from sqlalchemy import select

API = "/api/v1"
OWNER = "owner@example.com"


def _owner_and_services(client):
    owner = login(client, OWNER)
    response = client.get(f"{API}/platform/services", headers=owner)
    assert response.status_code == 200, response.text
    services = {row["code"]: row for row in response.json()}
    return owner, services


def _campaigns(client, owner):
    response = client.get(f"{API}/platform/campaigns", headers=owner)
    assert response.status_code == 200, response.text
    return response.json()


def _create_campaign(
    client,
    owner,
    service_id: int,
    *,
    name: str,
    days: int,
    priority: int,
    stackable: bool = False,
    max_recipients: int | None = None,
    notification: str = "IN_APP",
    rules: list[dict] | None = None,
):
    response = client.post(
        f"{API}/platform/campaigns",
        headers=owner,
        json={
            "name": name,
            "serviceId": service_id,
            "trigger": "FIRST_LOGIN",
            "rules": rules or [{"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"}],
            "grantDays": days,
            "priority": priority,
            "stackable": stackable,
            "maxRecipients": max_recipients,
            "notification": notification,
            "message": f"Beneficio de {name}",
        },
    )
    assert response.status_code == 201, response.text
    campaign = response.json()
    activated = client.post(f"{API}/platform/campaigns/{campaign['id']}/activate", headers=owner)
    assert activated.status_code == 200, activated.text
    return activated.json()


def test_campaign_portal_is_owner_only_and_welcome_is_seeded_as_draft(client) -> None:
    alice = login(client, "alice@example.com")
    assert client.get(f"{API}/platform/campaigns", headers=alice).status_code == 403

    owner, _ = _owner_and_services(client)
    welcome = next(row for row in _campaigns(client, owner) if row["code"] == "WELCOME_PLATFORM")
    assert welcome["status"] == "DRAFT"
    assert welcome["trigger"] == "FIRST_LOGIN"
    assert welcome["grantDays"] == 3
    assert welcome["notification"] == "IN_APP"


def test_active_welcome_applies_once_on_first_login_and_notifies_in_app(client) -> None:
    owner, _ = _owner_and_services(client)
    welcome = next(row for row in _campaigns(client, owner) if row["code"] == "WELCOME_PLATFORM")
    activated = client.post(f"{API}/platform/campaigns/{welcome['id']}/activate", headers=owner)
    assert activated.status_code == 200

    alice = login(client, "alice@example.com")
    me = client.get(f"{API}/me", headers=alice).json()
    assert me["service"]["source"] == "PLATFORM"
    assert me["service"]["origin"] == "CAMPAIGN"
    assert me["service"]["expiresAt"] is not None

    notices = client.get(f"{API}/campaign-notices", headers=alice).json()
    assert len(notices) == 1
    assert notices[0]["campaignId"] == welcome["id"]
    assert "3 días" in notices[0]["benefit"]
    assert client.post(
        f"{API}/campaign-notices/{notices[0]['grantId']}/read", headers=alice
    ).status_code == 204
    assert client.get(f"{API}/campaign-notices", headers=alice).json() == []

    login(client, "alice@example.com")
    rows = client.get(f"{API}/platform/campaigns", headers=owner).json()
    welcome_after = next(row for row in rows if row["id"] == welcome["id"])
    assert welcome_after["recipients"] == 1


def test_existing_account_does_not_receive_first_login_campaign_later(client) -> None:
    alice = login(client, "old@example.com")
    owner, _ = _owner_and_services(client)
    welcome = next(row for row in _campaigns(client, owner) if row["code"] == "WELCOME_PLATFORM")
    client.post(f"{API}/platform/campaigns/{welcome['id']}/activate", headers=owner)

    login(client, "old@example.com")
    assert client.get(f"{API}/me", headers=alice).json()["service"]["source"] == "BYOK"


def test_priority_selects_non_stackable_campaign(client) -> None:
    owner, services = _owner_and_services(client)
    plan = services["INDIVIDUAL_PLATFORM"]
    high = _create_campaign(
        client, owner, plan["id"], name="Primeros 100", days=30, priority=1, stackable=False
    )
    low = _create_campaign(
        client, owner, plan["id"], name="Bienvenida alternativa", days=3, priority=2, stackable=False
    )

    login(client, "priority@example.com")
    rows = {row["id"]: row for row in _campaigns(client, owner)}
    assert rows[high["id"]]["recipients"] == 1
    assert rows[low["id"]]["recipients"] == 0


def test_two_stackable_campaigns_add_their_days(client) -> None:
    from app.campaigns.models import CampaignGrant
    from app.db import SessionLocal
    from app.subscriptions.models import Subscription

    owner, services = _owner_and_services(client)
    plan = services["INDIVIDUAL_PLATFORM"]
    _create_campaign(client, owner, plan["id"], name="Promo 30", days=30, priority=1, stackable=True)
    _create_campaign(client, owner, plan["id"], name="Bienvenida 3", days=3, priority=2, stackable=True)

    before = datetime.now(timezone.utc)
    login(client, "stack@example.com")
    with SessionLocal() as db:
        grants = db.scalars(select(CampaignGrant)).all()
        account_id = grants[0].account_id
        account_grants = [g for g in grants if g.account_id == account_id]
        subscription = db.scalars(
            select(Subscription).where(Subscription.account_id == account_id)
        ).one()
        assert len(account_grants) == 2
        expiry = subscription.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        assert 32.9 <= (expiry - before).total_seconds() / 86400 <= 33.1


def test_max_recipients_reserves_only_configured_slots(client) -> None:
    owner, services = _owner_and_services(client)
    campaign = _create_campaign(
        client,
        owner,
        services["INDIVIDUAL_PLATFORM"]["id"],
        name="Solo uno",
        days=7,
        priority=1,
        max_recipients=1,
    )
    first = login(client, "first@example.com")
    second = login(client, "second@example.com")
    assert client.get(f"{API}/me", headers=first).json()["service"]["source"] == "PLATFORM"
    assert client.get(f"{API}/me", headers=second).json()["service"]["source"] == "BYOK"
    row = next(r for r in _campaigns(client, owner) if r["id"] == campaign["id"])
    assert row["recipients"] == 1


def test_overlapping_non_stackable_campaigns_return_warning(client) -> None:
    owner, services = _owner_and_services(client)
    plan_id = services["INDIVIDUAL_PLATFORM"]["id"]
    first = _create_campaign(client, owner, plan_id, name="A", days=3, priority=10)
    response = client.post(
        f"{API}/platform/campaigns",
        headers=owner,
        json={
            "name": "B",
            "serviceId": plan_id,
            "trigger": "FIRST_LOGIN",
            "rules": [],
            "grantDays": 5,
            "priority": 20,
            "stackable": False,
            "notification": "NONE",
        },
    )
    assert response.status_code == 201, response.text
    assert any(w["id"] == first["id"] for w in response.json()["overlapWarnings"])


def test_email_notification_is_queued_not_sent_by_campaign_engine(client) -> None:
    owner, services = _owner_and_services(client)
    campaign = _create_campaign(
        client,
        owner,
        services["INDIVIDUAL_PLATFORM"]["id"],
        name="Email futuro",
        days=4,
        priority=1,
        notification="EMAIL",
    )
    login(client, "mail@example.com")
    row = next(r for r in _campaigns(client, owner) if r["id"] == campaign["id"])
    assert row["pendingEmails"] == 1
