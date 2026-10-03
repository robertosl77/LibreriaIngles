"""T-065: motor de campañas extensible, segmentación y preview."""

from datetime import datetime, timedelta, timezone

from conftest import login
from sqlalchemy import select

from app.accounts.models import Account
from app.campaigns.models import CampaignGrant
from app.db import SessionLocal
from app.learning.models import ClassSession, ClassSessionStatus, SessionKind
from app.study_profiles.models import AccountStudyProfile
from app.subscriptions.models import Subscription, SubscriptionStatus

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
