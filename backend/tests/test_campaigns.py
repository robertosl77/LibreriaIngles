"""T-004 etapa 2: campañas configurables sobre beneficios reutilizables."""

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


def _benefit(client, owner, service_id: int, *, name: str, days: int) -> dict:
    response = client.post(
        f"{API}/platform/benefits",
        headers=owner,
        json={"name": name, "serviceId": service_id, "durationDays": days, "active": True},
    )
    assert response.status_code == 201, response.text
    return response.json()


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
    benefit = _benefit(client, owner, service_id, name=f"{name} · beneficio", days=days)
    response = client.post(
        f"{API}/platform/campaigns",
        headers=owner,
        json={
            "name": name,
            "benefitId": benefit["id"],
            "trigger": "FIRST_LOGIN",
            "rules": rules or [{"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"}],
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
    assert welcome["benefitName"] == "Bienvenida"
    assert welcome["grantDays"] == 3
    assert welcome["notification"] == "IN_APP"


def test_active_welcome_applies_once_on_first_login_and_notifies_in_app(client) -> None:
    owner, _ = _owner_and_services(client)
    welcome = next(row for row in _campaigns(client, owner) if row["code"] == "WELCOME_PLATFORM")
    activated = client.post(f"{API}/platform/campaigns/{welcome['id']}/activate", headers=owner)
    assert activated.status_code == 200
    assert activated.json()["activatedAt"] is not None

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


def test_first_login_campaign_reconciles_from_persisted_timestamps(client) -> None:
    from app.campaigns.models import CampaignGrant
    from app.db import SessionLocal
    from app.subscriptions.models import Subscription

    owner, _ = _owner_and_services(client)
    welcome = next(row for row in _campaigns(client, owner) if row["code"] == "WELCOME_PLATFORM")
    activated = client.post(f"{API}/platform/campaigns/{welcome['id']}/activate", headers=owner)
    assert activated.status_code == 200

    alice = login(client, "reconcile@example.com")
    with SessionLocal() as db:
        grant = db.scalar(
            select(CampaignGrant).where(CampaignGrant.campaign_id == welcome["id"])
        )
        assert grant is not None
        subscription = db.get(Subscription, grant.subscription_id)
        db.delete(grant)
        if subscription is not None:
            db.delete(subscription)
        db.commit()

    me = client.get(f"{API}/me", headers=alice)
    assert me.status_code == 200
    assert me.json()["service"]["source"] == "PLATFORM"
    assert me.json()["service"]["origin"] == "CAMPAIGN"


def test_reactivation_does_not_capture_first_login_that_happened_while_paused(client) -> None:
    owner, _ = _owner_and_services(client)
    welcome = next(row for row in _campaigns(client, owner) if row["code"] == "WELCOME_PLATFORM")

    assert client.post(
        f"{API}/platform/campaigns/{welcome['id']}/activate", headers=owner
    ).status_code == 200

    saturn = login(client, "saturno1@example.com")
    assert client.get(f"{API}/me", headers=saturn).json()["service"]["source"] == "PLATFORM"

    assert client.post(
        f"{API}/platform/campaigns/{welcome['id']}/pause", headers=owner
    ).status_code == 200

    neptune = login(client, "neptuno1@example.com")
    assert client.get(f"{API}/me", headers=neptune).json()["service"]["source"] == "BYOK"

    assert client.post(
        f"{API}/platform/campaigns/{welcome['id']}/activate", headers=owner
    ).status_code == 200

    neptune = login(client, "neptuno1@example.com")
    assert client.get(f"{API}/me", headers=neptune).json()["service"]["source"] == "BYOK"


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
    first = _create_campaign(client, owner, plan_id, name="Campaña A", days=3, priority=10)
    benefit = _benefit(client, owner, plan_id, name="Campaña B · beneficio", days=5)
    response = client.post(
        f"{API}/platform/campaigns",
        headers=owner,
        json={
            "name": "Campaña B",
            "benefitId": benefit["id"],
            "trigger": "FIRST_LOGIN",
            "rules": [],
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


def test_campaign_engine_exception_never_blocks_login_me_or_level(client, monkeypatch) -> None:
    import app.auth.api as auth_api
    import app.campaigns.service as campaign_service

    def explode(*args, **kwargs):
        raise RuntimeError("campaign-engine-boom")

    monkeypatch.setattr(campaign_service, "evaluate_login_campaigns", explode)
    headers = login(client, "campaign-failure@example.com")

    monkeypatch.setattr(auth_api, "reconcile_first_login_campaigns", explode)
    me = client.get(f"{API}/me", headers=headers)
    assert me.status_code == 200, me.text

    level = client.put(f"{API}/me/level", headers=headers, json={"level": "A1"})
    assert level.status_code == 200, level.text


def test_ended_campaign_cannot_be_reactivated_or_deleted_before_end(client) -> None:
    owner, services = _owner_and_services(client)
    campaign = _create_campaign(
        client,
        owner,
        services["INDIVIDUAL_PLATFORM"]["id"],
        name="Ciclo cerrado",
        days=3,
        priority=10,
    )

    assert client.delete(f"{API}/platform/campaigns/{campaign['id']}", headers=owner).status_code == 409
    assert client.post(
        f"{API}/platform/campaigns/{campaign['id']}/finish", headers=owner
    ).status_code == 200
    assert client.post(
        f"{API}/platform/campaigns/{campaign['id']}/activate", headers=owner
    ).status_code == 409


def test_delete_ended_campaign_without_recipients_is_physical(client) -> None:
    from app.campaigns.models import Campaign
    from app.db import SessionLocal

    owner, services = _owner_and_services(client)
    benefit = _benefit(
        client, owner, services["INDIVIDUAL_PLATFORM"]["id"], name="Sin beneficiarios · beneficio", days=3
    )
    response = client.post(
        f"{API}/platform/campaigns",
        headers=owner,
        json={
            "name": "Sin beneficiarios",
            "benefitId": benefit["id"],
            "trigger": "FIRST_LOGIN",
            "rules": [],
            "priority": 20,
            "stackable": False,
            "notification": "NONE",
        },
    )
    assert response.status_code == 201, response.text
    campaign_id = response.json()["id"]
    campaign_code = response.json()["code"]

    assert client.post(f"{API}/platform/campaigns/{campaign_id}/finish", headers=owner).status_code == 200
    assert client.delete(f"{API}/platform/campaigns/{campaign_id}", headers=owner).status_code == 204

    with SessionLocal() as db:
        assert db.get(Campaign, campaign_id) is None
    assert all(row["code"] != campaign_code for row in _campaigns(client, owner))


def test_delete_ended_campaign_with_recipients_keeps_grant_history(client) -> None:
    from app.accounts.models import Account
    from app.campaigns.models import Campaign, CampaignGrant
    from app.db import SessionLocal

    owner, services = _owner_and_services(client)
    campaign = _create_campaign(
        client,
        owner,
        services["INDIVIDUAL_PLATFORM"]["id"],
        name="Con historial",
        days=3,
        priority=1,
    )

    user = login(client, "history@example.com")
    assert client.get(f"{API}/me", headers=user).json()["service"]["source"] == "PLATFORM"

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "history@example.com"))
        assert account is not None
        account_id = account.id
        assert db.scalar(
            select(CampaignGrant.id).where(
                CampaignGrant.campaign_id == campaign["id"],
                CampaignGrant.account_id == account_id,
            )
        ) is not None

    assert client.post(f"{API}/platform/campaigns/{campaign['id']}/finish", headers=owner).status_code == 200
    assert client.delete(f"{API}/platform/campaigns/{campaign['id']}", headers=owner).status_code == 204
    assert all(row["id"] != campaign["id"] for row in _campaigns(client, owner))

    login(client, "history@example.com")
    with SessionLocal() as db:
        stored = db.get(Campaign, campaign["id"])
        assert stored is not None
        assert stored.deleted_at is not None
        grants = db.scalars(
            select(CampaignGrant).where(
                CampaignGrant.campaign_id == campaign["id"],
                CampaignGrant.account_id == account_id,
            )
        ).all()
        assert len(grants) == 1


def test_deleted_seed_welcome_without_recipients_is_not_recreated(client) -> None:
    owner, _ = _owner_and_services(client)
    welcome = next(row for row in _campaigns(client, owner) if row["code"] == "WELCOME_PLATFORM")
    assert welcome["recipients"] == 0

    assert client.post(f"{API}/platform/campaigns/{welcome['id']}/finish", headers=owner).status_code == 200
    assert client.delete(f"{API}/platform/campaigns/{welcome['id']}", headers=owner).status_code == 204
    assert all(row["code"] != "WELCOME_PLATFORM" for row in _campaigns(client, owner))


def test_benefit_cannot_be_deleted_while_campaign_is_active_or_paused(client) -> None:
    owner, services = _owner_and_services(client)
    service_id = services["INDIVIDUAL_PLATFORM"]["id"]
    benefit = _benefit(client, owner, service_id, name="Beneficio campaña vigente", days=15)
    campaign = client.post(
        f"{API}/platform/campaigns",
        headers=owner,
        json={
            "name": "Campaña vigente",
            "benefitId": benefit["id"],
            "trigger": "FIRST_LOGIN",
            "rules": [],
            "priority": 10,
            "stackable": False,
            "notification": "NONE",
        },
    ).json()

    assert client.post(
        f"{API}/platform/campaigns/{campaign['id']}/activate", headers=owner
    ).status_code == 200
    listed = next(
        row for row in client.get(f"{API}/platform/benefits", headers=owner).json()
        if row["id"] == benefit["id"]
    )
    assert listed["activeCampaigns"] == 1
    assert listed["canDelete"] is False
    assert client.delete(f"{API}/platform/benefits/{benefit['id']}", headers=owner).status_code == 409

    assert client.post(
        f"{API}/platform/campaigns/{campaign['id']}/pause", headers=owner
    ).status_code == 200
    listed = next(
        row for row in client.get(f"{API}/platform/benefits", headers=owner).json()
        if row["id"] == benefit["id"]
    )
    assert listed["activeCampaigns"] == 1
    assert listed["canDelete"] is False

    assert client.post(
        f"{API}/platform/campaigns/{campaign['id']}/finish", headers=owner
    ).status_code == 200
    listed = next(
        row for row in client.get(f"{API}/platform/benefits", headers=owner).json()
        if row["id"] == benefit["id"]
    )
    assert listed["activeCampaigns"] == 0
    assert listed["canDelete"] is True


def test_campaign_assist_builds_reviewable_draft_without_persisting(client, monkeypatch) -> None:
    from types import SimpleNamespace

    import app.platform.campaigns_api as campaigns_api

    owner, services = _owner_and_services(client)
    benefit = _benefit(
        client,
        owner,
        services["INDIVIDUAL_PLATFORM"]["id"],
        name="Fidelidad",
        days=30,
    )
    before = len(_campaigns(client, owner))

    def fake_assist(*args, **kwargs):
        return SimpleNamespace(
            data={
                "draft": {
                    "name": "Aniversario",
                    "benefitId": benefit["id"],
                    "trigger": "SCHEDULED",
                    "rules": [
                        {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
                        {"field": "DAYS_SINCE_CREATED", "operator": "GTE", "value": 365},
                    ],
                    "priority": 50,
                    "stackable": True,
                    "maxRecipients": 100,
                    "notification": "IN_APP",
                    "message": "Gracias por seguir con nosotros.",
                },
                "warnings": ["El pedido menciona un descuento, que el motor actual no administra."],
                "summary": "Fidelización al cumplir un año.",
            }
        )

    monkeypatch.setattr(campaigns_api, "run_platform_json_task", fake_assist)
    response = client.post(
        f"{API}/platform/campaigns/assist",
        headers=owner,
        json={"description": "Al cumplir un año, dar un beneficio y 20% de descuento."},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["draft"]["name"] == "Aniversario"
    assert body["draft"]["benefitId"] == benefit["id"]
    assert body["draft"]["trigger"] == "LOGIN"
    assert body["draft"]["rules"][1] == {
        "field": "DAYS_SINCE_CREATED",
        "operator": "GTE",
        "value": 365,
    }
    assert any("disparador" in warning.lower() for warning in body["warnings"])
    assert any("descuento" in warning.lower() for warning in body["warnings"])
    assert len(_campaigns(client, owner)) == before


def test_campaign_assist_uses_platform_ai_only_and_does_not_create_campaign(client) -> None:
    from app.ai.models import AIConnectionOwnerType, AIUsageEvent
    from app.db import SessionLocal

    owner, _ = _owner_and_services(client)

    own = client.post(
        f"{API}/ai/connections",
        headers=owner,
        json={
            "provider": "MOCK",
            "name": "Owner BYOK",
            "model": "mock",
            "priority": 1,
            "scope": "account",
        },
    )
    assert own.status_code == 201, own.text

    platform = client.post(
        f"{API}/ai/connections",
        headers=owner,
        json={
            "provider": "MOCK",
            "name": "Asistente plataforma",
            "model": "mock",
            "priority": 20,
            "scope": "platform",
        },
    )
    assert platform.status_code == 201, platform.text

    before = len(_campaigns(client, owner))
    response = client.post(
        f"{API}/platform/campaigns/assist",
        headers=owner,
        json={"description": "Usuarios con al menos un año desde el registro, al volver a ingresar."},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["draft"]["trigger"] == "LOGIN"
    assert any(
        rule["field"] == "DAYS_SINCE_CREATED"
        and rule["operator"] == "GTE"
        and rule["value"] == 365
        for rule in body["draft"]["rules"]
    )
    assert len(_campaigns(client, owner)) == before

    with SessionLocal() as db:
        events = list(
            db.scalars(
                select(AIUsageEvent).where(AIUsageEvent.operation == "campaign_assist")
            )
        )
        assert len(events) == 1
        assert events[0].owner_type == AIConnectionOwnerType.PLATFORM
        assert events[0].connection_id == platform.json()["id"]


def test_campaign_assist_is_owner_only(client) -> None:
    user = login(client, "campaign-assist-user@example.com")
    response = client.post(
        f"{API}/platform/campaigns/assist",
        headers=user,
        json={"description": "Crear una campaña de bienvenida para usuarios nuevos."},
    )
    assert response.status_code == 403
