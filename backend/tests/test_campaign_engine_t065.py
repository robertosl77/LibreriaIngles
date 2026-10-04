"""T-065: motor de campañas extensible, segmentación y preview."""

from datetime import datetime, timedelta, timezone

from conftest import login
from sqlalchemy import select

from app.accounts.models import Account
from app.campaigns.models import CampaignGrant
from app.db import SessionLocal
from app.learning.models import ClassSession, ClassSessionStatus, SessionKind
from app.study_profiles.models import AccountStudyProfile
from app.subscriptions.models import Subscription, SubscriptionOrigin, SubscriptionStatus

API = "/api/v1"
OWNER = "owner@example.com"


def _owner(client):
    return login(client, OWNER)


def _welcome_benefit_id(client, owner) -> int:
    campaigns = client.get(f"{API}/platform/campaigns", headers=owner)
    assert campaigns.status_code == 200, campaigns.text
    welcome = next(row for row in campaigns.json() if row["code"] == "WELCOME_PLATFORM")
    return int(welcome["benefitId"])


def _preview(client, owner, benefit_id: int, rules: list[dict]):
    return client.post(
        f"{API}/platform/campaigns/preview",
        headers=owner,
        json={
            "name": "Preview T-065",
            "benefitId": benefit_id,
            "action": "GRANT_BENEFIT",
            "actionConfig": {},
            "trigger": "LOGIN",
            "rules": rules,
            "priority": 100,
            "stackable": False,
            "maxRecipients": None,
            "startsAt": None,
            "endsAt": None,
            "notification": "IN_APP",
            "message": "Preview",
        },
    )


def test_campaign_capabilities_are_single_owner_catalog(client) -> None:
    user = login(client, "t065-user@example.com")
    assert client.get(f"{API}/platform/campaigns/capabilities", headers=user).status_code == 403

    owner = _owner(client)
    response = client.get(f"{API}/platform/campaigns/capabilities", headers=owner)
    assert response.status_code == 200, response.text
    body = response.json()

    rules = {rule["key"]: rule for rule in body["rules"]}
    assert rules["DAYS_SINCE_LAST_ACTIVITY"]["operators"] == ["EQ", "GTE", "LTE"]
    assert rules["DAYS_SINCE_SERVICE_EXPIRED"]["valueType"] == "integer"
    assert rules["DAYS_UNTIL_SERVICE_EXPIRES"]["valueType"] == "integer"
    assert rules["DOCUMENT_COUNTRY"]["valueType"] == "string"
    assert rules["SUBSCRIPTION_ORIGIN"]["valueType"] == "enum"
    assert {option["value"] for option in rules["SUBSCRIPTION_ORIGIN"]["options"]} == {
        "MANUAL",
        "CAMPAIGN",
        "INVITATION",
        "PAYMENT",
    }
    assert rules["NEVER_STUDIED"]["valueType"] == "boolean"
    assert rules["CURRENT_LEVEL"]["valueType"] == "enum"

    actions = {action["key"]: action for action in body["actions"]}
    assert actions["GRANT_BENEFIT"]["available"] is True
    assert actions["APPLY_DISCOUNT"]["available"] is False

    triggers = {trigger["key"]: trigger for trigger in body["triggers"]}
    assert triggers["LOGIN"]["available"] is True
    assert triggers["SCHEDULED"]["available"] is False


