from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(120))
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str] = mapped_column(String(2), default="AR")
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class JobTitle(Base):
    """Catálogo reutilizable de cargos/funciones declarados por referentes."""

    __tablename__ = "job_titles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    normalized_name: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrganizationOnboardingStatus(str, Enum):
    DRAFT = "DRAFT"
    COMPANY_VERIFIED = "COMPANY_VERIFIED"
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ABANDONED = "ABANDONED"
    PROVISIONED = "PROVISIONED"


class OrganizationActingCapacity(str, Enum):
    LEGAL_REPRESENTATIVE = "LEGAL_REPRESENTATIVE"
    PROXY = "PROXY"
    AUTHORIZED_EMPLOYEE = "AUTHORIZED_EMPLOYEE"
    OTHER = "OTHER"


class OrganizationOnboarding(Base):
    """Solicitud previa al alta definitiva de Organization.

    P01 captura y verifica empresa + referente. No crea todavía Organization ni Membership.
    """

    __tablename__ = "organization_onboardings"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid4())
    )
    status: Mapped[OrganizationOnboardingStatus] = mapped_column(
        SqlEnum(OrganizationOnboardingStatus, native_enum=False),
        default=OrganizationOnboardingStatus.DRAFT,
        index=True,
    )

    country: Mapped[str] = mapped_column(String(2), default="AR", index=True)
    tax_id_type: Mapped[str] = mapped_column(String(32), default="CUIT")
    tax_id: Mapped[str] = mapped_column(String(64), index=True)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    legal_entity_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    registry_jurisdiction: Mapped[str | None] = mapped_column(String(160), nullable=True)
    registry_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fiscal_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    legal_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_activity: Mapped[str | None] = mapped_column(String(300), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)

    contact_first_name: Mapped[str] = mapped_column(String(100))
    contact_last_name: Mapped[str] = mapped_column(String(100))
    contact_email: Mapped[str] = mapped_column(String(320), index=True)
    contact_job_title_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_titles.id"), nullable=True, index=True
    )
    # Snapshot histórico del nombre aunque el catálogo cambie en el futuro.
    contact_job_title: Mapped[str] = mapped_column(String(160))
    contact_phone: Mapped[str] = mapped_column(String(64))
    acting_capacity: Mapped[OrganizationActingCapacity] = mapped_column(
        SqlEnum(OrganizationActingCapacity, native_enum=False)
    )
    authority_declared: Mapped[bool] = mapped_column(Boolean, default=False)

    verification_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verification_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    official_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    abandoned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
