"""Motor de campañas de T-004, etapa 2.

La campaña no conoce conceptos comerciales como "bienvenida" o "fidelización": combina trigger,
condiciones, prioridad/acumulabilidad, beneficio (servicio) y notificación. T-059 agregará el
scheduler para CampaignTrigger.SCHEDULED sin cambiar este contrato.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.models import Account, PlatformRole
from app.campaigns.models import (
    Campaign,
    CampaignGrant,
    CampaignNotification,
    CampaignStatus,
    CampaignTrigger,
)
from app.memberships.models import Membership, MembershipStatus
from app.subscriptions.models import Plan, Subscription, SubscriptionOrigin
from app.subscriptions.service import effective_service, grant_service

WELCOME_CODE = "WELCOME_PLATFORM"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def seed_campaigns(db: Session) -> None:
    """Crea la campaña ejemplo de bienvenida como BORRADOR; el OWNER decide cuándo activarla."""
    if db.scalar(select(Campaign.id).where(Campaign.code == WELCOME_CODE)) is not None:
        return
    plan = db.scalar(select(Plan).where(Plan.code == "INDIVIDUAL_PLATFORM"))
    if plan is None:
        return
    db.add(
        Campaign(
            code=WELCOME_CODE,
            name="Bienvenida · 3 días de Plataforma",
            plan_id=plan.id,
            status=CampaignStatus.DRAFT,
            trigger=CampaignTrigger.FIRST_LOGIN,
            eligibility={
                "mode": "ALL",
                "rules": [
                    {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
                    {"field": "HAS_GRANTED_SERVICE", "operator": "EQ", "value": False},
                ],
            },
            grant_days=3,
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


def _first_login_matches(db: Session, campaign: Campaign, account: Account) -> bool:
    """FIRST_LOGIN se decide con hechos persistidos y no con un boolean efímero del request.

    Para campañas que ya estaban activas antes de que existiera activated_at, el backfill pudo
    quedar más tarde que el inicio real. Un beneficio ya otorgado es evidencia inequívoca de que la
    campaña estaba activa en ese momento, por lo que usamos el grant más antiguo como piso histórico
    conservador."""
    first_login = _as_utc(account.first_login_at)
    activated = _as_utc(campaign.activated_at)
    first_grant = _as_utc(
        db.scalar(
            select(CampaignGrant.applied_at)
            .where(CampaignGrant.campaign_id == campaign.id)
            .order_by(CampaignGrant.applied_at.asc(), CampaignGrant.id.asc())
            .limit(1)
        )
    )
    activation_floor = activated
    if first_grant is not None and (activation_floor is None or first_grant < activation_floor):
        activation_floor = first_grant

    if first_login is None or activation_floor is None or first_login < activation_floor:
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


def _rule_matches(db: Session, account: Account, rule: dict, now: datetime) -> bool:
    field = str(rule.get("field", "")).upper()
    operator = str(rule.get("operator", "EQ")).upper()
    expected = rule.get("value")

    if field == "ACCOUNT_TYPE":
        return operator == "EQ" and account.account_type.value == str(expected).upper()

    service = None
    if field in {"HAS_GRANTED_SERVICE", "SERVICE_SOURCE"}:
        service = effective_service(db, account)

    if field == "HAS_GRANTED_SERVICE":
        return operator == "EQ" and service.granted == bool(expected)

    if field == "SERVICE_SOURCE":
        return operator == "EQ" and service.source.value == str(expected).upper()

    if field == "EMAIL_DOMAIN":
        domain = account.email.rsplit("@", 1)[-1].lower() if "@" in account.email else ""
        return operator == "EQ" and domain == str(expected).strip().lower()

    if field == "DAYS_SINCE_CREATED":
        created = _as_utc(account.created_at) or now
        days = max(0, int((now - created).total_seconds() // 86400))
        try:
            return _compare_number(days, operator, int(expected))
        except (TypeError, ValueError):
            return False

    if field == "CREATED_AT":
        try:
            expected_dt = datetime.fromisoformat(str(expected).replace("Z", "+00:00"))
            expected_dt = _as_utc(expected_dt)
            actual = _as_utc(account.created_at) or now
        except ValueError:
            return False
        if operator == "GTE":
            return actual >= expected_dt
        if operator == "LTE":
            return actual <= expected_dt
        return operator == "EQ" and actual == expected_dt

    # Configuración desconocida: nunca otorgar por accidente.
    return False


def _available_for_account(
    db: Session, campaign: Campaign, account: Account, *, now: datetime
) -> bool:
    if campaign.status != CampaignStatus.ACTIVE or not _within_window(campaign, now):
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
    if campaign.trigger == CampaignTrigger.FIRST_LOGIN and not _first_login_matches(db, campaign, account):
        return False
    eligibility = campaign.eligibility or {"mode": "ALL", "rules": []}
    # Hoy solo ALL/AND. El JSON ya deja espacio para grupos OR cuando se defina su UX.
    if str(eligibility.get("mode", "ALL")).upper() != "ALL":
        return False
    return all(_rule_matches(db, account, rule, now) for rule in eligibility.get("rules", []))


def _benefit_summary(plan: Plan, days: int | None) -> str:
    return f"{plan.name} · {days} días" if days else f"{plan.name} · sin vencimiento"


def _notification_message(campaign: Campaign, benefit: str) -> str:
    return (campaign.message or "").strip() or f'Recibiste la campaña "{campaign.name}": {benefit}.'


def _apply_service(db: Session, campaign: Campaign, account: Account) -> Subscription | None:
    plan = db.get(Plan, campaign.plan_id)
    if plan is None or not plan.active:
        return None

    current = effective_service(db, account)
    duration = campaign.grant_days if campaign.grant_days is not None else plan.duration_days
    now = utcnow()

    if current.granted:
        # Una campaña nunca reemplaza silenciosamente un servicio diferente. Puede bonificar días
        # sobre el mismo servicio; para reemplazos explícitos habrá una acción/política propia.
        if current.plan_id != plan.id or current.subscription_id is None:
            return None
        subscription = db.get(Subscription, current.subscription_id)
        if subscription is None:
            return None
        if duration is None:
            subscription.expires_at = None
        else:
            expiry = _as_utc(subscription.expires_at)
            base = expiry if expiry and expiry > now else now
            subscription.expires_at = base + timedelta(days=duration)
        db.flush()
        return subscription

    creator = db.get(Account, campaign.created_by_account_id) if campaign.created_by_account_id else None
    return grant_service(
        db,
        account,
        plan,
        granted_by=creator,
        days=duration,
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
    """Reserva cupo, otorga el beneficio y registra nunca_recibió(campaña) en una transacción."""
    # Bloquea la fila en motores que soportan FOR UPDATE; SQLite serializa las escrituras.
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

    subscription = _apply_service(db, locked, account)
    if subscription is None:
        return None
    plan = db.get(Plan, locked.plan_id)
    duration = locked.grant_days if locked.grant_days is not None else plan.duration_days
    benefit = _benefit_summary(plan, duration)
    notification = locked.notification
    grant = CampaignGrant(
        campaign_id=locked.id,
        account_id=account.id,
        subscription_id=subscription.id,
        benefit_summary=benefit,
        notification_message=(
            _notification_message(locked, benefit)
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
            Campaign.trigger.in_(triggers),
        )
        .order_by(Campaign.priority.asc(), Campaign.id.asc())
    ).all()

    # Todas las condiciones se calculan sobre el mismo estado inicial para que las campañas
    # acumulables no se anulen entre sí por el beneficio recién otorgado.
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
    """Evalúa LOGIN y FIRST_LOGIN.

    FIRST_LOGIN se valida contra first_login_at + activated_at persistidos. Así puede reconciliarse
    en un request posterior sin hacerse retroactivo para cuentas que ingresaron antes de la campaña.
    """
    return _evaluate_campaigns(
        db,
        account,
        triggers=[CampaignTrigger.FIRST_LOGIN, CampaignTrigger.LOGIN],
    )


def reconcile_first_login_campaigns(db: Session, account: Account) -> list[CampaignGrant]:
    """Reintento seguro para campañas FIRST_LOGIN al cargar /me."""
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
