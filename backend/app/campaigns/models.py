from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CampaignStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


class CampaignTrigger(str, Enum):
    FIRST_LOGIN = "FIRST_LOGIN"
    LOGIN = "LOGIN"
    # T-059 implementará el scheduler. Se modela desde ahora para no migrar el contrato después.
    SCHEDULED = "SCHEDULED"


class CampaignNotification(str, Enum):
    NONE = "NONE"
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    IN_APP_EMAIL = "IN_APP_EMAIL"


class CampaignAction(str, Enum):
    """Qué hace la campaña. T-065 explicita la acción sin duplicar motores."""

    GRANT_BENEFIT = "GRANT_BENEFIT"
    # Las siguientes quedan modeladas para evolución futura; capacidades.py decide disponibilidad.
    SEND_NOTIFICATION = "SEND_NOTIFICATION"
    GENERATE_REPORT = "GENERATE_REPORT"
    CREATE_INVITATION = "CREATE_INVITATION"
    APPLY_DISCOUNT = "APPLY_DISCOUNT"


class CampaignSeedMarker(Base):
    """Marca que una campaña ejemplo ya fue creada una vez."""

    __tablename__ = "campaign_seed_markers"

    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    seeded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Campaign(Base):
    """Regla configurable que aplica un beneficio cuando una cuenta cumple condiciones."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    benefit_id: Mapped[int] = mapped_column(ForeignKey("benefits.id"), index=True)
    # NULL = scope plataforma/OWNER. T-059/T-005 reutilizan esta columna para campañas de empresa.
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    status: Mapped[CampaignStatus] = mapped_column(
        SqlEnum(CampaignStatus, native_enum=False), default=CampaignStatus.DRAFT, index=True
    )
    trigger: Mapped[CampaignTrigger] = mapped_column(
        SqlEnum(CampaignTrigger, native_enum=False), default=CampaignTrigger.FIRST_LOGIN, index=True
    )
    eligibility: Mapped[dict] = mapped_column(JSON, default=lambda: {"mode": "ALL", "rules": []})
    action: Mapped[CampaignAction] = mapped_column(
        SqlEnum(CampaignAction, native_enum=False, length=40),
        default=CampaignAction.GRANT_BENEFIT,
        server_default=CampaignAction.GRANT_BENEFIT.value,
    )
    # Configuración reservada para futuras acciones; GRANT_BENEFIT sigue usando benefit_id.
    action_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    stackable: Mapped[bool] = mapped_column(Boolean, default=False)
    max_recipients: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notification: Mapped[CampaignNotification] = mapped_column(
        SqlEnum(CampaignNotification, native_enum=False), default=CampaignNotification.IN_APP
    )
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CampaignGrant(Base):
    """Beneficio efectivamente otorgado. La unicidad materializa nunca_recibió(campaña)."""

    __tablename__ = "campaign_grants"
    __table_args__ = (
        UniqueConstraint("campaign_id", "account_id", name="uq_campaign_grant_account"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=True
    )
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    benefit_summary: Mapped[str] = mapped_column(String(300))
    notification_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    in_app_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # T-051 consumirá los PENDING; el motor de campaña no envía correo directamente.
    email_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
