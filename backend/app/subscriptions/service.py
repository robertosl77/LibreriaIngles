"""Servicio vigente de cada cuenta (T-004, etapa 1).

Modelo (docs/tareas_pendientes_v0_1.md, T-004):
- VÍNCULO: personal (sin empresa) o corporativo (vía una empresa). Se deduce, no se elige.
- FUENTE DE IA: BYOK (propias keys) | PLATAFORMA (keys de sr.macros) | HÍBRIDO (propias primero).
- SERVICIO = vínculo + fuente + metadatos. No define vigencia ni límites de consumo.
- BENEFICIO = servicio + duración. Es la única capa que define por cuánto tiempo se otorga.
  Lo aplica sr.macros manualmente, una campaña, una invitación o un pago futuro.

Sin servicio otorgado vigente, la cuenta es "Individual · propias keys" (personal + BYOK): sigue
usando sus propias API keys, como hasta ahora. Cuando vence un servicio otorgado, vuelve a eso.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.subscriptions.models import (
    AISource,
    Plan,
    ServiceLinkType,
    Subscription,
    SubscriptionOrigin,
    SubscriptionStatus,
)

DEFAULT_CODE = "INDIVIDUAL_BYOK"
DEFAULT_SERVICES = [
    ("INDIVIDUAL_BYOK", "Individual · propias keys", AISource.BYOK, "Usás tus propias API keys."),
    ("INDIVIDUAL_PLATFORM", "Individual · Plataforma", AISource.PLATFORM, "Usás la IA de Librería Inglés."),
    (
        "INDIVIDUAL_HYBRID",
        "Individual · Híbrido",
        AISource.HYBRID,
        "Tus API keys primero; si fallan, la IA de Librería Inglés.",
    ),
]
# Aviso "tu servicio venció" visible durante estos días.
RECENT_EXPIRY = timedelta(days=14)


# Qué rol cumplen las keys propias según la fuente. Único lugar a tocar si aparece una fuente
# nueva: el frontend decide la pantalla por estas banderas, no por el nombre del servicio.
OWN_KEYS_ROLE = {
    AISource.BYOK: "required",  # sin keys propias no hay IA
    AISource.HYBRID: "optional",  # se usan primero; si no hay, plataforma (ver T-054)
    AISource.PLATFORM: "unused",  # se ignoran
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def seed_services(db: Session) -> None:
    """Crea los servicios iniciales si faltan (idempotente; la migración 0012 también los siembra)."""
    existing = set(db.scalars(select(Plan.code)).all())
    for code, name, source, description in DEFAULT_SERVICES:
        if code not in existing:
            db.add(
                Plan(
                    code=code,
                    name=name,
                    ai_source=source,
                    link_type=ServiceLinkType.PERSONAL,
                    description=description,
                    active=True,
                )
            )
    db.flush()


@dataclass(frozen=True)
class EffectiveService:
    name: str
    source: AISource
    link_type: ServiceLinkType
    code: str | None = None
    plan_id: int | None = None
    subscription_id: int | None = None
    expires_at: datetime | None = None
    origin: SubscriptionOrigin | None = None
    benefit_id: int | None = None
    benefit_name: str | None = None
    # Último servicio otorgado que venció hace poco (para avisar).
    expired_name: str | None = None
    expired_at: datetime | None = None

    @property
    def granted(self) -> bool:
        return self.subscription_id is not None

    def payload(self) -> dict:
        return {
            "name": self.name,
            "code": self.code,
            "source": self.source.value,
            "linkType": self.link_type.value,
            "granted": self.granted,
            "origin": self.origin.value if self.origin else None,
            "benefitId": self.benefit_id,
            "benefitName": self.benefit_name,
            "expiresAt": self.expires_at,
            "ownKeys": OWN_KEYS_ROLE[self.source],
            "expired": (
                {"name": self.expired_name, "at": self.expired_at} if self.expired_name else None
            ),
        }


DEFAULT_SERVICE = EffectiveService(
    name="Individual · propias keys",
    source=AISource.BYOK,
    link_type=ServiceLinkType.PERSONAL,
    code=DEFAULT_CODE,
)


def _expire_due(db: Session, account: Account) -> None:
    """Marca como vencidas las suscripciones cuya vigencia terminó (vencimiento perezoso)."""
    now = utcnow()
    changed = False
    for subscription in db.scalars(
        select(Subscription).where(
            Subscription.account_id == account.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at.is_not(None),
        )
    ).all():
        if _as_utc(subscription.expires_at) <= now:
            subscription.status = SubscriptionStatus.EXPIRED
            subscription.ended_at = subscription.expires_at
            changed = True
    if changed:
        db.flush()  # la sesión no hace autoflush


def effective_service(db: Session, account: Account) -> EffectiveService:
    """Servicio que rige ahora para la cuenta."""
    _expire_due(db, account)
    row = db.execute(
        select(Subscription, Plan)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(
            Subscription.account_id == account.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        .order_by(Subscription.started_at.desc(), Subscription.id.desc())
    ).first()
    if row is not None:
        subscription, plan = row
        benefit_name = None
        if subscription.benefit_id is not None:
            from app.benefits.models import Benefit
            benefit = db.get(Benefit, subscription.benefit_id)
            benefit_name = benefit.name if benefit is not None else None
        return EffectiveService(
            name=plan.name,
            source=plan.ai_source,
            link_type=plan.link_type,
            code=plan.code,
            plan_id=plan.id,
            subscription_id=subscription.id,
            expires_at=_as_utc(subscription.expires_at),
            origin=subscription.origin,
            benefit_id=subscription.benefit_id,
            benefit_name=benefit_name,
        )

    expired = db.execute(
        select(Subscription, Plan)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(
            Subscription.account_id == account.id,
            Subscription.status == SubscriptionStatus.EXPIRED,
        )
        .order_by(Subscription.ended_at.desc(), Subscription.id.desc())
    ).first()
    if expired is not None:
        subscription, plan = expired
        ended = _as_utc(subscription.ended_at or subscription.expires_at)
        if ended and utcnow() - ended <= RECENT_EXPIRY:
            return EffectiveService(
                name=DEFAULT_SERVICE.name,
                source=DEFAULT_SERVICE.source,
                link_type=DEFAULT_SERVICE.link_type,
                code=DEFAULT_CODE,
                expired_name=plan.name,
                expired_at=ended,
            )
    return DEFAULT_SERVICE


def grant_service(
    db: Session,
    account: Account,
    plan: Plan,
    *,
    granted_by: Account | None,
    days: int | None = None,
    origin: SubscriptionOrigin = SubscriptionOrigin.MANUAL,
    note: str | None = None,
) -> Subscription:
    """Otorga un servicio a la cuenta. Reemplaza al que tuviera vigente."""
    revoke_service(db, account)
    now = utcnow()
    subscription = Subscription(
        plan_id=plan.id,
        account_id=account.id,
        status=SubscriptionStatus.ACTIVE,
        started_at=now,
        expires_at=now + timedelta(days=days) if days else None,
        origin=origin,
        granted_by_account_id=granted_by.id if granted_by else None,
        note=note,
    )
    db.add(subscription)
    db.flush()
    return subscription


def revoke_service(db: Session, account: Account) -> int:
    """Cancela los servicios vigentes de la cuenta: vuelve a "Individual · propias keys"."""
    now = utcnow()
    count = 0
    for subscription in db.scalars(
        select(Subscription).where(
            Subscription.account_id == account.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
    ).all():
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.ended_at = now
        count += 1
    db.flush()
    return count
