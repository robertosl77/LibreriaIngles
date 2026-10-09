from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AISource(str, Enum):
    BYOK = "BYOK"
    PLATFORM = "PLATFORM"
    HYBRID = "HYBRID"


class ServiceLinkType(str, Enum):
    """Vínculo (T-004): personal (sin empresa) o corporativo (vía una empresa)."""

    PERSONAL = "PERSONAL"
    CORPORATE = "CORPORATE"


class SubscriptionOrigin(str, Enum):
    """Cómo se otorgó el servicio (T-004)."""

    MANUAL = "MANUAL"  # sr.macros desde su portal
    CAMPAIGN = "CAMPAIGN"  # etapa 2
    INVITATION = "INVITATION"  # etapa 3
    PAYMENT = "PAYMENT"  # futuro


class SubscriptionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class Plan(Base):
    """Servicio del catálogo (T-004): vínculo × fuente de IA + metadatos comerciales."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    ai_source: Mapped[AISource] = mapped_column(
        SqlEnum(AISource, native_enum=False)
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    link_type: Mapped[ServiceLinkType] = mapped_column(
        SqlEnum(ServiceLinkType, native_enum=False), default=ServiceLinkType.PERSONAL
    )
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # T-220 (N-01/E-08): límites propios del plan {clave: valor}. Clave ausente = hereda el valor
    # de plataforma. Las claves válidas son las del catálogo único (app/limits/registry.py).
    limits: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Subscription(Base):
    """Servicio otorgado a una cuenta (o empresa), con su vigencia."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    benefit_id: Mapped[int | None] = mapped_column(
        ForeignKey("benefits.id"), nullable=True, index=True
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True, index=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SqlEnum(SubscriptionStatus, native_enum=False),
        default=SubscriptionStatus.ACTIVE,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    origin: Mapped[SubscriptionOrigin] = mapped_column(
        SqlEnum(SubscriptionOrigin, native_enum=False), default=SubscriptionOrigin.MANUAL
    )
    granted_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
