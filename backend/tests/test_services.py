"""T-004 etapa 1: servicios (vínculo × fuente de IA) otorgados por sr.macros."""

import json
from datetime import timedelta

from app.ai.service import PLATFORM_LABEL
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
    benefit_response = client.post(
        f"{API}/platform/benefits",
        json={
            "name": f"Manual test {email} {service_id} {days}",
            "serviceId": service_id,
            "durationDays": days,
            "active": True,
        },
        headers=owner,
    )
    assert benefit_response.status_code == 201, benefit_response.text
    response = client.post(
        f"{API}/platform/accounts/{_account_id(client, owner, email)}/benefit",
        json={"benefitId": benefit_response.json()["id"]},
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


def test_service_does_not_define_duration_and_manual_grant_uses_benefit(client) -> None:
    owner = login(client, OWNER)
    service = _services(client, owner)["INDIVIDUAL_PLATFORM"]
    assert "durationDays" not in service

    alice = _student(client, "benefit-only@example.com")
    benefit = client.post(
        f"{API}/platform/benefits",
        json={
            "name": "Plataforma 12 días",
            "serviceId": service["id"],
            "durationDays": 12,
            "active": True,
        },
        headers=owner,
    )
    assert benefit.status_code == 201, benefit.text

    granted = client.post(
        f"{API}/platform/accounts/{_account_id(client, owner, 'benefit-only@example.com')}/benefit",
        json={"benefitId": benefit.json()["id"]},
        headers=owner,
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["service"]["origin"] == "MANUAL"
    assert granted.json()["service"]["expiresAt"] is not None

    legacy = client.post(
        f"{API}/platform/accounts/{_account_id(client, owner, 'benefit-only@example.com')}/service",
        json={"serviceId": service["id"], "days": 99},
        headers=owner,
    )
    assert legacy.status_code == 405


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
    me = client.get(f"{API}/me", headers=alice).json()
    assert me["service"]["ownKeys"] == "unused"
    assert me["ai"]["own"] == 1  # guardada aunque no se use
    assert _new_class(client, alice)["generatedBy"] == PLATFORM_LABEL

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
    assert _new_class(client, alice)["generatedBy"] == PLATFORM_LABEL


def test_service_has_no_request_limit_field(client) -> None:
    owner = login(client, OWNER)
    service = _services(client, owner)["INDIVIDUAL_PLATFORM"]

    listed = client.get(f"{API}/platform/services", headers=owner)
    assert listed.status_code == 200
    assert all("dailyRequestLimit" not in row for row in listed.json())

    legacy = client.put(
        f"{API}/platform/services/{service['id']}",
        json={
            "name": service["name"],
            "description": service["description"],
            "active": service["active"],
            "dailyRequestLimit": 25,
        },
        headers=owner,
    )
    assert legacy.status_code == 422


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
    assert _new_class(client, alice)["generatedBy"] == PLATFORM_LABEL

    with SessionLocal() as db:
        subscription = db.scalars(select(Subscription)).one()
        subscription.expires_at = subscription.started_at + timedelta(seconds=1) - timedelta(days=1)
        db.commit()

    service = client.get(f"{API}/me", headers=alice).json()["service"]
    assert service["code"] == "INDIVIDUAL_BYOK"
    assert service["expired"]["name"] == "Individual · Plataforma"
    assert _new_class(client, alice)["generatedBy"] == "Mía"


def test_service_axes_are_fixed_and_only_combination_state_is_configurable(client) -> None:
    owner = login(client, OWNER)
    service = _services(client, owner)["INDIVIDUAL_PLATFORM"]

    # No se crean nuevas filas/columnas/combinaciones desde el portal.
    assert client.post(
        f"{API}/platform/services",
        json={"name": "Empresa", "source": "BYOK", "linkType": "CORPORATE"},
        headers=owner,
    ).status_code == 405

    # Tampoco se puede transformar una combinación existente cambiando sus ejes.
    changed_axis = client.put(
        f"{API}/platform/services/{service['id']}",
        json={"active": service["active"], "source": "HYBRID"},
        headers=owner,
    )
    assert changed_axis.status_code == 422

    updated = client.put(
        f"{API}/platform/services/{service['id']}",
        json={"active": True},
        headers=owner,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["source"] == "PLATFORM"
    assert updated.json()["linkType"] == "PERSONAL"


def test_platform_connection_details_are_hidden_from_students(client) -> None:
    """T-055: el alumno ve "IA de Librería Inglés", nunca nombre/proveedor/motor de plataforma."""
    owner = login(client, OWNER)
    _connection(client, owner, "Gemini interna", platform=True, model="mock-fail-quota")
    _connection(client, owner, "Clave secreta sr.macros", platform=True)
    alice = _student(client)
    _grant(client, owner, "alice@example.com", _services(client, owner)["INDIVIDUAL_PLATFORM"]["id"])

    created = _new_class(client, alice)
    assert created["generatedBy"] == PLATFORM_LABEL
    assert created["generationAi"]["providerLabel"] == PLATFORM_LABEL
    assert created["generationAi"]["model"] == ""
    assert created["generationAi"]["connectionId"] is None

    active = client.get(f"{API}/ai/active", headers=alice).json()["default"]
    assert active["connection"] == PLATFORM_LABEL and active["model"] == ""

    body = json.dumps(client.get(f"{API}/classes/{created['id']}", headers=alice).json())
    assert "Gemini interna" not in body and "Clave secreta" not in body

    # El dueño ve sus conexiones de plataforma con nombre.
    _connection(client, owner, "Mía del dueño")
    owner_active = client.get(f"{API}/ai/active", headers=owner).json()["default"]
    assert owner_active["connection"] == "Mía del dueño"


def test_platform_errors_do_not_name_platform_connections(client) -> None:
    owner = login(client, OWNER)
    _connection(client, owner, "Gemini interna", platform=True, model="mock-fail-quota")
    alice = _student(client)
    _grant(client, owner, "alice@example.com", _services(client, owner)["INDIVIDUAL_PLATFORM"]["id"])
    failed = _new_class(client, alice)
    assert failed["status"] == "GENERATION_FAILED"
    assert "Gemini interna" not in failed["generationError"]


def test_dev_purge_account_removes_personal_history_and_never_owner(client) -> None:
    from sqlalchemy import select

    from app.accounts.models import Account
    from app.campaigns.models import CampaignGrant
    from app.db import SessionLocal
    from app.study_profiles.models import AccountStudyProfile, StudyProfile
    from app.subscriptions.models import Subscription

    owner = login(client, OWNER)
    client.get(f"{API}/platform/services", headers=owner)

    with SessionLocal() as db:
        owner_account = db.scalar(select(Account).where(Account.email == OWNER))
        assert owner_account is not None
        owner_id = owner_account.id
    blocked = client.delete(f"{API}/platform/accounts/{owner_id}/dev-purge", headers=owner)
    assert blocked.status_code == 409

    campaigns = client.get(f"{API}/platform/campaigns", headers=owner).json()
    welcome = next(row for row in campaigns if row["code"] == "WELCOME_PLATFORM")
    assert client.post(
        f"{API}/platform/campaigns/{welcome['id']}/activate", headers=owner
    ).status_code == 200

    user_headers = login(client, "purge-me@example.com")
    assert client.get(f"{API}/me", headers=user_headers).json()["service"]["origin"] == "CAMPAIGN"

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "purge-me@example.com"))
        assert account is not None
        account_id = account.id
        profile_id = db.scalar(
            select(AccountStudyProfile.study_profile_id).where(
                AccountStudyProfile.account_id == account_id
            )
        )
        assert profile_id is not None
        assert db.scalar(
            select(CampaignGrant.id).where(CampaignGrant.account_id == account_id)
        ) is not None
        assert db.scalar(
            select(Subscription.id).where(Subscription.account_id == account_id)
        ) is not None

    response = client.delete(f"{API}/platform/accounts/{account_id}/dev-purge", headers=owner)
    assert response.status_code == 204, response.text

    with SessionLocal() as db:
        assert db.get(Account, account_id) is None
        assert db.get(StudyProfile, profile_id) is None
        assert db.scalar(
            select(AccountStudyProfile.account_id).where(
                AccountStudyProfile.account_id == account_id
            )
        ) is None
        assert db.scalar(
            select(CampaignGrant.id).where(CampaignGrant.account_id == account_id)
        ) is None
        assert db.scalar(
            select(Subscription.id).where(Subscription.account_id == account_id)
        ) is None


def test_dev_account_purge_flag_is_disabled_in_qa_and_production() -> None:
    from app.core.config import Settings

    assert Settings(app_env="local").dev_account_purge_allowed is True
    assert Settings(app_env="test").dev_account_purge_allowed is True
    assert Settings(app_env="qa").dev_account_purge_allowed is False
    assert Settings(app_env="production").dev_account_purge_allowed is False


def test_manual_benefit_can_be_replaced_and_remains_traceable(client) -> None:
    from app.db import SessionLocal
    from app.subscriptions.models import Subscription, SubscriptionStatus

    owner = login(client, OWNER)
    _student(client, "neptuno@example.com")
    services = _services(client, owner)
    service_id = services["INDIVIDUAL_PLATFORM"]["id"]
    account_id = _account_id(client, owner, "neptuno@example.com")

    first = client.post(
        f"{API}/platform/benefits",
        json={"name": "Bienvenida prueba", "serviceId": service_id, "durationDays": 3, "active": True},
        headers=owner,
    ).json()
    second = client.post(
        f"{API}/platform/benefits",
        json={"name": "Invitación amigo", "serviceId": service_id, "durationDays": 10, "active": True},
        headers=owner,
    ).json()

    granted = client.post(
        f"{API}/platform/accounts/{account_id}/benefit",
        json={"benefitId": first["id"]},
        headers=owner,
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["service"]["benefitId"] == first["id"]
    assert granted.json()["service"]["benefitName"] == "Bienvenida prueba"

    replaced = client.post(
        f"{API}/platform/accounts/{account_id}/benefit",
        json={"benefitId": second["id"]},
        headers=owner,
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["service"]["benefitId"] == second["id"]
    assert replaced.json()["service"]["benefitName"] == "Invitación amigo"

    with SessionLocal() as db:
        rows = db.scalars(
            select(Subscription)
            .where(Subscription.account_id == account_id)
            .order_by(Subscription.id)
        ).all()
        assert [row.benefit_id for row in rows[-2:]] == [first["id"], second["id"]]
        assert rows[-2].status == SubscriptionStatus.CANCELLED
        assert rows[-1].status == SubscriptionStatus.ACTIVE

    overview = client.get(f"{API}/platform/overview", headers=owner).json()
    row = next(item for item in overview["accountBenefits"] if item["email"] == "neptuno@example.com")
    assert row["benefitName"] == "Invitación amigo"
    assert row["serviceName"] == "Individual · Plataforma"
    assert row["origin"] == "MANUAL"


def test_benefit_delete_is_logical_and_keeps_historical_reference(client) -> None:
    from app.db import SessionLocal
    from app.subscriptions.models import Subscription

    owner = login(client, OWNER)
    _student(client, "logical-delete@example.com")
    service_id = _services(client, owner)["INDIVIDUAL_PLATFORM"]["id"]
    account_id = _account_id(client, owner, "logical-delete@example.com")

    benefit = client.post(
        f"{API}/platform/benefits",
        json={"name": "Temporal trazable", "serviceId": service_id, "durationDays": 7, "active": True},
        headers=owner,
    ).json()
    assert client.post(
        f"{API}/platform/accounts/{account_id}/benefit",
        json={"benefitId": benefit["id"]},
        headers=owner,
    ).status_code == 200

    # Mientras haya un beneficiario vigente, la baja lógica está protegida.
    assert client.delete(
        f"{API}/platform/benefits/{benefit['id']}", headers=owner
    ).status_code == 409

    # Al quitar el beneficio de la cuenta, la referencia pasa a ser histórica y ya no bloquea.
    assert client.delete(f"{API}/platform/accounts/{account_id}/service", headers=owner).status_code == 200
    deleted = client.delete(f"{API}/platform/benefits/{benefit['id']}", headers=owner)
    assert deleted.status_code == 204
    assert benefit["id"] not in {
        item["id"] for item in client.get(f"{API}/platform/benefits", headers=owner).json()
    }

    with SessionLocal() as db:
        historical = db.scalar(
            select(Subscription)
            .where(
                Subscription.account_id == account_id,
                Subscription.benefit_id == benefit["id"],
            )
            .order_by(Subscription.id.desc())
        )
        assert historical is not None
        assert historical.benefit_id == benefit["id"]


def test_benefit_cannot_be_deleted_with_current_beneficiary(client) -> None:
    owner = login(client, OWNER)
    _student(client, "protected-benefit@example.com")
    service_id = _services(client, owner)["INDIVIDUAL_PLATFORM"]["id"]
    account_id = _account_id(client, owner, "protected-benefit@example.com")

    benefit = client.post(
        f"{API}/platform/benefits",
        json={
            "name": "Promesa 30 días",
            "serviceId": service_id,
            "durationDays": 30,
            "active": True,
        },
        headers=owner,
    ).json()
    assert client.post(
        f"{API}/platform/accounts/{account_id}/benefit",
        json={"benefitId": benefit["id"]},
        headers=owner,
    ).status_code == 200

    listed = next(
        row for row in client.get(f"{API}/platform/benefits", headers=owner).json()
        if row["id"] == benefit["id"]
    )
    assert listed["activeBeneficiaries"] == 1
    assert listed["canDelete"] is False

    blocked = client.delete(f"{API}/platform/benefits/{benefit['id']}", headers=owner)
    assert blocked.status_code == 409
    assert "beneficiario" in blocked.json()["detail"]

    assert client.delete(f"{API}/platform/accounts/{account_id}/service", headers=owner).status_code == 200
    listed = next(
        row for row in client.get(f"{API}/platform/benefits", headers=owner).json()
        if row["id"] == benefit["id"]
    )
    assert listed["activeBeneficiaries"] == 0
    assert listed["canDelete"] is True
    assert client.delete(f"{API}/platform/benefits/{benefit['id']}", headers=owner).status_code == 204


def test_combination_cannot_be_disabled_while_active_benefit_or_account_uses_it(client) -> None:
    owner = login(client, OWNER)
    service = _services(client, owner)["INDIVIDUAL_HYBRID"]

    benefit = client.post(
        f"{API}/platform/benefits",
        headers=owner,
        json={
            "name": "Combinación protegida",
            "service": "PERSONAL",
            "source": "HYBRID",
            "durationDays": 30,
            "active": True,
        },
    )
    assert benefit.status_code == 201, benefit.text

    blocked_by_benefit = client.put(
        f"{API}/platform/services/{service['id']}",
        headers=owner,
        json={"active": False},
    )
    assert blocked_by_benefit.status_code == 409
    assert "beneficio" in blocked_by_benefit.json()["detail"]

    _student(client, "combo-protected@example.com")
    account_id = _account_id(client, owner, "combo-protected@example.com")
    assert client.post(
        f"{API}/platform/accounts/{account_id}/benefit",
        headers=owner,
        json={"benefitId": benefit.json()["id"]},
    ).status_code == 200

    # El beneficio puede quedar inactivo para futuros usos, pero la cuenta vigente sigue protegiendo la combinación.
    inactive = client.put(
        f"{API}/platform/benefits/{benefit.json()['id']}",
        headers=owner,
        json={
            "name": "Combinación protegida",
            "service": "PERSONAL",
            "source": "HYBRID",
            "durationDays": 30,
            "active": False,
        },
    )
    assert inactive.status_code == 200, inactive.text

    blocked_by_account = client.put(
        f"{API}/platform/services/{service['id']}",
        headers=owner,
        json={"active": False},
    )
    assert blocked_by_account.status_code == 409
    assert "cuenta" in blocked_by_account.json()["detail"]

    assert client.delete(f"{API}/platform/accounts/{account_id}/service", headers=owner).status_code == 200
    disabled = client.put(
        f"{API}/platform/services/{service['id']}",
        headers=owner,
        json={"active": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["active"] is False


def test_default_personal_account_protects_individual_byok_combination(client) -> None:
    owner = login(client, OWNER)
    byok = _services(client, owner)["INDIVIDUAL_BYOK"]
    _student(client, "default-byok@example.com")

    listed = _services(client, owner)["INDIVIDUAL_BYOK"]
    assert listed["activeAccounts"] >= 1
    assert listed["canDisable"] is False

    blocked = client.put(
        f"{API}/platform/services/{byok['id']}",
        headers=owner,
        json={"active": False},
    )
    assert blocked.status_code == 409
    assert "cuenta" in blocked.json()["detail"]
