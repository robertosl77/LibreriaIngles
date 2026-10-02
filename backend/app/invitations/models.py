from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InvitationRecipientMode(str, Enum):
    """NAMED = identidad/email concreto. OPEN = cualquiera con el link, sujeto a cupo."""

    NAMED = "NAMED"
    OPEN = "OPEN"


class InvitationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    EXHAUSTED = "EXHAUSTED"


class Invitation(Base):
    """Pre-invitación genérica.

    NULL organization_id = invitación emitida por PLATFORM_OWNER para vínculo personal.
    En etapa corporativa se reutiliza la misma tabla con organization_id.
    """

    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    created_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    benefit_id: Mapped[int | None] = mapped_column(
        ForeignKey("benefits.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    recipient_mode: Mapped[InvitationRecipientMode] = mapped_column(
        SqlEnum(InvitationRecipientMode, native_enum=False),
        default=InvitationRecipientMode.NAMED,
    )
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    # El link se guarda cifrado para poder reenviarlo por T-051 sin almacenar el secreto en claro.
    token_encrypted: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    status: Mapped[InvitationStatus] = mapped_column(
        SqlEnum(InvitationStatus, native_enum=False),
        default=InvitationStatus.ACTIVE,
        index=True,
    )
    max_redemptions: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # T-051 consumirá PENDING de invitaciones nominadas.
    email_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class InvitationRedemption(Base):
    """Canje individual de una invitación.

    Un link abierto puede generar muchos canjes, pero una misma cuenta no consume dos veces
    el mismo link.
    """

    __tablename__ = "invitation_redemptions"
    __table_args__ = (
        UniqueConstraint(
            "invitation_id",
            "account_id",
            name="uq_invitation_redemption_account",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invitation_id: Mapped[int] = mapped_column(ForeignKey("invitations.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=True
    )
    benefit_summary: Mapped[str] = mapped_column(String(300))
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