def test_preview_audience_uses_level_and_never_studied_without_side_effects(client) -> None:
    user = login(client, "preview-level@example.com")
    level = client.put(f"{API}/me/level", headers=user, json={"level": "A1"})
    assert level.status_code == 200, level.text

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    before_campaigns = len(client.get(f"{API}/platform/campaigns", headers=owner).json())

    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "CURRENT_LEVEL", "operator": "EQ", "value": "A1"},
            {"field": "NEVER_STUDIED", "operator": "EQ", "value": True},
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidateCount"] == 1
    assert body["eligibleCount"] == 1
    assert body["sample"][0]["email"] == "preview-level@example.com"
    assert body["sample"][0]["eligible"] is True
    assert body["action"] == "GRANT_BENEFIT"

    after_campaigns = len(client.get(f"{API}/platform/campaigns", headers=owner).json())
    assert after_campaigns == before_campaigns
    with SessionLocal() as db:
        assert db.scalar(select(CampaignGrant.id)) is None
        account = db.scalar(select(Account).where(Account.email == "preview-level@example.com"))
        assert account is not None
        assert db.scalar(
            select(Subscription.id).where(Subscription.account_id == account.id)
        ) is None


def test_preview_can_segment_by_days_since_last_activity(client) -> None:
    user = login(client, "inactive@example.com")
    assert client.put(f"{API}/me/level", headers=user, json={"level": "A1"}).status_code == 200

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "inactive@example.com"))
        link = db.scalar(
            select(AccountStudyProfile).where(AccountStudyProfile.account_id == account.id)
        )
        assert account is not None and link is not None
        db.add(
            ClassSession(
                study_profile_id=link.study_profile_id,
                account_id=account.id,
                status=ClassSessionStatus.COMPLETED,
                kind=SessionKind.CLASS,
                target_level="A1",
                evaluated_at=datetime.now(timezone.utc) - timedelta(days=65),
            )
        )
        db.commit()

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [{"field": "DAYS_SINCE_LAST_ACTIVITY", "operator": "GTE", "value": 60}],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    result = body["sample"][0]["rules"][0]
    assert result["field"] == "DAYS_SINCE_LAST_ACTIVITY"
    assert result["matched"] is True
    assert result["actual"] >= 60


def test_preview_can_segment_by_expired_service_without_confusing_payment(client) -> None:
    user = login(client, "expired-service@example.com")
    owner = _owner(client)
    services = client.get(f"{API}/platform/services", headers=owner).json()
    plan = next(row for row in services if row["code"] == "INDIVIDUAL_PLATFORM")
    benefit_id = _welcome_benefit_id(client, owner)

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "expired-service@example.com"))
        assert account is not None
        now = datetime.now(timezone.utc)
        db.add(
            Subscription(
                plan_id=plan["id"],
                account_id=account.id,
                status=SubscriptionStatus.EXPIRED,
                started_at=now - timedelta(days=80),
                expires_at=now - timedelta(days=40),
                ended_at=now - timedelta(days=40),
            )
        )
        db.commit()

    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {"field": "HAS_GRANTED_SERVICE", "operator": "EQ", "value": False},
            {"field": "DAYS_SINCE_SERVICE_EXPIRED", "operator": "GTE", "value": 30},
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json()["eligibleCount"] == 1


