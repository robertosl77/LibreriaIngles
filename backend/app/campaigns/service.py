"""Motor de campañas de T-004, etapa 2.

La campaña define CUÁNDO/A QUIÉN; el beneficio reusable define QUÉ servicio/duración se otorga.
T-059 agregará el scheduler para CampaignTrigger.SCHEDULED sin cambiar este contrato.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.models import Account, AccountStatus, AccountType, PlatformRole
from app.benefits.models import Benefit
from app.benefits.service import (
    BenefitApplication,
    apply_service_benefit,
    seed_benefits,
)
from app.campaigns.models import (
    Campaign,
    CampaignAction,
    CampaignGrant,
    CampaignSeedMarker,
    CampaignNotification,
    CampaignStatus,
    CampaignTrigger,
)
from app.learning.models import ClassSession, ClassSessionStatus, SessionKind
from app.memberships.models import Membership, MembershipStatus
from app.study_profiles.models import (
    AccountStudyProfile,
    AccountStudyProfileStatus,
    StudyProfile,
    StudyProfileStatus,
)
from app.subscriptions.models import Subscription, SubscriptionOrigin, SubscriptionStatus
from app.subscriptions.service import effective_service

WELCOME_CODE = "WELCOME_PLATFORM"
WELCOME_BENEFIT_CODE = "WELCOME_PLATFORM_3D"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def seed_campaigns(db: Session) -> None:
    """Crea una sola vez la campaña ejemplo de bienvenida como BORRADOR."""
    marker = db.get(CampaignSeedMarker, WELCOME_CODE)
    if marker is not None:
        return

    existing = db.scalar(select(Campaign).where(Campaign.code == WELCOME_CODE))
    if existing is not None:
        db.add(CampaignSeedMarker(code=WELCOME_CODE))
        db.flush()
        return

    seed_benefits(db)
    benefit = db.scalar(select(Benefit).where(Benefit.code == WELCOME_BENEFIT_CODE))
    if benefit is None:
        return

    db.add(CampaignSeedMarker(code=WELCOME_CODE))
    db.add(
        Campaign(
            code=WELCOME_CODE,
            name="Bienvenida · 3 días de Plataforma",
            benefit_id=benefit.id,
            status=CampaignStatus.DRAFT,
            trigger=CampaignTrigger.FIRST_LOGIN,
            eligibility={
                "mode": "ALL",
                "rules": [
                    {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
                    {"field": "HAS_GRANTED_SERVICE", "operator": "EQ", "value": False},
                ],
            },
            priority=100,
            stackable=False,
            notification=CampaignNotification.IN_APP,
            message="Bienvenido: tenés 3 días para probar la IA de Librería Inglés.",
        )
    )
    db.flush()


def _scope_matches(db: Session, campaign: Campaign, account: Account) -> bool:
    if campaign.organization_id is None:
        return True
    return (
        db.scalar(
            select(Membership.id).where(
                Membership.account_id == account.id,
                Membership.organization_id == campaign.organization_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        is not None
    )


def _within_window(campaign: Campaign, now: datetime) -> bool:
    starts = _as_utc(campaign.starts_at)
    ends = _as_utc(campaign.ends_at)
    return (starts is None or starts <= now) and (ends is None or now < ends)


def _first_login_matches(campaign: Campaign, account: Account) -> bool:
    first_login = _as_utc(account.first_login_at)
    activated = _as_utc(campaign.activated_at)
    if first_login is None or activated is None or first_login < activated:
        return False

    starts = _as_utc(campaign.starts_at)
    ends = _as_utc(campaign.ends_at)
    if starts is not None and first_login < starts:
        return False
    if ends is not None and first_login >= ends:
        return False
    return True


def _compare_number(actual: int | float, operator: str, expected: int | float) -> bool:
    if operator == "EQ":
        return actual == expected
    if operator == "GTE":
        return actual >= expected
    if operator == "LTE":
        return actual <= expected
    return False


def _days_since(value: datetime | None, now: datetime) -> int | None:
    value = _as_utc(value)
    if value is None:
        return None
    return max(0, int((now - value).total_seconds() // 86400))


def _last_activity_at(db: Session, account: Account) -> datetime | None:
    return db.scalar(
        select(func.max(ClassSession.evaluated_at)).where(
            ClassSession.account_id == account.id,
            ClassSession.kind == SessionKind.CLASS,
            ClassSession.status == ClassSessionStatus.COMPLETED,
            ClassSession.evaluated_at.is_not(None),
        )
    )


def _last_expired_service_at(db: Session, account: Account) -> datetime | None:
    # Fuerza el vencimiento perezoso antes de consultar el histórico.
    effective_service(db, account)
    rows = db.scalars(
        select(Subscription)
        .where(
            Subscription.account_id == account.id,
            Subscription.status == SubscriptionStatus.EXPIRED,
        )
        .order_by(Subscription.ended_at.desc(), Subscription.expires_at.desc(), Subscription.id.desc())
    ).all()
    if not rows:
        return None
    latest = rows[0]
    return latest.ended_at or latest.expires_at


def _current_level(db: Session, account: Account) -> str | None:
    row = db.execute(
        select(AccountStudyProfile, StudyProfile)
        .join(StudyProfile, StudyProfile.id == AccountStudyProfile.study_profile_id)
        .where(
            AccountStudyProfile.account_id == account.id,
            AccountStudyProfile.status == AccountStudyProfileStatus.ACTIVE,
            StudyProfile.status == StudyProfileStatus.ACTIVE,
        )
        .order_by(AccountStudyProfile.linked_at.desc())
    ).first()
    if row is None:
        return None
    _, profile = row
    return profile.operational_level or profile.selected_level or profile.estimated_level


def rule_evaluation(
    db: Session,
    account: Account,
    rule: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Evalúa una condición y devuelve evidencia explicable para preview/auditoría."""
    now = now or utcnow()
    field = str(rule.get("field", "")).upper()
    operator = str(rule.get("operator", "EQ")).upper()
    expected = rule.get("value")
    actual = None

    if field == "ACCOUNT_TYPE":
        actual = account.account_type.value
        matched = operator == "EQ" and actual == str(expected).upper()
    elif field in {"HAS_GRANTED_SERVICE", "SERVICE_SOURCE"}:
        service = effective_service(db, account)
        if field == "HAS_GRANTED_SERVICE":
            actual = service.granted
            matched = operator == "EQ" and actual == bool(expected)
        else:
            actual = service.source.value
            matched = operator == "EQ" and actual == str(expected).upper()
    elif field == "EMAIL_DOMAIN":
        actual = account.email.rsplit("@", 1)[-1].lower() if "@" in account.email else ""
        matched = operator == "EQ" and actual == str(expected).strip().lower()
    elif field == "DAYS_SINCE_CREATED":
        actual = _days_since(account.created_at, now)
        try:
            matched = actual is not None and _compare_number(actual, operator, int(expected))
        except (TypeError, ValueError):
            matched = False
    elif field == "CREATED_AT":
        actual_dt = _as_utc(account.created_at)
        actual = actual_dt.isoformat() if actual_dt else None
        try:
            expected_dt = _as_utc(datetime.fromisoformat(str(expected).replace("Z", "+00:00")))
            if operator == "GTE":
                matched = actual_dt is not None and actual_dt >= expected_dt
            elif operator == "LTE":
                matched = actual_dt is not None and actual_dt <= expected_dt
            else:
                matched = actual_dt is not None and actual_dt == expected_dt
        except (TypeError, ValueError):
            matched = False
    elif field == "DAYS_SINCE_LAST_ACTIVITY":
        last_activity = _last_activity_at(db, account)
        actual = _days_since(last_activity, now)
        try:
            matched = actual is not None and _compare_number(actual, operator, int(expected))
        except (TypeError, ValueError):
            matched = False
    elif field == "NEVER_STUDIED":
        actual = _last_activity_at(db, account) is None
        matched = operator == "EQ" and actual == bool(expected)
    elif field == "DAYS_SINCE_SERVICE_EXPIRED":
        actual = _days_since(_last_expired_service_at(db, account), now)
        try:
            matched = actual is not None and _compare_number(actual, operator, int(expected))
        except (TypeError, ValueError):
            matched = False
    elif field == "CURRENT_LEVEL":
        actual = _current_level(db, account)
        matched = operator == "EQ" and actual == str(expected).upper()
    else:
        matched = False

    return {
        "field": field,
        "operator": operator,
        "expected": expected,
        "actual": actual,
        "matched": bool(matched),
    }


