"""Beneficios reutilizables de T-004.

Un beneficio define QUÉ se otorga (servicio + duración). Campañas e invitaciones deciden
CUÁNDO/A QUIÉN o CÓMO se reclama, respectivamente.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.benefits.models import Benefit
from app.subscriptions.models import Plan, Subscription, SubscriptionOrigin
from app.subscriptions.service import effective_service, grant_service, seed_services

WELCOME_BENEFIT_CODE = "WELCOME_PLATFORM_3D"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def seed_benefits(db: Session) -> None:
    """Crea el beneficio base de bienvenida si todavía no existe."""
    seed_services(db)
    existing = db.scalar(select(Benefit).where(Benefit.code == WELCOME_BENEFIT_CODE))
    if existing is not None:
        return
    plan = db.scalar(select(Plan).where(Plan.code == "INDIVIDUAL_PLATFORM"))
    if plan is None:
        return
    db.add(
        Benefit(
            code=WELCOME_BENEFIT_CODE,
            name="Plataforma · 3 días",
            plan_id=plan.id,
            duration_days=3,
            active=True,
        )
    )
    db.flush()


def benefit_duration(benefit: Benefit, plan: Plan | None = None) -> int | None:
    """Duración definida únicamente por el beneficio.

    `plan` se mantiene temporalmente en la firma para no duplicar cambios en los consumidores;
    ya no participa de la decisión.
    """
    return benefit.duration_days


def benefit_summary(benefit: Benefit, plan: Plan) -> str:
    days = benefit_duration(benefit, plan)
    return f"{plan.name} · {days} días" if days else f"{plan.name} · sin vencimiento"


@dataclass(frozen=True)
class BenefitApplication:
    subscription: Subscription | None
    summary: str
    error: str | None = None

    @property
    def applied(self) -> bool:
        return self.subscription is not None


def apply_service_benefit(
    db: Session,
    benefit: Benefit,
    account: Account,
    *,
    granted_by: Account | None,
    origin: SubscriptionOrigin,
    note: str | None = None,
) -> BenefitApplication:
    """Aplica un beneficio sin reemplazar silenciosamente otro servicio distinto.

    Política actual (conservadora):
    - sin servicio otorgado: crea una suscripción con grant_service;
    - mismo servicio: suma días (o lo deja sin vencimiento si el beneficio no vence);
    - servicio distinto: no aplica. Una futura política explícita decidirá reemplazo/crédito.
    """
    plan = db.get(Plan, benefit.plan_id)
    if plan is None or not plan.active or not benefit.active:
        return BenefitApplication(None, benefit.name, "El beneficio o su servicio no está activo.")

    summary = benefit_summary(benefit, plan)
    current = effective_service(db, account)
    duration = benefit_duration(benefit, plan)
    now = utcnow()

    if current.granted:
        if current.plan_id != plan.id or current.subscription_id is None:
            return BenefitApplication(
                None,
                summary,
                "La cuenta ya tiene otro servicio otorgado. El beneficio no reemplaza servicios distintos.",
            )
        subscription = db.get(Subscription, current.subscription_id)
        if subscription is None:
            return BenefitApplication(None, summary, "No se pudo localizar el servicio vigente.")
        if duration is None:
            subscription.expires_at = None
        else:
            expiry = _as_utc(subscription.expires_at)
            base = expiry if expiry and expiry > now else now
            subscription.expires_at = base + timedelta(days=duration)
        db.flush()
        return BenefitApplication(subscription, summary)

    subscription = grant_service(
        db,
        account,
        plan,
        granted_by=granted_by,
        days=duration,
        origin=origin,
        note=note,
    )
    return BenefitApplication(subscription, summary)