def test_preview_can_segment_by_days_until_active_service_expires(client) -> None:
    login(client, "expiring-service@example.com")
    owner = _owner(client)
    services = client.get(f"{API}/platform/services", headers=owner).json()
    plan = next(row for row in services if row["code"] == "INDIVIDUAL_PLATFORM")
    benefit_id = _welcome_benefit_id(client, owner)

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "expiring-service@example.com"))
        assert account is not None
        now = datetime.now(timezone.utc)
        db.add(
            Subscription(
                plan_id=plan["id"],
                account_id=account.id,
                status=SubscriptionStatus.ACTIVE,
                origin=SubscriptionOrigin.MANUAL,
                started_at=now - timedelta(days=10),
                expires_at=now + timedelta(days=6, hours=12),
            )
        )
        db.commit()

    response = _preview(
        client,
        owner,
        benefit_id,
        [{"field": "DAYS_UNTIL_SERVICE_EXPIRES", "operator": "LTE", "value": 7}],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    result = body["sample"][0]["rules"][0]
    assert result["field"] == "DAYS_UNTIL_SERVICE_EXPIRES"
    assert result["actual"] == 7
    assert result["matched"] is True


def test_preview_can_segment_by_document_country(client) -> None:
    login(client, "argentina-document@example.com")
    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "argentina-document@example.com"))
        assert account is not None
        account.document_country = "AR"
        db.commit()

    response = _preview(
        client,
        owner,
        benefit_id,
        [{"field": "DOCUMENT_COUNTRY", "operator": "EQ", "value": "ar"}],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    result = body["sample"][0]["rules"][0]
    assert result["actual"] == "AR"
    assert result["expected"] == "AR"
    assert result["matched"] is True

    invalid = _preview(
        client,
        owner,
        benefit_id,
        [{"field": "DOCUMENT_COUNTRY", "operator": "EQ", "value": "ARG"}],
    )
    assert invalid.status_code == 422


def test_preview_can_segment_by_active_subscription_origin(client) -> None:
    login(client, "invitation-origin@example.com")
    owner = _owner(client)
    services = client.get(f"{API}/platform/services", headers=owner).json()
    plan = next(row for row in services if row["code"] == "INDIVIDUAL_PLATFORM")
    benefit_id = _welcome_benefit_id(client, owner)

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "invitation-origin@example.com"))
        assert account is not None
        now = datetime.now(timezone.utc)
        db.add(
            Subscription(
                plan_id=plan["id"],
                account_id=account.id,
                status=SubscriptionStatus.ACTIVE,
                origin=SubscriptionOrigin.INVITATION,
                started_at=now - timedelta(days=3),
                expires_at=now + timedelta(days=20),
            )
        )
        db.commit()

    response = _preview(
        client,
        owner,
        benefit_id,
        [{"field": "SUBSCRIPTION_ORIGIN", "operator": "EQ", "value": "INVITATION"}],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    result = body["sample"][0]["rules"][0]
    assert result["actual"] == "INVITATION"
    assert result["matched"] is True


def test_unavailable_action_is_rejected_instead_of_faked(client) -> None:
    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = client.post(
        f"{API}/platform/campaigns",
        headers=owner,
        json={
            "name": "Descuento todavía no",
            "benefitId": benefit_id,
            "action": "APPLY_DISCOUNT",
            "actionConfig": {"percent": 20},
            "trigger": "LOGIN",
            "rules": [],
            "priority": 100,
            "stackable": False,
            "notification": "NONE",
        },
    )
    assert response.status_code == 422


def _add_completed_classes(email: str, day_offsets: list[int], classes_per_day: list[int]) -> None:
    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == email))
        assert account is not None
        link = db.scalar(
            select(AccountStudyProfile).where(AccountStudyProfile.account_id == account.id)
        )
        assert link is not None
        now = datetime.now(timezone.utc)
        for offset, count in zip(day_offsets, classes_per_day, strict=True):
            for index in range(count):
                db.add(
                    ClassSession(
                        study_profile_id=link.study_profile_id,
                        account_id=account.id,
                        status=ClassSessionStatus.COMPLETED,
                        kind=SessionKind.CLASS,
                        target_level="A1",
                        evaluated_at=now - timedelta(days=offset, minutes=index),
                    )
                )
        db.commit()


def test_activity_metrics_can_express_five_classes_each_day_for_a_week(client) -> None:
    user = login(client, "loyal-week@example.com")
    assert client.put(f"{API}/me/level", headers=user, json={"level": "A1"}).status_code == 200
    _add_completed_classes(
        "loyal-week@example.com",
        day_offsets=[0, 1, 2, 3, 4, 5, 6],
        classes_per_day=[5, 5, 5, 5, 5, 5, 5],
    )

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {
                "field": "MIN_CLASSES_PER_ACTIVE_DAY",
                "operator": "GTE",
                "value": 5,
                "windowDays": 7,
            },
            {
                "field": "ACTIVE_STUDY_DAYS",
                "operator": "GTE",
                "value": 7,
                "windowDays": 7,
            },
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    values = {row["field"]: row for row in body["sample"][0]["rules"]}
    assert values["MIN_CLASSES_PER_ACTIVE_DAY"]["actual"] == 5
    assert values["MIN_CLASSES_PER_ACTIVE_DAY"]["windowDays"] == 7
    assert values["ACTIVE_STUDY_DAYS"]["actual"] == 7