def _rule_matches(db: Session, account: Account, rule: dict, now: datetime) -> bool:
    return bool(rule_evaluation(db, account, rule, now=now)["matched"])


def preview_audience(
    db: Session,
    *,
    rules: list[dict],
    trigger: CampaignTrigger,
    campaign_id: int | None = None,
    sample_limit: int = 10,
) -> dict:
    """Simula audiencia sin aplicar beneficio ni crear grants.

    Para FIRST_LOGIN de una campaña nueva, solo son candidatos prospectivos quienes todavía
    no hicieron su primer login. Para una campaña ya activada se respeta activated_at.
    """
    now = utcnow()
    campaign = db.get(Campaign, campaign_id) if campaign_id else None
    accounts = db.scalars(
        select(Account)
        .where(
            Account.status == AccountStatus.ACTIVE,
            Account.account_type == AccountType.PERSONAL,
            Account.platform_role.is_(None),
        )
        .order_by(Account.id)
    ).all()

    rows: list[dict] = []
    for account in accounts:
        evaluations = [rule_evaluation(db, account, rule, now=now) for rule in rules]
        conditions_match = all(item["matched"] for item in evaluations)

        already_received = False
        if campaign_id is not None:
            already_received = db.scalar(
                select(CampaignGrant.id).where(
                    CampaignGrant.campaign_id == campaign_id,
                    CampaignGrant.account_id == account.id,
                )
            ) is not None

        if trigger == CampaignTrigger.FIRST_LOGIN:
            if campaign is not None and campaign.activated_at is not None:
                trigger_match = _first_login_matches(campaign, account)
            else:
                trigger_match = account.first_login_at is None
        else:
            # LOGIN y SCHEDULED dependen del evento/scheduler; el preview responde quién
            # cumple las condiciones ahora.
            trigger_match = True

        eligible_now = conditions_match and trigger_match and not already_received
        rows.append(
            {
                "accountId": account.id,
                "email": account.email,
                "displayName": account.display_name,
                "eligible": eligible_now,
                "alreadyReceived": already_received,
                "triggerMatch": trigger_match,
                "rules": evaluations,
            }
        )

    eligible_rows = [row for row in rows if row["eligible"]]
    excluded_rows = [row for row in rows if not row["eligible"]]
    sample = (eligible_rows[:sample_limit] + excluded_rows[: max(0, sample_limit - len(eligible_rows[:sample_limit]))])[:sample_limit]
    warnings: list[str] = []
    if trigger == CampaignTrigger.SCHEDULED:
        warnings.append("La audiencia se puede simular, pero SCHEDULED requiere el scheduler de T-059 para ejecutarse.")
    if trigger == CampaignTrigger.FIRST_LOGIN and campaign is None:
        warnings.append("Para una campaña nueva de primer login, el preview cuenta solo cuentas que aún no ingresaron por primera vez.")

    return {
        "candidateCount": len(rows),
        "eligibleCount": len(eligible_rows),
        "excludedCount": len(excluded_rows),
        "sample": sample,
        "warnings": warnings,
    }


