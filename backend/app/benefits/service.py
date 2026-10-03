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

# Beneficios de laboratorio T-065. Solo se crean cuando el motor los solicita explícitamente
# desde un entorno local/dev; nunca forman parte del seed de producción.
FIDELITY_LAB_BENEFITS = (
    ("LAB_FID_6M_AVG5", "LAB · Permanencia 6 meses + promedio alto", "INDIVIDUAL_PLATFORM", 14),
    ("LAB_FID_1Y", "LAB · Aniversario 1 año", "INDIVIDUAL_PLATFORM", 21),
    ("LAB_FID_DAILY_7", "LAB · Constancia diaria 7 días", "INDIVIDUAL_PLATFORM", 7),
    ("LAB_FID_STREAK_14", "LAB · Racha 14 días", "INDIVIDUAL_PLATFORM", 10),
    ("LAB_FID_ACTIVE_20", "LAB · Alta presencia mensual", "INDIVIDUAL_PLATFORM", 10),
    ("LAB_FID_VOLUME_50", "LAB · Volumen mensual", "INDIVIDUAL_PLATFORM", 7),
    ("LAB_FID_A1_INTENSE", "LAB · Impulso A1 intensivo", "INDIVIDUAL_PLATFORM", 7),
    ("LAB_FID_WINBACK_30", "LAB · Regreso 30 días", "INDIVIDUAL_PLATFORM", 5),
    ("LAB_FID_WINBACK_90", "LAB · Regreso 90 días", "INDIVIDUAL_PLATFORM", 14),
    ("LAB_FID_EXPIRED_30", "LAB · Servicio vencido 30 días", "INDIVIDUAL_PLATFORM", 10),
    ("LAB_FID_NEVER_STARTED", "LAB · Primera práctica", "INDIVIDUAL_PLATFORM", 3),
    ("LAB_FID_LOW_ACTIVITY", "LAB · Reactivación por baja actividad", "INDIVIDUAL_PLATFORM", 5),
    ("LAB_FID_BYOK_6M", "LAB · Fidelidad BYOK", "INDIVIDUAL_BYOK", 7),
    ("LAB_FID_HYBRID_ACTIVE", "LAB · Fidelidad híbrida", "INDIVIDUAL_HYBRID", 7),
    ("LAB_FID_COMPLAINT", "LAB · Compensación post-reclamo", "INDIVIDUAL_PLATFORM", 7),
)


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
            name="Bienvenida",
            plan_id=plan.id,
            duration_days=3,
            active=True,
        )
    )
    db.flush()


def seed_fidelity_lab_benefits(db: Session) -> dict[str, Benefit]:
    """Crea beneficios reutilizables del laboratorio T-065 de forma idempotente."""
    seed_services(db)
    existing = {
        benefit.code: benefit
        for benefit in db.scalars(
            select(Benefit).where(Benefit.code.in_([row[0] for row in FIDELITY_LAB_BENEFITS]))
        ).all()
    }
    plans = {
        plan.code: plan
        for plan in db.scalars(
            select(Plan).where(Plan.code.in_([row[2] for row in FIDELITY_LAB_BENEFITS]))
        ).all()
    }

    for code, name, plan_code, duration_days in FIDELITY_LAB_BENEFITS:
        if code in existing:
            continue
        plan = plans.get(plan_code)
        if plan is None:
            continue
        benefit = Benefit(
            code=code,
            name=name,
            plan_id=plan.id,
            duration_days=duration_days,
            active=True,
        )
        db.add(benefit)
        db.flush()
        existing[code] = benefit

    return existing


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
    replace_existing: bool = False,
) -> BenefitApplication:
    """Aplica un beneficio.

    Campañas/invitaciones conservan la política segura: mismo servicio extiende y un servicio
    distinto no se reemplaza silenciosamente. El otorgamiento manual del OWNER puede pedir
    reemplazo explícito, preservando la suscripción anterior como historial.
    """
    plan = db.get(Plan, benefit.plan_id)
    if plan is None or not plan.active or not benefit.active:
        return BenefitApplication(None, benefit.name, "El beneficio o su servicio no está activo.")

    summary = benefit_summary(benefit, plan)
    current = effective_service(db, account)
    duration = benefit_duration(benefit, plan)
    now = utcnow()

    if current.granted and replace_existing:
        subscription = grant_service(
            db,
            account,
            plan,
            granted_by=granted_by,
            days=duration,
            origin=origin,
            benefit_id=benefit.id,
            note=note,
        )
        return BenefitApplication(subscription, summary)

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
        subscription.benefit_id = benefit.id
        if note:
            subscription.note = note
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
        benefit_id=benefit.id,
        note=note,
    )
    return BenefitApplication(subscription, summary)