def test_activity_metrics_support_total_average_and_streak(client) -> None:
    user = login(client, "loyal-metrics@example.com")
    assert client.put(f"{API}/me/level", headers=user, json={"level": "A1"}).status_code == 200
    _add_completed_classes(
        "loyal-metrics@example.com",
        day_offsets=[0, 1, 2],
        classes_per_day=[3, 5, 7],
    )

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {"field": "CLASSES_COMPLETED", "operator": "GTE", "value": 15, "windowDays": 7},
            {
                "field": "AVERAGE_CLASSES_PER_ACTIVE_DAY",
                "operator": "GTE",
                "value": 5,
                "windowDays": 7,
            },
            {"field": "STUDY_STREAK_DAYS", "operator": "GTE", "value": 3},
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    values = {row["field"]: row["actual"] for row in body["sample"][0]["rules"]}
    assert values["CLASSES_COMPLETED"] == 15
    assert values["AVERAGE_CLASSES_PER_ACTIVE_DAY"] == 5.0
    assert values["STUDY_STREAK_DAYS"] == 3


def test_metric_rule_requires_explicit_window(client) -> None:
    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [{"field": "CLASSES_COMPLETED", "operator": "GTE", "value": 5}],
    )
    assert response.status_code == 422
    assert "ventana" in response.text.lower()