def _available_for_account(
    db: Session, campaign: Campaign, account: Account, *, now: datetime
) -> bool:
    if (
        campaign.deleted_at is not None
        or campaign.status != CampaignStatus.ACTIVE
        or not _within_window(campaign, now)
    ):
        return False
    if not _scope_matches(db, campaign, account):
        return False
    return db.scalar(
        select(CampaignGrant.id).where(
            CampaignGrant.campaign_id == campaign.id,
            CampaignGrant.account_id == account.id,
        )
    ) is None


def eligible(db: Session, campaign: Campaign, account: Account, *, now: datetime | None = None) -> bool:
    now = now or utcnow()
    if not _available_for_account(db, campaign, account, now=now):
        return False
    if campaign.trigger == CampaignTrigger.FIRST_LOGIN and not _first_login_matches(campaign, account):
        return False
    eligibility = campaign.eligibility or {"mode": "ALL", "rules": []}
    if str(eligibility.get("mode", "ALL")).upper() != "ALL":
        return False
    return all(_rule_matches(db, account, rule, now) for rule in eligibility.get("rules", []))


def _notification_message(campaign: Campaign, benefit: str) -> str:
    return (campaign.message or "").strip() or f'Recibiste la campaña "{campaign.name}": {benefit}.'


def _apply_benefit(db: Session, campaign: Campaign, account: Account) -> BenefitApplication | None:
    benefit = db.get(Benefit, campaign.benefit_id)
    if benefit is None:
        return None
    creator = db.get(Account, campaign.created_by_account_id) if campaign.created_by_account_id else None
    return apply_service_benefit(
        db,
        benefit,
        account,
        granted_by=creator,
        origin=SubscriptionOrigin.CAMPAIGN,
        note=f"Campaña #{campaign.id}: {campaign.name}",
    )


