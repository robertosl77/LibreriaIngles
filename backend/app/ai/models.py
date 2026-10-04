from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite devuelve datetimes sin zona: se asumen UTC."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class AIConnectionOwnerType(str, Enum):
    PLATFORM = "PLATFORM"
    ORGANIZATION = "ORGANIZATION"
    ACCOUNT = "ACCOUNT"


class AIConnectionStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    PROVIDER_DOWN = "PROVIDER_DOWN"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    DISABLED = "DISABLED"


class AIConnection(Base):
    __tablename__ = "ai_connections"
    __table_args__ = (
        CheckConstraint(
            "(owner_type = 'PLATFORM' AND owner_id IS NULL) "
            "OR (owner_type <> 'PLATFORM' AND owner_id IS NOT NULL)",
            name="ck_ai_connections_owner",
        ),
        Index("ix_ai_connections_owner", "owner_type", "owner_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_type: Mapped[AIConnectionOwnerType] = mapped_column(
        SqlEnum(AIConnectionOwnerType, native_enum=False)
    )
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    credentials_encrypted: Mapped[str | None] = mapped_column(
        String(4000), nullable=True
    )
    credential_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Límites de consumo (ventana móvil de 24 h). NULL = sin límite.
    # Pensados para conexiones PLATFORM, donde el costo lo asume la plataforma.
    daily_request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_account_daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[AIConnectionStatus] = mapped_column(
        SqlEnum(AIConnectionStatus, native_enum=False),
        default=AIConnectionStatus.AVAILABLE,
    )
    backoff_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    @property
    def is_usable(self) -> bool:
        if not self.active:
            return False
        if self.status in (
            AIConnectionStatus.INVALID_CREDENTIALS,
            AIConnectionStatus.DISABLED,
        ):
            return False
        backoff = as_utc(self.backoff_until)
        return backoff is None or backoff <= utcnow()


class AICredentialAuditEvent(Base):
    """Auditoría de copia de credenciales por PLATFORM_OWNER.

    Nunca guarda el secreto: solo quién, qué conexión, qué acción y cuándo.
    """

    __tablename__ = "ai_credential_audit_events"
    __table_args__ = (
        Index(
            "ix_ai_credential_audit_connection_created",
            "connection_id",
            "created_at",
        ),
        Index(
            "ix_ai_credential_audit_account_created",
            "account_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "ai_connections.id",
            name="fk_ai_credential_audit_connection_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", name="fk_ai_credential_audit_account_id"),
        nullable=False,
    )
    connection_name: Mapped[str] = mapped_column(String(120))
    owner_type: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class AIProviderUsageMapping(Base):
    """Cómo un proveedor externo declara sus contadores de consumo.

    Las rutas son dot-paths sobre el JSON de respuesta del proveedor. El motor de
    consumo las interpreta dinámicamente y no contiene condicionales por proveedor.
    """

    __tablename__ = "ai_provider_usage_mappings"

    provider: Mapped[str] = mapped_column(String(80), primary_key=True)
    input_tokens_path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    output_tokens_path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    total_tokens_path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIUsageEvent(Base):
    """Una llamada a un proveedor de IA (exitosa o fallida).

    Sirve para aplicar límites de consumo y para el portal de plataforma.
    No guarda prompts ni respuestas: solo metadatos.
    """

    __tablename__ = "ai_usage_events"
    __table_args__ = (
        Index("ix_ai_usage_events_connection_created", "connection_id", "created_at"),
        Index("ix_ai_usage_events_account_created", "account_id", "created_at"),
        Index("ix_ai_usage_events_organization_created", "organization_id", "created_at"),
        Index("ix_ai_usage_events_subject", "subject_type", "subject_id"),
        Index("ix_ai_usage_events_execution", "execution_id", "attempt_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "ai_connections.id",
            name="fk_ai_usage_events_connection_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    connection_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_type: Mapped[AIConnectionOwnerType] = mapped_column(
        SqlEnum(AIConnectionOwnerType, native_enum=False)
    )
    provider: Mapped[str] = mapped_column(String(80))
    # Modelo usado en esa llamada: una conexión puede cambiar de modelo con el tiempo.
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", name="fk_ai_usage_events_account_id"), nullable=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", name="fk_ai_usage_events_organization_id"),
        nullable=True,
    )
    membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id", name="fk_ai_usage_events_membership_id"),
        nullable=True,
    )
    # Fuente configurada en el servicio al momento del uso (BYOK/PLATFORM/HYBRID).
    # owner_type conserva además qué conexión atendió efectivamente.
    service_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Una ejecución lógica puede intentar varias conexiones por failover.
    execution_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempt_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operation: Mapped[str] = mapped_column(String(80))
    subject_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject_label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    subject_route: Mapped[str | None] = mapped_column(String(300), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
