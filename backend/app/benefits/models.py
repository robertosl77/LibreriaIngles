from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BenefitConflictPolicy(str, Enum):
    """Qué hacer si la cuenta ya tiene un servicio otorgado distinto."""

    EXTEND_SAME_SERVICE = "EXTEND_SAME_SERVICE"


class Benefit(Base):
    """Definición reusable de un otorgamiento de servicio.

    Campañas e invitaciones referencian esta capa para no duplicar servicio + duración.
    NULL organization_id = beneficio administrado por PLATFORM_OWNER.
    """

    __tablename__ = "benefits"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conflict_policy: Mapped[BenefitConflictPolicy] = mapped_column(
        SqlEnum(BenefitConflictPolicy, native_enum=False),
        default=BenefitConflictPolicy.EXTEND_SAME_SERVICE,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