def test_campaign_assist_understands_daily_classes_and_keeps_discount_as_warning(client) -> None:
    owner = _owner(client)
    _welcome_benefit_id(client, owner)
    connection = client.post(
        f"{API}/ai/connections",
        headers=owner,
        json={
            "provider": "MOCK",
            "name": "T-065 assistant",
            "model": "mock",
            "priority": 1,
            "scope": "platform",
        },
    )
    assert connection.status_code == 201, connection.text

    response = client.post(
        f"{API}/platform/campaigns/assist",
        headers=owner,
        json={
            "description": (
                "Alumnos personales que realizan por lo menos 5 clases diarias: "
                "darles un beneficio y un 10% de descuento."
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    rules = body["draft"]["rules"]
    assert any(
        rule["field"] == "MIN_CLASSES_PER_ACTIVE_DAY"
        and rule["operator"] == "GTE"
        and rule["value"] == 5
        and rule["windowDays"] == 30
        for rule in rules
    )
    assert any(
        rule["field"] == "ACTIVE_STUDY_DAYS"
        and rule["operator"] == "GTE"
        and rule["value"] == 30
        and rule["windowDays"] == 30
        for rule in rules
    )
    warnings = " ".join(body["warnings"]).lower()
    assert "30 días" in warnings
    assert "descuento" in warnings or "precio" in warnings
    assert body["executable"] is False
    assert body["blockingIssues"]



def test_average_classes_per_day_counts_inactive_days_in_window(client) -> None:
    user = login(client, "average-real@example.com")
    assert client.put(f"{API}/me/level", headers=user, json={"level": "A1"}).status_code == 200
    # 150 clases concentradas en 10 días: promedio real de una ventana de 30 = 5/día.
    _add_completed_classes(
        "average-real@example.com",
        day_offsets=list(range(10)),
        classes_per_day=[15] * 10,
    )

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {
                "field": "AVERAGE_CLASSES_PER_DAY",
                "operator": "GTE",
                "value": 5,
                "windowDays": 30,
            },
            {
                "field": "AVERAGE_CLASSES_PER_ACTIVE_DAY",
                "operator": "GTE",
                "value": 15,
                "windowDays": 30,
            },
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    values = {row["field"]: row["actual"] for row in body["sample"][0]["rules"]}
    assert values["AVERAGE_CLASSES_PER_DAY"] == 5.0
    assert values["AVERAGE_CLASSES_PER_ACTIVE_DAY"] == 15.0


def _ensure_mock_campaign_assistant(client, owner) -> None:
    response = client.post(
        f"{API}/ai/connections",
        headers=owner,
        json={
            "provider": "MOCK",
            "name": "T-065 fidelity lab",
            "model": "mock",
            "priority": 1,
            "scope": "platform",
        },
    )
    assert response.status_code == 201, response.text


def _create_scenario_benefit(client, owner, service_id: int, *, index: int, name: str) -> dict:
    durations = [7, 5, 3, 10, 14, 7, 5, 10, 3, 14, 7, 5]
    response = client.post(
        f"{API}/platform/benefits",
        headers=owner,
        json={
            "name": f"T065 · {name}",
            "serviceId": service_id,
            "durationDays": durations[index % len(durations)],
            "active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _assert_rule(draft: dict, expected: dict) -> None:
    candidates = [rule for rule in draft["rules"] if rule["field"] == expected["field"]]
    assert candidates, f"Falta regla {expected['field']} en {draft['rules']}"
    assert any(
        all(rule.get(key) == value for key, value in expected.items())
        for rule in candidates
    ), f"No se encontró {expected}; reglas: {candidates}"


def test_fifteen_fidelity_campaigns_are_simulated_and_supported_ones_can_be_created(client) -> None:
    owner = _owner(client)
    _welcome_benefit_id(client, owner)
    _ensure_mock_campaign_assistant(client, owner)
    services = client.get(f"{API}/platform/services", headers=owner)
    assert services.status_code == 200, services.text
    service_id = next(
        row["id"] for row in services.json() if row["code"] == "INDIVIDUAL_PLATFORM"
    )

    scenarios = [
        {
            "name": "Premio aniversario",
            "description": (
                "Premiar a alumnos personales con más de 1 año de antigüedad en la app "
                "con un beneficio de agradecimiento."
            ),
            "rules": [{"field": "DAYS_SINCE_CREATED", "operator": "GTE", "value": 365}],
            "executable": True,
        },
        {
            "name": "Promedio diario alto",
            "description": (
                "Premiar a alumnos personales con un promedio mínimo de 5 clases por día "
                "en los últimos 30 días con un beneficio."
            ),
            "rules": [
                {
                    "field": "AVERAGE_CLASSES_PER_DAY",
                    "operator": "GTE",
                    "value": 5,
                    "windowDays": 30,
                }
            ],
            "executable": True,
        },
        {
            "name": "Constancia diaria estricta",
            "description": (
                "Premiar a alumnos personales que hagan al menos 3 clases todos los días "
                "durante 7 días con un beneficio."
            ),
            "rules": [
                {
                    "field": "MIN_CLASSES_PER_ACTIVE_DAY",
                    "operator": "GTE",
                    "value": 3,
                    "windowDays": 7,
                },
                {
                    "field": "ACTIVE_STUDY_DAYS",
                    "operator": "GTE",
                    "value": 7,
                    "windowDays": 7,
                },
            ],
            "executable": True,
        },
        {
            "name": "Racha de estudio",
            "description": (
                "Premiar a alumnos personales con una racha de 14 días de estudio con un beneficio."
            ),
            "rules": [{"field": "STUDY_STREAK_DAYS", "operator": "GTE", "value": 14}],
            "executable": True,
        },
        {
            "name": "Alta presencia mensual",
            "description": (
                "Premiar a alumnos personales con al menos 20 días con actividad "
                "en los últimos 30 días con un beneficio."
            ),
            "rules": [
                {
                    "field": "ACTIVE_STUDY_DAYS",
                    "operator": "GTE",
                    "value": 20,
                    "windowDays": 30,
                }
            ],
            "executable": True,
        },
        {
            "name": "Volumen mensual",
            "description": (
                "Premiar a alumnos personales que completen al menos 50 clases "
                "en los últimos 30 días con un beneficio."
            ),
            "rules": [
                {
                    "field": "CLASSES_COMPLETED",
                    "operator": "GTE",
                    "value": 50,
                    "windowDays": 30,
                }
            ],
            "executable": True,
        },
        {
            "name": "Regreso por inactividad",
            "description": (
                "Hacer volver a alumnos personales sin membresía que no estudian hace 60 días "
                "ofreciéndoles un beneficio de regreso."
            ),
            "rules": [
                {"field": "HAS_GRANTED_SERVICE", "operator": "EQ", "value": False},
                {"field": "DAYS_SINCE_LAST_ACTIVITY", "operator": "GTE", "value": 60},
            ],
            "executable": True,
        },
        {
            "name": "Regreso tras vencimiento",
            "description": (
                "Recuperar alumnos personales sin membresía cuyo servicio venció hace 30 días "
                "con un beneficio para volver."
            ),
            "rules": [
                {"field": "HAS_GRANTED_SERVICE", "operator": "EQ", "value": False},
                {"field": "DAYS_SINCE_SERVICE_EXPIRED", "operator": "GTE", "value": 30},
            ],
            "executable": True,
        },
        {
            "name": "Nunca empezó",
            "description": (
                "Motivar a alumnos personales que nunca estudiaron ni completaron una clase "
                "con un beneficio de primera práctica."
            ),
            "rules": [{"field": "NEVER_STUDIED", "operator": "EQ", "value": True}],
            "executable": True,
        },
        {
            "name": "Impulso A1 intensivo",
            "description": (
                "Premiar alumnos personales A1 que completen al menos 30 clases "
                "en los últimos 14 días con un beneficio."
            ),
            "rules": [
                {"field": "CURRENT_LEVEL", "operator": "EQ", "value": "A1"},
                {
                    "field": "CLASSES_COMPLETED",
                    "operator": "GTE",
                    "value": 30,
                    "windowDays": 14,
                },
            ],
            "executable": True,
        },
        {
            "name": "Riesgo por baja actividad",
            "description": (
                "Reactivar alumnos personales con como máximo 3 clases "
                "en los últimos 30 días con un beneficio para volver."
            ),
            "rules": [
                {
                    "field": "CLASSES_COMPLETED",
                    "operator": "LTE",
                    "value": 3,
                    "windowDays": 30,
                }
            ],
            "executable": True,
        },
        {
            "name": "Riesgo por promedio bajo",
            "description": (
                "Reactivar alumnos personales cuyo promedio sea como máximo 1 clase por día "
                "en los últimos 14 días con un beneficio."
            ),
            "rules": [
                {
                    "field": "AVERAGE_CLASSES_PER_DAY",
                    "operator": "LTE",
                    "value": 1,
                    "windowDays": 14,
                }
            ],
            "executable": True,
        },
        {
            "name": "Recuperación de reclamo",
            "description": (
                "Dar una compensación a alumnos personales que tuvieron un reclamo resuelto "
                "por soporte durante la última semana."
            ),
            "rules": [],
            "executable": False,
            "warning": "reclamos",
        },
        {
            "name": "Premio por referidos",
            "description": (
                "Premiar a alumnos personales que invitaron a 3 amigos que se registraron "
                "con un beneficio especial."
            ),
            "rules": [],
            "executable": False,
            "warning": "referid",
        },
        {
            "name": "Antigüedad y promedio con descuento",
            "description": (
                "Necesito crear una campaña para beneficiar a los alumnos personal no corporativos "
                "que lleven más de 6 meses en la app y hagan un promedio de 5 clases diarias como mínimo; "
                "a estos les quiero ofrecer un 10% de descuento en la membresía."
            ),
            "rules": [
                {"field": "DAYS_SINCE_CREATED", "operator": "GTE", "value": 180},
                {
                    "field": "AVERAGE_CLASSES_PER_DAY",
                    "operator": "GTE",
                    "value": 5,
                    "windowDays": 30,
                },
            ],
            "executable": False,
            "warning": "descuento",
        },
    ]

    created_names: list[str] = []
    simulated: list[dict] = []
    reward_index = 0

    for scenario in scenarios:
        response = client.post(
            f"{API}/platform/campaigns/assist",
            headers=owner,
            json={"description": scenario["description"]},
        )
        assert response.status_code == 200, f"{scenario['name']}: {response.text}"
        body = response.json()
        draft = body["draft"]
        for expected_rule in scenario["rules"]:
            _assert_rule(draft, expected_rule)

        simulated.append(
            {
                "name": scenario["name"],
                "draft": draft,
                "warnings": body["warnings"],
                "blockingIssues": body["blockingIssues"],
            }
        )
        assert body["executable"] is scenario["executable"], (scenario["name"], body)

        if not scenario["executable"]:
            warning_text = " ".join(body["warnings"]).lower()
            assert scenario["warning"] in warning_text, (scenario["name"], body)
            assert body["blockingIssues"], (
                f"{scenario['name']} debe quedar explícitamente bloqueada"
            )
            continue

        benefit = _create_scenario_benefit(
            client,
            owner,
            service_id,
            index=reward_index,
            name=scenario["name"],
        )
        reward_index += 1
        final_draft = {
            **draft,
            "name": scenario["name"],
            "benefitId": benefit["id"],
        }
        created = client.post(
            f"{API}/platform/campaigns",
            headers=owner,
            json=final_draft,
        )
        assert created.status_code == 201, f"{scenario['name']}: {created.text}"
        created_body = created.json()
        assert created_body["name"] == scenario["name"]
        assert created_body["status"] == "DRAFT"
        assert created_body["action"] == "GRANT_BENEFIT"
        created_names.append(created_body["name"])

    assert len(simulated) == 15
    assert len(created_names) == 12
    assert len(set(created_names)) == 12

    rows = client.get(f"{API}/platform/campaigns", headers=owner)
    assert rows.status_code == 200
    persisted_names = {row["name"] for row in rows.json()}
    assert set(created_names) <= persisted_names



def test_local_fidelity_lab_seed_creates_fifteen_drafts_idempotently(client) -> None:
    from app.campaigns.service import FIDELITY_LAB_CAMPAIGNS, _seed_fidelity_lab_campaigns

    owner = _owner(client)
    _welcome_benefit_id(client, owner)

    with SessionLocal() as db:
        _seed_fidelity_lab_campaigns(db)
        db.commit()

    rows = client.get(f"{API}/platform/campaigns", headers=owner)
    assert rows.status_code == 200, rows.text
    lab_rows = [row for row in rows.json() if row["code"].startswith("LAB_FID_")]
    assert len(lab_rows) == 15
    assert len({row["code"] for row in lab_rows}) == 15
    assert all(row["status"] == "DRAFT" for row in lab_rows)
    assert {row["code"] for row in lab_rows} == {
        spec["code"] for spec in FIDELITY_LAB_CAMPAIGNS
    }

    complaint = next(row for row in lab_rows if row["code"] == "LAB_FID_15_COMPLAINT")
    assert complaint["rules"] == [
        {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
        {
            "field": "ACCOUNT_EMAIL",
            "operator": "EQ",
            "value": "reemplazar@ejemplo.invalid",
        },
    ]

    avg = next(row for row in lab_rows if row["code"] == "LAB_FID_01_6M_AVG5")
    assert any(
        rule["field"] == "AVERAGE_CLASSES_PER_DAY"
        and rule["operator"] == "GTE"
        and rule["value"] == 5
        and rule["windowDays"] == 30
        for rule in avg["rules"]
    )

    with SessionLocal() as db:
        _seed_fidelity_lab_campaigns(db)
        db.commit()

    rows_again = client.get(f"{API}/platform/campaigns", headers=owner)
    assert rows_again.status_code == 200
    assert len(
        [row for row in rows_again.json() if row["code"].startswith("LAB_FID_")]
    ) == 15
