"""T-065: motor de campañas extensible, segmentación y preview."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from conftest import login
from sqlalchemy import select

from app.accounts.models import Account
from app.ai.models import AIConnection, AIConnectionOwnerType, AIUsageEvent
from app.campaigns.models import CampaignGrant
from app.curriculum.service import get_level
from app.db import SessionLocal
from app.exams.models import LevelCertificate
from app.learning.models import (
    Attempt,
    ClassSession,
    ClassSessionStatus,
    EvaluationMode,
    Exercise,
    PresentationMode,
    ResponseMode,
    SessionKind,
)
from app.progress.service import recompute_skill
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
    assert rules["CERTIFICATE_ISSUED"]["valueType"] == "enum"
    assert {option["value"] for option in rules["CERTIFICATE_ISSUED"]["options"]} == {
        "A1",
        "A2",
        "B1",
        "B2",
        "C1",
        "C2",
    }
    assert rules["EXAMS_FAILED"]["requiresWindow"] is True
    assert rules["CLASSES_GENERATED"]["requiresWindow"] is True
    assert rules["CLASSES_STARTED"]["requiresWindow"] is True
    assert rules["CLASSES_GENERATION_FAILED"]["requiresWindow"] is True
    assert rules["CLASSES_NOT_COMPLETED"]["requiresWindow"] is True
    assert rules["LAST_ENDED_STREAK_DAYS"]["valueType"] == "integer"
    assert rules["DAYS_SINCE_STREAK_BROKEN"]["valueType"] == "integer"
    assert rules["SKILL_STATUS"]["subjectLabel"] == "Skill"
    assert rules["SKILL_STATUS"]["subjectOptions"]
    assert rules["ABILITY_STATUS"]["subjectLabel"] == "Habilidad"
    assert {option["value"] for option in rules["ABILITY_STATUS"]["subjectOptions"]} >= {
        "WRITING",
        "SPEAKING",
        "LISTENING",
    }
    assert rules["APPEALS_COUNT"]["requiresWindow"] is True
    assert rules["SPEAKING_RESPONSES"]["requiresWindow"] is False
    assert rules["LISTENING_RESPONSES"]["requiresWindow"] is False
    assert rules["AI_FAILURES_COUNT"]["requiresWindow"] is True
    ai_filters = {item["key"]: item for item in rules["AI_FAILURES_COUNT"]["filters"]}
    assert {option["value"] for option in ai_filters["ownerType"]["options"]} >= {
        "ACCOUNT",
        "PLATFORM",
    }
    assert {option["value"] for option in ai_filters["errorCode"]["options"]} >= {
        "CREDENTIAL_OR_QUOTA",
        "INVALID_CREDENTIALS",
        "QUOTA_EXCEEDED",
    }
    assert ai_filters["operation"]["valueType"] == "string"
    assert rules["DAYS_SINCE_BYOK_CONFIGURED_WITHOUT_SUCCESS"]["valueType"] == "integer"

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


def test_preview_can_segment_by_real_level_certificate(client) -> None:
    user = login(client, "certificate-campaign@example.com")
    assert client.put(f"{API}/me/level", headers=user, json={"level": "A1"}).status_code == 200

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "certificate-campaign@example.com"))
        link = db.scalar(
            select(AccountStudyProfile).where(AccountStudyProfile.account_id == account.id)
        )
        assert account is not None and link is not None
        now = datetime.now(timezone.utc)
        exam = ClassSession(
            study_profile_id=link.study_profile_id,
            account_id=account.id,
            status=ClassSessionStatus.COMPLETED,
            kind=SessionKind.EXAM,
            target_level="A1",
            score=88,
            exam_result={"passed": True},
            evaluated_at=now - timedelta(days=1),
        )
        db.add(exam)
        db.flush()
        db.add(
            LevelCertificate(
                code="LI-A1-CAMPAIGN-TEST",
                study_profile_id=link.study_profile_id,
                account_id=account.id,
                exam_session_id=exam.id,
                holder_name=account.display_name or "Alumno",
                level="A1",
                score=88,
                area_scores={},
                issued_at=now - timedelta(days=1),
            )
        )
        db.commit()

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [{"field": "CERTIFICATE_ISSUED", "operator": "EQ", "value": "A1"}],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    result = body["sample"][0]["rules"][0]
    assert result["actual"] == "A1"
    assert result["expected"] == "A1"
    assert result["matched"] is True

    other_level = _preview(
        client,
        owner,
        benefit_id,
        [{"field": "CERTIFICATE_ISSUED", "operator": "EQ", "value": "B1"}],
    )
    assert other_level.status_code == 200, other_level.text
    assert other_level.json()["eligibleCount"] == 0

    invalid = _preview(
        client,
        owner,
        benefit_id,
        [{"field": "CERTIFICATE_ISSUED", "operator": "EQ", "value": "A7"}],
    )
    assert invalid.status_code == 422


def test_preview_can_segment_by_failed_exam_count(client) -> None:
    user = login(client, "exam-metrics@example.com")
    assert client.put(f"{API}/me/level", headers=user, json={"level": "A1"}).status_code == 200

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "exam-metrics@example.com"))
        link = db.scalar(
            select(AccountStudyProfile).where(AccountStudyProfile.account_id == account.id)
        )
        assert account is not None and link is not None
        now = datetime.now(timezone.utc)
        for index, passed in enumerate((False, False, True), start=1):
            db.add(
                ClassSession(
                    study_profile_id=link.study_profile_id,
                    account_id=account.id,
                    status=ClassSessionStatus.COMPLETED,
                    kind=SessionKind.EXAM,
                    target_level="A1",
                    score=55 if not passed else 85,
                    exam_result={"passed": passed},
                    evaluated_at=now - timedelta(days=index * 3),
                )
            )
        db.commit()

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {"field": "EXAMS_COMPLETED", "operator": "GTE", "value": 3, "windowDays": 30},
            {"field": "EXAMS_FAILED", "operator": "GTE", "value": 2, "windowDays": 30},
            {"field": "EXAMS_PASSED", "operator": "EQ", "value": 1, "windowDays": 30},
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    values = {row["field"]: row["actual"] for row in body["sample"][0]["rules"]}
    assert values["EXAMS_COMPLETED"] == 3
    assert values["EXAMS_FAILED"] == 2
    assert values["EXAMS_PASSED"] == 1


def test_preview_can_segment_by_class_lifecycle_metrics(client) -> None:
    user = login(client, "class-lifecycle@example.com")
    assert client.put(f"{API}/me/level", headers=user, json={"level": "A1"}).status_code == 200

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "class-lifecycle@example.com"))
        link = db.scalar(
            select(AccountStudyProfile).where(AccountStudyProfile.account_id == account.id)
        )
        assert account is not None and link is not None
        now = datetime.now(timezone.utc)

        rows = [
            ClassSession(
                study_profile_id=link.study_profile_id,
                account_id=account.id,
                status=ClassSessionStatus.COMPLETED,
                kind=SessionKind.CLASS,
                target_level="A1",
                created_at=now - timedelta(days=1),
                generated_at=now - timedelta(days=1),
                submitted_at=now - timedelta(days=1),
                evaluated_at=now - timedelta(days=1),
            ),
            ClassSession(
                study_profile_id=link.study_profile_id,
                account_id=account.id,
                status=ClassSessionStatus.IN_PROGRESS,
                kind=SessionKind.CLASS,
                target_level="A1",
                created_at=now - timedelta(days=2),
                generated_at=now - timedelta(days=2),
            ),
            ClassSession(
                study_profile_id=link.study_profile_id,
                account_id=account.id,
                status=ClassSessionStatus.READY,
                kind=SessionKind.CLASS,
                target_level="A1",
                created_at=now - timedelta(days=3),
                generated_at=now - timedelta(days=3),
            ),
            ClassSession(
                study_profile_id=link.study_profile_id,
                account_id=account.id,
                status=ClassSessionStatus.READY,
                kind=SessionKind.CLASS,
                target_level="A1",
                created_at=now - timedelta(days=4),
                generated_at=now - timedelta(days=4),
            ),
            ClassSession(
                study_profile_id=link.study_profile_id,
                account_id=account.id,
                status=ClassSessionStatus.READY,
                kind=SessionKind.CLASS,
                target_level="A1",
                created_at=now - timedelta(days=5),
                generated_at=now - timedelta(days=5),
            ),
            ClassSession(
                study_profile_id=link.study_profile_id,
                account_id=account.id,
                status=ClassSessionStatus.GENERATION_FAILED,
                kind=SessionKind.CLASS,
                target_level="A1",
                created_at=now - timedelta(days=2),
                generation_error="fallo simulado",
            ),
        ]
        db.add_all(rows)
        db.commit()

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {"field": "CLASSES_GENERATED", "operator": "GTE", "value": 5, "windowDays": 7},
            {"field": "CLASSES_STARTED", "operator": "GTE", "value": 2, "windowDays": 7},
            {
                "field": "CLASSES_GENERATION_FAILED",
                "operator": "GTE",
                "value": 1,
                "windowDays": 7,
            },
            {"field": "CLASSES_NOT_COMPLETED", "operator": "GTE", "value": 4, "windowDays": 7},
            {"field": "CLASSES_COMPLETED", "operator": "LTE", "value": 1, "windowDays": 7},
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    values = {row["field"]: row["actual"] for row in body["sample"][0]["rules"]}
    assert values["CLASSES_GENERATED"] == 5
    assert values["CLASSES_STARTED"] == 2
    assert values["CLASSES_GENERATION_FAILED"] == 1
    assert values["CLASSES_NOT_COMPLETED"] == 4
    assert values["CLASSES_COMPLETED"] == 1


def test_preview_uses_real_broken_streak_history(client) -> None:
    user = login(client, "broken-streak@example.com")
    assert client.put(f"{API}/me/level", headers=user, json={"level": "A1"}).status_code == 200
    _add_completed_classes(
        "broken-streak@example.com",
        day_offsets=[4, 5, 6, 7],
        classes_per_day=[1, 1, 1, 1],
    )

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {"field": "STUDY_STREAK_DAYS", "operator": "EQ", "value": 0},
            {"field": "LAST_ENDED_STREAK_DAYS", "operator": "GTE", "value": 4},
            {"field": "DAYS_SINCE_STREAK_BROKEN", "operator": "GTE", "value": 2},
            {"field": "DAYS_SINCE_STREAK_BROKEN", "operator": "LTE", "value": 5},
            {"field": "DAYS_SINCE_LAST_ACTIVITY", "operator": "EQ", "value": 4},
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    values = [row for row in body["sample"][0]["rules"]]
    by_field = {}
    for row in values:
        by_field.setdefault(row["field"], []).append(row["actual"])
    assert by_field["STUDY_STREAK_DAYS"] == [0]
    assert by_field["LAST_ENDED_STREAK_DAYS"] == [4]
    assert by_field["DAYS_SINCE_STREAK_BROKEN"] == [3, 3]
    assert by_field["DAYS_SINCE_LAST_ACTIVITY"] == [4]


def test_preview_can_segment_by_skill_and_ability_progress(client) -> None:
    user = login(client, "progress-campaign@example.com")
    assert client.put(f"{API}/me/level", headers=user, json={"level": "A1"}).status_code == 200

    curriculum = get_level("A1")
    assert curriculum is not None
    writing_skill = next(skill for skill in curriculum.skills if skill.area_key == "writing")

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "progress-campaign@example.com"))
        link = db.scalar(
            select(AccountStudyProfile).where(AccountStudyProfile.account_id == account.id)
        )
        assert account is not None and link is not None
        now = datetime.now(timezone.utc)
        session = ClassSession(
            study_profile_id=link.study_profile_id,
            account_id=account.id,
            status=ClassSessionStatus.COMPLETED,
            kind=SessionKind.CLASS,
            target_level="A1",
            evaluated_at=now,
        )
        db.add(session)
        db.flush()
        exercise = Exercise(
            class_session_id=session.id,
            study_profile_id=link.study_profile_id,
            position=0,
            level="A1",
            area="writing",
            skill_key=writing_skill.key,
            exercise_type="short_writing",
            prompt="Write a short answer.",
            evaluation_mode=EvaluationMode.AI,
        )
        db.add(exercise)
        db.flush()
        for number, score in enumerate((90, 90, 20, 20), start=1):
            db.add(
                Attempt(
                    exercise_id=exercise.id,
                    study_profile_id=link.study_profile_id,
                    account_id=account.id,
                    attempt_number=number,
                    raw_answer=f"answer {number}",
                    normalized_answer=f"answer {number}",
                    response_mode=ResponseMode.WRITE,
                    score=score,
                    evaluated_at=now - timedelta(days=5 - number),
                )
            )
        db.flush()
        recompute_skill(
            db,
            study_profile_id=link.study_profile_id,
            skill_key=writing_skill.key,
        )
        db.commit()

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {
                "field": "SKILL_STATUS",
                "subject": writing_skill.key,
                "operator": "EQ",
                "value": "NEEDS_REVIEW",
            },
            {
                "field": "SKILL_SCORE",
                "subject": writing_skill.key,
                "operator": "LTE",
                "value": 60,
            },
            {
                "field": "SKILL_TREND",
                "subject": writing_skill.key,
                "operator": "EQ",
                "value": "DOWN",
            },
            {
                "field": "ABILITY_STATUS",
                "subject": "WRITING",
                "operator": "EQ",
                "value": "NEEDS_REVIEW",
            },
            {
                "field": "ABILITY_SCORE",
                "subject": "WRITING",
                "operator": "LTE",
                "value": 60,
            },
            {
                "field": "ABILITY_TREND",
                "subject": "WRITING",
                "operator": "EQ",
                "value": "DOWN",
            },
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    rows = body["sample"][0]["rules"]
    assert all(row["matched"] for row in rows)
    assert {row.get("subject") for row in rows} == {writing_skill.key, "WRITING"}

    invalid = _preview(
        client,
        owner,
        benefit_id,
        [{"field": "ABILITY_STATUS", "operator": "EQ", "value": "NEEDS_REVIEW"}],
    )
    assert invalid.status_code == 422
    assert "seleccionar" in invalid.text.lower()


def test_preview_can_segment_by_recent_appeals(client) -> None:
    user = login(client, "appeals-campaign@example.com")
    assert client.put(f"{API}/me/level", headers=user, json={"level": "A1"}).status_code == 200

    curriculum = get_level("A1")
    assert curriculum is not None
    skill = curriculum.skills[0]

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "appeals-campaign@example.com"))
        link = db.scalar(
            select(AccountStudyProfile).where(AccountStudyProfile.account_id == account.id)
        )
        assert account is not None and link is not None
        now = datetime.now(timezone.utc)
        session = ClassSession(
            study_profile_id=link.study_profile_id,
            account_id=account.id,
            status=ClassSessionStatus.COMPLETED,
            kind=SessionKind.CLASS,
            target_level="A1",
            evaluated_at=now,
        )
        db.add(session)
        db.flush()
        exercise = Exercise(
            class_session_id=session.id,
            study_profile_id=link.study_profile_id,
            position=0,
            level="A1",
            area=skill.area_key,
            skill_key=skill.key,
            exercise_type="fill_blank",
            prompt="Complete.",
            evaluation_mode=EvaluationMode.HYBRID,
        )
        db.add(exercise)
        db.flush()
        for number in range(1, 4):
            db.add(
                Attempt(
                    exercise_id=exercise.id,
                    study_profile_id=link.study_profile_id,
                    account_id=account.id,
                    attempt_number=number,
                    raw_answer="x",
                    normalized_answer="x",
                    score=50,
                    appealed_at=now - timedelta(days=number),
                    evaluated_at=now - timedelta(days=number),
                )
            )
        db.commit()

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [{"field": "APPEALS_COUNT", "operator": "GTE", "value": 3, "windowDays": 14}],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    result = body["sample"][0]["rules"][0]
    assert result["actual"] == 3
    assert result["matched"] is True


def test_preview_can_segment_by_speaking_and_listening_usage(client) -> None:
    user = login(client, "modality-campaign@example.com")
    assert client.put(f"{API}/me/level", headers=user, json={"level": "A1"}).status_code == 200
    _add_completed_classes(
        "modality-campaign@example.com",
        day_offsets=list(range(20)),
        classes_per_day=[1] * 20,
    )

    curriculum = get_level("A1")
    assert curriculum is not None
    skill = curriculum.skills[0]

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "modality-campaign@example.com"))
        link = db.scalar(
            select(AccountStudyProfile).where(AccountStudyProfile.account_id == account.id)
        )
        assert account is not None and link is not None
        now = datetime.now(timezone.utc)
        session = ClassSession(
            study_profile_id=link.study_profile_id,
            account_id=account.id,
            status=ClassSessionStatus.COMPLETED,
            kind=SessionKind.CLASS,
            target_level="A1",
            evaluated_at=now,
        )
        db.add(session)
        db.flush()
        for position in range(2):
            exercise = Exercise(
                class_session_id=session.id,
                study_profile_id=link.study_profile_id,
                position=position,
                level="A1",
                area=skill.area_key,
                skill_key=skill.key,
                exercise_type="multiple_choice",
                prompt=f"Listen {position}",
                presentation_mode=PresentationMode.LISTEN,
                response_mode=ResponseMode.SELECT,
                evaluation_mode=EvaluationMode.DETERMINISTIC,
            )
            db.add(exercise)
            db.flush()
            db.add(
                Attempt(
                    exercise_id=exercise.id,
                    study_profile_id=link.study_profile_id,
                    account_id=account.id,
                    attempt_number=1,
                    raw_answer="a",
                    normalized_answer="a",
                    response_mode=ResponseMode.SELECT,
                    score=100,
                    evaluated_at=now,
                )
            )
        db.commit()

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {"field": "CLASSES_COMPLETED", "operator": "GTE", "value": 20, "windowDays": 30},
            {"field": "SPEAKING_RESPONSES", "operator": "EQ", "value": 0},
            {"field": "LISTENING_RESPONSES", "operator": "GTE", "value": 2},
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    values = {row["field"]: row["actual"] for row in body["sample"][0]["rules"]}
    assert values["SPEAKING_RESPONSES"] == 0
    assert values["LISTENING_RESPONSES"] == 2


def test_preview_counts_ai_failures_with_compound_filters(client) -> None:
    login(client, "ai-failures-campaign@example.com")
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        account = db.scalar(
            select(Account).where(Account.email == "ai-failures-campaign@example.com")
        )
        assert account is not None
        selected = [
            ("INVALID_CREDENTIALS", "generate_class"),
            ("INVALID_CREDENTIALS", "generate_class"),
            ("QUOTA_EXCEEDED", "generate_class"),
        ]
        excluded = [
            (AIConnectionOwnerType.ACCOUNT, "NETWORK_ERROR", "generate_class"),
            (AIConnectionOwnerType.ACCOUNT, "QUOTA_EXCEEDED", "transcribe_audio"),
            (AIConnectionOwnerType.PLATFORM, "INVALID_CREDENTIALS", "generate_class"),
        ]
        for error_code, operation in selected:
            db.add(
                AIUsageEvent(
                    owner_type=AIConnectionOwnerType.ACCOUNT,
                    provider="MOCK",
                    account_id=account.id,
                    operation=operation,
                    success=False,
                    error_code=error_code,
                    created_at=now - timedelta(days=1),
                )
            )
        for owner_type, error_code, operation in excluded:
            db.add(
                AIUsageEvent(
                    owner_type=owner_type,
                    provider="MOCK",
                    account_id=account.id,
                    operation=operation,
                    success=False,
                    error_code=error_code,
                    created_at=now - timedelta(days=1),
                )
            )
        db.commit()

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {
                "field": "AI_FAILURES_COUNT",
                "filters": {
                    "ownerType": "ACCOUNT",
                    "errorCode": "CREDENTIAL_OR_QUOTA",
                    "operation": "generate_class",
                },
                "operator": "GTE",
                "value": 3,
                "windowDays": 7,
            }
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    result = body["sample"][0]["rules"][0]
    assert result["actual"] == 3
    assert result["matched"] is True
    assert result["filters"] == {
        "ownerType": "ACCOUNT",
        "errorCode": "CREDENTIAL_OR_QUOTA",
        "operation": "generate_class",
    }

    invalid = _preview(
        client,
        owner,
        benefit_id,
        [
            {
                "field": "AI_FAILURES_COUNT",
                "filters": {"ownerType": "BYOK"},
                "operator": "GTE",
                "value": 1,
                "windowDays": 7,
            }
        ],
    )
    assert invalid.status_code == 422
    assert "filtro" in invalid.text.lower()


def test_preview_detects_byok_configured_but_never_used_successfully(client) -> None:
    login(client, "byok-never-activated@example.com")
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        account = db.scalar(
            select(Account).where(Account.email == "byok-never-activated@example.com")
        )
        assert account is not None
        connection = AIConnection(
            owner_type=AIConnectionOwnerType.ACCOUNT,
            owner_id=account.id,
            provider="MOCK",
            name="BYOK sin activar",
            model="mock",
            active=True,
            created_at=now - timedelta(days=8),
        )
        db.add(connection)
        db.flush()
        # Un health check exitoso demuestra que la key respondió, pero no que el alumno
        # haya logrado usarla en una operación real.
        db.add(
            AIUsageEvent(
                connection_id=connection.id,
                owner_type=AIConnectionOwnerType.ACCOUNT,
                provider="MOCK",
                model="mock",
                account_id=account.id,
                operation="health_check",
                success=True,
                created_at=now - timedelta(days=7),
            )
        )
        db.commit()

    owner = _owner(client)
    benefit_id = _welcome_benefit_id(client, owner)
    response = _preview(
        client,
        owner,
        benefit_id,
        [
            {
                "field": "DAYS_SINCE_BYOK_CONFIGURED_WITHOUT_SUCCESS",
                "operator": "GTE",
                "value": 7,
            }
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligibleCount"] == 1
    result = body["sample"][0]["rules"][0]
    assert result["actual"] >= 7
    assert result["matched"] is True

    with SessionLocal() as db:
        account = db.scalar(
            select(Account).where(Account.email == "byok-never-activated@example.com")
        )
        connection = db.scalar(
            select(AIConnection).where(
                AIConnection.owner_type == AIConnectionOwnerType.ACCOUNT,
                AIConnection.owner_id == account.id,
            )
        )
        assert account is not None and connection is not None
        db.add(
            AIUsageEvent(
                connection_id=connection.id,
                owner_type=AIConnectionOwnerType.ACCOUNT,
                provider="MOCK",
                model="mock",
                account_id=account.id,
                operation="generate_class",
                success=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    after_success = _preview(
        client,
        owner,
        benefit_id,
        [
            {
                "field": "DAYS_SINCE_BYOK_CONFIGURED_WITHOUT_SUCCESS",
                "operator": "GTE",
                "value": 7,
            }
        ],
    )
    assert after_success.status_code == 200, after_success.text
    assert after_success.json()["eligibleCount"] == 0
    result = after_success.json()["sample"][0]["rules"][0]
    assert result["actual"] is None
    assert result["matched"] is False


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


def test_campaign_assist_generic_benefit_is_form_selection_not_semantic_blocker(
    client, monkeypatch
) -> None:
    import app.platform.campaigns_api as campaigns_api

    owner = _owner(client)
    _welcome_benefit_id(client, owner)

    fake = {
        "draft": {
            "name": "Argentina · invitación · próximo vencimiento",
            "benefitId": None,
            "action": "GRANT_BENEFIT",
            "actionConfig": {},
            "trigger": "LOGIN",
            "rules": [
                {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
                {"field": "DOCUMENT_COUNTRY", "operator": "EQ", "value": "AR"},
                {"field": "SUBSCRIPTION_ORIGIN", "operator": "EQ", "value": "INVITATION"},
                {"field": "DAYS_UNTIL_SERVICE_EXPIRES", "operator": "LTE", "value": 7},
            ],
            "priority": 100,
            "stackable": False,
            "maxRecipients": None,
            "startsAt": None,
            "endsAt": None,
            "notification": "IN_APP",
            "message": None,
        },
        "requirements": [
            {
                "text": "Usuarios personales",
                "kind": "RULE",
                "status": "REPRESENTED",
                "capability": "ACCOUNT_TYPE",
            },
            {
                "text": "Documento de Argentina",
                "kind": "RULE",
                "status": "REPRESENTED",
                "capability": "DOCUMENT_COUNTRY",
            },
            {
                "text": "Servicio actual mediante invitación",
                "kind": "RULE",
                "status": "REPRESENTED",
                "capability": "SUBSCRIPTION_ORIGIN",
            },
            {
                "text": "Servicio vence dentro de 7 días",
                "kind": "RULE",
                "status": "REPRESENTED",
                "capability": "DAYS_UNTIL_SERVICE_EXPIRES",
            },
            {
                "text": "Ejecutar al ingresar",
                "kind": "TRIGGER",
                "status": "REPRESENTED",
                "capability": "LOGIN",
            },
            {
                "text": "Dar un beneficio",
                "kind": "ACTION",
                "status": "REPRESENTED",
                "capability": "GRANT_BENEFIT",
            },
            {
                "text": "Beneficio a otorgar",
                "kind": "BENEFIT",
                "status": "UNSUPPORTED",
                "capability": None,
            },
        ],
        "warnings": [],
        "summary": "Borrador representable; falta elegir el beneficio en el formulario.",
    }

    monkeypatch.setattr(
        campaigns_api,
        "run_platform_json_task",
        lambda *args, **kwargs: SimpleNamespace(data=fake),
    )

    response = client.post(
        f"{API}/platform/campaigns/assist",
        headers=owner,
        json={
            "description": (
                "Quiero dar un beneficio a usuarios personales cuyo documento sea de Argentina, "
                "que hayan obtenido su servicio actual mediante una invitación y cuyo servicio "
                "venza dentro de 7 días o menos. Ejecutarla cuando vuelvan a ingresar."
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["draft"]["benefitId"] is None
    assert body["draft"]["action"] == "GRANT_BENEFIT"
    assert body["executable"] is True
    assert body["blockingIssues"] == []
    benefit_requirement = next(
        item for item in body["requirements"] if item["kind"] == "BENEFIT"
    )
    assert benefit_requirement["status"] == "REPRESENTED"
    assert benefit_requirement["verified"] is True


def test_campaign_assist_specific_unresolved_benefit_remains_blocking(
    client, monkeypatch
) -> None:
    import app.platform.campaigns_api as campaigns_api

    owner = _owner(client)
    _welcome_benefit_id(client, owner)

    fake = {
        "draft": {
            "name": "Beneficio concreto",
            "benefitId": None,
            "action": "GRANT_BENEFIT",
            "actionConfig": {},
            "trigger": "LOGIN",
            "rules": [{"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"}],
            "priority": 100,
            "stackable": False,
            "maxRecipients": None,
            "startsAt": None,
            "endsAt": None,
            "notification": "IN_APP",
            "message": None,
        },
        "requirements": [
            {
                "text": "Usuarios personales",
                "kind": "RULE",
                "status": "REPRESENTED",
                "capability": "ACCOUNT_TYPE",
            },
            {
                "text": "Ejecutar al ingresar",
                "kind": "TRIGGER",
                "status": "REPRESENTED",
                "capability": "LOGIN",
            },
            {
                "text": "Otorgar beneficio",
                "kind": "ACTION",
                "status": "REPRESENTED",
                "capability": "GRANT_BENEFIT",
            },
            {
                "text": "Beneficio Plataforma 7 días",
                "kind": "BENEFIT",
                "status": "UNSUPPORTED",
                "capability": None,
            },
        ],
        "warnings": [],
        "summary": "No se pudo resolver el beneficio concreto.",
    }

    monkeypatch.setattr(
        campaigns_api,
        "run_platform_json_task",
        lambda *args, **kwargs: SimpleNamespace(data=fake),
    )

    response = client.post(
        f"{API}/platform/campaigns/assist",
        headers=owner,
        json={
            "description": (
                "Quiero dar exactamente el beneficio Plataforma 7 días "
                "a usuarios personales cuando ingresen."
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["executable"] is False
    assert any("Beneficio Plataforma 7 días" in issue for issue in body["blockingIssues"])


def test_campaign_assist_discount_stays_unsupported_instead_of_becoming_benefit(
    client, monkeypatch
) -> None:
    import app.platform.campaigns_api as campaigns_api

    owner = _owner(client)
    _welcome_benefit_id(client, owner)

    fake = {
        "draft": {
            "name": "Descuento inválido",
            "benefitId": None,
            "action": "GRANT_BENEFIT",
            "actionConfig": {},
            "trigger": "LOGIN",
            "rules": [{"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"}],
            "priority": 100,
            "stackable": False,
            "maxRecipients": None,
            "startsAt": None,
            "endsAt": None,
            "notification": "IN_APP",
            "message": None,
        },
        "requirements": [
            {
                "text": "Usuarios personales",
                "kind": "RULE",
                "status": "REPRESENTED",
                "capability": "ACCOUNT_TYPE",
            },
            {
                "text": "Ejecutar al ingresar",
                "kind": "TRIGGER",
                "status": "REPRESENTED",
                "capability": "LOGIN",
            },
            {
                "text": "Aplicar 20% de descuento",
                "kind": "ACTION",
                "status": "UNSUPPORTED",
                "capability": None,
            },
        ],
        "warnings": [],
        "summary": "El descuento no es una acción disponible.",
    }

    monkeypatch.setattr(
        campaigns_api,
        "run_platform_json_task",
        lambda *args, **kwargs: SimpleNamespace(data=fake),
    )

    response = client.post(
        f"{API}/platform/campaigns/assist",
        headers=owner,
        json={"description": "Dar 20% de descuento a usuarios personales cuando ingresen."},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["executable"] is False
    combined = " ".join(body["blockingIssues"] + body["warnings"]).lower()
    assert "descuento" in combined or "precio" in combined


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