def apply_campaign(
    db: Session,
    campaign: Campaign,
    account: Account,
    *,
    conditions_prechecked: bool = False,
) -> CampaignGrant | None:
    """Reserva cupo, aplica el beneficio y registra nunca_recibió(campaña)."""
    locked = db.scalar(select(Campaign).where(Campaign.id == campaign.id).with_for_update())
    now = utcnow()
    if locked is None or not _available_for_account(db, locked, account, now=now):
        return None
    if not conditions_prechecked and not eligible(db, locked, account, now=now):
        return None
    if locked.max_recipients is not None:
        used = db.scalar(
            select(func.count(CampaignGrant.id)).where(CampaignGrant.campaign_id == locked.id)
        ) or 0
        if int(used) >= locked.max_recipients:
            return None

    if locked.action != CampaignAction.GRANT_BENEFIT:
        # T-065 modela acciones futuras, pero solo GRANT_BENEFIT está habilitada hoy.
        return None

    application = _apply_benefit(db, locked, account)
    if application is None or not application.applied or application.subscription is None:
        return None

    notification = locked.notification
    grant = CampaignGrant(
        campaign_id=locked.id,
        account_id=account.id,
        subscription_id=application.subscription.id,
        benefit_summary=application.summary,
        notification_message=(
            _notification_message(locked, application.summary)
            if notification in {CampaignNotification.IN_APP, CampaignNotification.IN_APP_EMAIL}
            else None
        ),
        email_status=(
            "PENDING"
            if notification in {CampaignNotification.EMAIL, CampaignNotification.IN_APP_EMAIL}
            else None
        ),
    )
    db.add(grant)
    db.flush()
    return grant


def _evaluate_campaigns(
    db: Session,
    account: Account,
    *,
    triggers: list[CampaignTrigger],
) -> list[CampaignGrant]:
    if account.platform_role == PlatformRole.PLATFORM_OWNER:
        return []
    seed_campaigns(db)
    now = utcnow()
    campaigns = db.scalars(
        select(Campaign)
        .where(
            Campaign.status == CampaignStatus.ACTIVE,
            Campaign.deleted_at.is_(None),
            Campaign.trigger.in_(triggers),
        )
        .order_by(Campaign.priority.asc(), Campaign.id.asc())
    ).all()

    candidates = [campaign for campaign in campaigns if eligible(db, campaign, account, now=now)]

    applied: list[CampaignGrant] = []
    applied_campaigns: list[Campaign] = []
    for campaign in candidates:
        if applied_campaigns and (
            not campaign.stackable or any(not previous.stackable for previous in applied_campaigns)
        ):
            continue
        grant = apply_campaign(db, campaign, account, conditions_prechecked=True)
        if grant is None:
            continue
        applied.append(grant)
        applied_campaigns.append(campaign)
        if not campaign.stackable:
            break
    return applied


def evaluate_login_campaigns(
    db: Session,
    account: Account,
    *,
    first_login: bool | None = None,
) -> list[CampaignGrant]:
    return _evaluate_campaigns(
        db,
        account,
        triggers=[CampaignTrigger.FIRST_LOGIN, CampaignTrigger.LOGIN],
    )


def reconcile_first_login_campaigns(db: Session, account: Account) -> list[CampaignGrant]:
    return _evaluate_campaigns(db, account, triggers=[CampaignTrigger.FIRST_LOGIN])


def pending_in_app_notices(db: Session, account: Account) -> list[dict]:
    rows = db.execute(
        select(CampaignGrant, Campaign)
        .join(Campaign, Campaign.id == CampaignGrant.campaign_id)
        .where(
            CampaignGrant.account_id == account.id,
            CampaignGrant.notification_message.is_not(None),
            CampaignGrant.in_app_read_at.is_(None),
        )
        .order_by(CampaignGrant.applied_at.desc(), CampaignGrant.id.desc())
    ).all()
    return [
        {
            "grantId": grant.id,
            "campaignId": campaign.id,
            "campaign": campaign.name,
            "message": grant.notification_message,
            "benefit": grant.benefit_summary,
            "appliedAt": grant.applied_at,
        }
        for grant, campaign in rows
    ]


def mark_notice_read(db: Session, account: Account, grant_id: int) -> bool:
    grant = db.scalar(
        select(CampaignGrant).where(
            CampaignGrant.id == grant_id,
            CampaignGrant.account_id == account.id,
            CampaignGrant.notification_message.is_not(None),
        )
    )
    if grant is None:
        return False
    if grant.in_app_read_at is None:
        grant.in_app_read_at = utcnow()
        db.flush()
    return True
